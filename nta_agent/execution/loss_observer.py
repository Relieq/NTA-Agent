"""Hands-side observer: detect real troop losses and record them (Cách A).

It watches the battle-records list (every ``poll_every`` ticks, and at once when the
dead/injured pawn count rises). Every NEW record whose ``deadInfo`` is non-empty
(our pawns died in it) is fetched, replayed through the sim for grounded detail
(which monster, AoE, exact deaths) and a counterfactual order — then recorded as a
``battle_loss`` event in the ledger for the brain to learn from, once per record.

Why not "the latest record when injuries rise" (the old way): a lossy battle is
often NOT the newest one by the time the injury count moves, and injuries can be
cured/revived between ticks — live on 2026-09-25 that caught 2 of 4 lossy battles
and replayed the wrong ones (reporting 0 deaths). Best-effort: any failure is an
event, never an exception in the loop.
"""
from __future__ import annotations

from nta_agent.execution.counterfactual import best_counterfactual_order, summarize_record


class LossObserver:
    name = "loss_observer"

    def __init__(self, actions, ledger, bridge, player_uid, on_event=None,
                 poll_every: int = 12, give_up_after: int = 3):
        self.actions = actions
        self.ledger = ledger
        self.bridge = bridge
        self.player_uid = str(player_uid)
        self._on_event = on_event or (lambda *a: None)
        self.poll_every = poll_every
        self.give_up_after = give_up_after
        self._last_injured: int | None = None
        self._ticks = 0
        self._seen: set[str] | None = None   # record uids already handled (None = no baseline)
        self._unexplained = 0                # injury rise not yet matched to a record
        self._unexplained_scans = 0

    # ------------------------------------------------------------------ tick -- #
    def tick(self, state) -> None:
        player = (getattr(state, "raw", None) or {}).get("player") or {}
        injured = len(player.get("injuryPawns") or [])
        prev = self._last_injured
        self._last_injured = injured
        rose = prev is not None and injured > prev
        if rose:
            self._unexplained += injured - prev
        due = self._ticks % self.poll_every == 0
        self._ticks += 1
        if not (rose or due or self._unexplained):
            return
        try:
            found = self._scan()
        except Exception as e:  # observability must never break the loop
            self._on_event("loss_observer_error", {"err": str(e)})
            return
        self._settle_unexplained(found)

    # ------------------------------------------------------------------ scan -- #
    def _scan(self) -> int:
        """Record every new lossy battle; returns our deaths recorded this scan."""
        records = self.actions.get_battle_records_list() or []
        if self._seen is None:  # baseline: battles from before we started aren't ours
            self._seen = {str(r.get("uid")) for r in records}
            return 0
        new = [r for r in records if str(r.get("uid")) not in self._seen]
        new.sort(key=lambda r: r.get("endTime", 0) or 0)
        found = 0
        for r in new:
            self._seen.add(str(r.get("uid")))
            dead = r.get("deadInfo")
            if not (isinstance(dead, list) and dead):
                continue  # nobody of ours died in this one
            found += self._record(r, len(dead))
        return found

    def _record(self, listed: dict, listed_dead: int) -> int:
        uid = str(listed.get("uid"))
        ctx: dict = {"self_dead": listed_dead, "cell": listed.get("index"),
                     "record_uid": uid, "end_ms": listed.get("endTime")}
        record = self.actions.get_battle_record(uid)
        if record and record.get("frames") and self.bridge is not None:
            summ = summarize_record(self.bridge, record)
            faithful = True
            if summ:
                # the game's own count (deadInfo) is authoritative; a replay that
                # disagrees (live: 0 vs 1) is kept for reference but not trusted for
                # the "what if" order below
                replay_dead = summ.get("summary", {}).get("self_dead", listed_dead)
                if replay_dead != listed_dead:
                    ctx["replay_dead"] = replay_dead
                    faithful = False
                ctx["enemy_ids"] = summ.get("enemy_ids", [])
                ctx["aoe"] = bool(summ.get("aoe"))
            cf = best_counterfactual_order(self.bridge, record) if faithful else None
            if cf:
                ctx["counterfactual"] = cf
        eid = self.ledger.record("battle_loss", ctx)
        self._on_event("battle_loss", {"id": eid, **ctx})
        return int(ctx["self_dead"] or 0)

    def _settle_unexplained(self, found: int) -> None:
        """Injuries that no record explains (list lag) get a few more scans, then are
        recorded from the injury delta alone so a loss is never silently dropped."""
        if not self._unexplained:
            self._unexplained_scans = 0
            return
        self._unexplained = max(0, self._unexplained - found)
        if not self._unexplained:
            self._unexplained_scans = 0
            return
        self._unexplained_scans += 1
        if self._unexplained_scans >= self.give_up_after:
            ctx = {"self_dead": self._unexplained, "cell": None, "unmatched": True}
            eid = self.ledger.record("battle_loss", ctx)
            self._on_event("battle_loss", {"id": eid, **ctx})
            self._unexplained, self._unexplained_scans = 0, 0
