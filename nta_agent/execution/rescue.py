"""Revived pawns go home: remember which army each pawn stood in, and plan their way back.

``ReviveInjured`` puts a revived pawn into the dedicated rescue army ("Cứu Hộ", see
:mod:`nta_agent.execution.injury`) unless its own army can take it at the city. The pawn still
belongs to the army it died in: :func:`plan_returns` pairs every rescued pawn with that army
(or, when the origin is unknown, with the group army missing a pawn of its type) and the
:class:`~nta_agent.runtime.rescue_service.RescueService` hands the result to the pawn-move queue,
which gathers both armies in one cell and moves the pawn. PURE: no engine / API.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from nta_agent.execution.injury import NEW_ARMY_NAME

ARMY_CAP = 9


def is_rescue(army: dict) -> bool:
    return str((army or {}).get("name", "")).startswith(NEW_ARMY_NAME)


def _used(army: dict) -> int:
    """Slots taken: pawns standing + recruits in training (they land in this army)."""
    return len(army.get("pawns") or []) + len(army.get("drillPawns") or [])


class OriginBook:
    """pawn uid -> the (non-rescue) army it was last seen in. Persisted, so the answer survives
    the pawn dying, being revived into the rescue army and an agent restart."""

    def __init__(self, path, keep_s: float = 86400.0):
        self.path = Path(path)
        self.keep_s = keep_s
        self._d: dict[str, dict] = {}
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                self._d = {str(k): v for k, v in d.items() if isinstance(v, dict)}
        except (OSError, ValueError):
            pass

    def origin(self, pawn_uid: str) -> str | None:
        rec = self._d.get(str(pawn_uid))
        return rec.get("army") if rec else None

    def set(self, pawn_uid: str, army_uid: str, now: float | None = None) -> None:
        self._d[str(pawn_uid)] = {"army": str(army_uid), "seen": now if now is not None else time.time()}

    def update(self, armies, injured, now: float | None = None) -> bool:
        """Refresh from the live army list; returns True when something changed (and saved)."""
        now = time.time() if now is None else now
        before = json.dumps(self._d, sort_keys=True)
        alive: set[str] = set()
        for a in armies or []:
            for p in a.get("pawns") or []:
                uid = str(p.get("uid"))
                alive.add(uid)
                if not is_rescue(a):
                    self._d[uid] = {"army": str(a.get("uid")), "seen": now}
                elif uid in self._d:
                    self._d[uid]["seen"] = now        # keeps its real origin while rescued
        dead = {str(p.get("uid")) for p in injured or []}
        for uid in list(self._d):
            if uid in alive or uid in dead:
                if uid in dead:
                    self._d[uid]["seen"] = now
                continue
            if now - float(self._d[uid].get("seen", 0) or 0) > self.keep_s:
                del self._d[uid]
        changed = json.dumps(self._d, sort_keys=True) != before
        if changed:
            self.save()
        return changed

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def origins_of(self, pawn_uids) -> set[str]:
        return {o for o in (self.origin(u) for u in pawn_uids) if o}


def _main_type(army: dict) -> int | None:
    from collections import Counter
    c = Counter(int(p.get("id", 0) or 0) for p in army.get("pawns") or [] if p.get("id"))
    return c.most_common(1)[0][0] if c else None


def plan_returns(armies, book: OriginBook, group=(), cap: int = ARMY_CAP) -> list[dict]:
    """``[{"from": rescue uid, "to": army uid, "pawns": [pawn uid, ...]}]``: where every rescued
    pawn goes. Home first (the army it was last seen in, if it still exists and has a free slot —
    a slot already being drilled counts as taken); else the army of the farm ``group`` (in the
    player's order) with room whose main troop type is the pawn's; else it waits in the rescue
    army. Several pawns never overfill one target."""
    by_uid = {str(a.get("uid")): a for a in armies or []}
    incoming: dict[str, int] = {}

    def room(a) -> bool:
        return _used(a) + incoming.get(str(a.get("uid")), 0) < cap

    out: list[dict] = []
    for r in armies or []:
        if not is_rescue(r) or not r.get("pawns"):
            continue
        by_target: dict[str, list[str]] = {}
        for p in r.get("pawns") or []:
            uid, pid = str(p.get("uid")), int(p.get("id", 0) or 0)
            tgt = by_uid.get(book.origin(uid) or "")
            if tgt is None or is_rescue(tgt) or not room(tgt):
                tgt = next((by_uid[g] for g in map(str, group)
                            if g in by_uid and not is_rescue(by_uid[g]) and room(by_uid[g])
                            and _main_type(by_uid[g]) == pid), None)
            if tgt is None:
                continue
            by_target.setdefault(str(tgt["uid"]), []).append(uid)
            incoming[str(tgt["uid"])] = incoming.get(str(tgt["uid"]), 0) + 1
        out += [{"from": str(r["uid"]), "to": t, "pawns": ps} for t, ps in by_target.items()]
    return out
