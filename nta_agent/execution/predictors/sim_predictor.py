"""Battle predictor backed by the headless engine sidecar.

Produces a :class:`BattlePrediction` whose ``win``/``loss_percent``/``loss_lv``
come straight from the game's own forecast (deterministic client seed). The
power fields are filled from the combat-stats valuer for continuity with the
older predictors and for army *selection*; they no longer drive the decision.
"""
from __future__ import annotations

from typing import Any

from nta_agent.execution.predictors.battle import BattlePrediction, default_pawn_power
from nta_agent.execution.predictors.sim_bridge import SimUnavailable, get_bridge
from nta_agent.execution.predictors.sim_input import build_forecast_input
from nta_agent.state.schema import GameState


class SimBattlePredictor:
    """Predict occupy/attack outcomes by running the real engine headless."""

    def __init__(self, bridge=None, config=None) -> None:
        self.bridge = bridge if bridge is not None else get_bridge()
        self._config = config
        self._valuer = None

    # ---- power (for army selection / continuity fields) ----------------- #
    @property
    def pawn_power(self):
        if self._valuer is None:
            try:
                from nta_agent.execution.predictors.combat import stat_pawn_power
                self._valuer = stat_pawn_power(self._config)
            except (FileNotFoundError, ImportError):
                self._valuer = default_pawn_power
        return self._valuer

    def _power(self, pawns: list[dict]) -> float:
        pp = self.pawn_power
        return sum(pp(p) for p in pawns or [])

    # ---- prediction ----------------------------------------------------- #
    def predict_target(
        self,
        state: GameState,
        army: dict[str, Any],
        *,
        target_index: int,
        land_id: int,
        distance: int,
        area_size: int | None = None,
        enemy_army_conf: dict | None = None,
    ) -> BattlePrediction:
        """Run the headless forecast for a single ``army`` attacking a target."""
        return self.predict_armies(
            state, [army], target_index=target_index, land_id=land_id,
            distance=distance, area_size=area_size, enemy_army_conf=enemy_army_conf)

    def predict_armies(
        self,
        state: GameState,
        armies: list[dict[str, Any]],
        *,
        target_index: int,
        land_id: int,
        distance: int,
        area_size: int | None = None,
        enemy_army_conf: dict | None = None,
    ) -> BattlePrediction:
        """Run the headless forecast for ``armies`` (selection order) on a target.

        Multiple armies use the reinforcement path: the first arrives, later ones
        join as waves — reproducing the 1-tile turn order.
        """
        inp = build_forecast_input(
            state, armies,
            target_index=target_index, land_id=land_id, distance=distance,
            area_size=area_size, enemy_army_conf=enemy_army_conf,
        )
        res = self.bridge.forecast(inp)

        my_pawns = [p for a in armies for p in (a.get("pawns") or [])]
        my_power = self._power(my_pawns)
        enemy_pawns = []
        if enemy_army_conf:
            for a in enemy_army_conf.get("armys", []) or []:
                enemy_pawns.extend(a.get("pawns", []) or [])
        enemy_power = self._power(enemy_pawns)
        ratio = my_power / enemy_power if enemy_power > 0 else float("inf")

        return BattlePrediction(
            win=bool(res.get("isWin")),
            my_power=my_power,
            enemy_power=enemy_power,
            ratio=ratio,
            loss_percent=float(res.get("lossPercent", 0.0) or 0.0),
            loss_lv=int(res.get("lossLv", 0) or 0),
            pawn_survival=(res.get("survivors") or {}).get("pawns"),
            duration_s=(float(res["durationS"]) if res.get("durationS") is not None else None),
        )

    def predict(self, my_pawns: list[dict], enemy_pawns: list[dict]) -> BattlePrediction:
        """Interface-compatible entry point.

        The engine needs the target context (cell/land/distance) to seed and to
        place fighters, which this signature lacks — so callers must use
        :meth:`predict_target`. Raising keeps the occupy rule falling back to the
        stats predictor rather than guessing.
        """
        raise SimUnavailable("SimBattlePredictor.predict() needs target context; use predict_target()")
