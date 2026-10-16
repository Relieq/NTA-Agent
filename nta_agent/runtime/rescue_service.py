"""Bring revived pawns home.

``ReviveInjured`` revives a dead pawn into the rescue army ("Cứu Hộ") unless its own army can take
it at the city. This service remembers which army every pawn stood in (``OriginBook``) and, for
each rescued pawn, queues a move job — the same durable queue the player's confirmed moves use —
that gathers the rescue army and the pawn's army in one cell and moves the pawn back. It also
tells the other rules what to leave alone: the rescue armies (nobody may send them off, top them
up or reshape them) and the armies whose free slot a dead or rescued pawn is coming back to
(no recruit may take that slot).
"""
from __future__ import annotations

import time


class RescueService:
    def __init__(self, actions, queue, book, *, profile=None, territory_source=None,
                 on_event=None, every: int = 3, retry_s: float = 120.0, cap: int = 9):
        self.actions = actions
        self.queue = queue
        self.book = book
        self.profile = profile
        self.territory_source = territory_source
        self._on_event = on_event or (lambda *a: None)
        self.every = max(1, int(every))
        self.retry_s = retry_s
        self.cap = cap
        self._n = 0
        self._rescue: set[str] = set()
        self._vacancy: set[str] = set()
        self._last: dict[tuple, float] = {}
        self._said: set[tuple] = set()

    # --- what the other rules must leave alone -----------------------------------------
    def rescue_uids(self) -> set[str]:
        return set(self._rescue)

    def vacancy_uids(self) -> set[str]:
        return set(self._vacancy)

    def origin_of(self, pawn_uid: str) -> str | None:
        return self.book.origin(pawn_uid)

    def _group(self) -> list[str]:
        try:
            from nta_agent.execution.profile import active_formation
            return [str(g) for g in (active_formation(self.profile).get("group") or [])]
        except Exception:
            return []

    # --- the tick ------------------------------------------------------------------------
    def tick(self, state) -> None:
        self._n += 1
        if (self._n - 1) % self.every:
            return
        from nta_agent.execution.army_health import is_idle
        from nta_agent.execution.rescue import is_rescue, plan_returns
        armies = self.actions.get_player_armys() or []
        player = (getattr(state, "raw", None) or {}).get("player") or {}
        injured = list(player.get("injuryPawns") or [])
        self.book.update(armies, injured)
        by_uid = {str(a.get("uid")): a for a in armies}
        self._rescue = {str(a.get("uid")) for a in armies if is_rescue(a)}
        holding = {str(p.get("uid")) for a in armies if is_rescue(a) for p in a.get("pawns") or []}
        self._vacancy = {u for u in self.book.origins_of({str(p.get("uid")) for p in injured} | holding)
                         if u in by_uid}
        if not self._rescue:
            return
        busy = self.queue.army_uids()
        now = time.time()
        for plan in plan_returns(armies, self.book, self._group(), cap=self.cap):
            src, dst = by_uid[plan["from"]], by_uid[plan["to"]]
            self._vacancy.add(plan["to"])
            if plan["from"] in busy or plan["to"] in busy:
                continue      # a job (this one, or the player's) already holds them
            key = (plan["from"], plan["to"])
            if now - self._last.get(key, 0.0) < self.retry_s:
                continue
            if not (is_idle(src) and is_idle(dst)):
                continue      # the queue would only wait: queue it when both can move
            job = self._job(src, dst, plan["pawns"], state)
            if job is None:
                if key not in self._said:
                    self._said.add(key)
                    self._on_event("rescue_wait", {"from": src.get("name"), "to": dst.get("name"),
                                                   "note": "chưa chọn được ô để hai đội gặp nhau"})
                continue
            self._last[key] = now
            self.queue.add(job)
            self._on_event("rescue_return", {"from": src.get("name"), "to": dst.get("name"),
                                             "pawns": len(plan["pawns"]),
                                             "gather": job["gather"]})

    def _job(self, src: dict, dst: dict, pawn_uids: list[str], state) -> dict | None:
        gather = int(src.get("index", 0) or 0) != int(dst.get("index", 0) or 0)
        meet = None
        if gather:
            from nta_agent.execution.pawn_moves import choose_meet
            try:
                owned = set((self.territory_source() or (set(), []))[0]) if self.territory_source else set()
            except Exception:
                owned = set()
            occupied: dict[int, int] = {}
            for a in self.actions.get_player_armys() or []:
                i = int(a.get("index", 0) or 0)
                occupied[i] = occupied.get(i, 0) + 1
            meet = choose_meet([src.get("index"), dst.get("index")], owned,
                               fallback=int(getattr(state, "main_city_index", 0) or 0) or None,
                               occupied=occupied, anchor=int(dst.get("index", 0) or 0))
            if meet is None:
                return None
        return {"op": "move", "from": str(src["uid"]), "to": str(dst["uid"]),
                "name_from": src.get("name") or str(src["uid"]),
                "name_to": dst.get("name") or str(dst["uid"]),
                "index": int((meet if gather else src.get("index", 0)) or 0),
                "gather": gather, "meet": meet,
                "travel": [x.get("name") or str(x["uid"]) for x in (src, dst)
                           if gather and x.get("index") != meet],
                "stay": [x.get("name") or str(x["uid"]) for x in (src, dst)
                         if gather and x.get("index") == meet],
                "pawn_id": None, "count": len(pawn_uids), "pawn_uids": list(pawn_uids)}
