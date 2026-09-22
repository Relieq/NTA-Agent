"""Hands-side observer: detect real troop losses and record them (Cách A).

Each tick it watches the player's dead-pawn count. When it rises (a battle cost
us troops) it fetches the latest battle record, replays it through the sim for
grounded detail (which monster, AoE, exact deaths) and runs a counterfactual to
see whether a different army order would have lost fewer troops — then records a
``battle_loss`` event in the ledger for the brain to learn from. Best-effort: any
failure falls back to the injury delta and never breaks the loop.
"""
from __future__ import annotations

from nta_agent.execution.counterfactual import best_counterfactual_order, summarize_record


class LossObserver:
    name = "loss_observer"

    def __init__(self, actions, ledger, bridge, player_uid, on_event=None):
        self.actions = actions
        self.ledger = ledger
        self.bridge = bridge
        self.player_uid = str(player_uid)
        self._on_event = on_event or (lambda *a: None)
        self._last_injured: int | None = None

    def tick(self, state) -> None:
        player = (getattr(state, "raw", None) or {}).get("player") or {}
        injured = len(player.get("injuryPawns") or [])
        prev = self._last_injured
        self._last_injured = injured
        if prev is None or injured <= prev:
            return
        try:
            self._record_latest_battle(injured - prev)
        except Exception as e:  # observability must never break the loop
            self._on_event("loss_observer_error", {"err": str(e)})

    def _record_latest_battle(self, new_dead: int) -> None:
        ctx: dict = {"self_dead": new_dead}
        records = self.actions.get_battle_records_list() or []
        if records:
            latest = max(records, key=lambda r: r.get("endTime", 0) or 0)
            ctx["cell"] = latest.get("index")
            record = self.actions.get_battle_record(str(latest.get("uid")))
            if record and record.get("frames") and self.bridge is not None:
                summ = summarize_record(self.bridge, record)
                if summ:
                    ctx["self_dead"] = summ.get("summary", {}).get("self_dead", new_dead)
                    ctx["enemy_ids"] = summ.get("enemy_ids", [])
                    ctx["aoe"] = bool(summ.get("aoe"))
                cf = best_counterfactual_order(self.bridge, record)
                if cf:
                    ctx["counterfactual"] = cf
        eid = self.ledger.record("battle_loss", ctx)
        self._on_event("battle_loss", {"id": eid, **ctx})
