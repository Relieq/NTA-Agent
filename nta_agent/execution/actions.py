"""High-level game actions — the "hands" translate intents into API calls.

Each method wraps one or more ``_C2S`` requests behind a typed, verified call and
keeps :class:`GameState` in step with the result. Higher layers (rules, brain)
call these; they never touch the codec or MQTT client directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nta_agent.io.api.session import GameSession


@dataclass
class Actions:
    session: GameSession

    @property
    def _state(self):
        return self.session.state

    def _player(self) -> dict[str, Any]:
        raw = self._state.raw or {}
        return raw.get("player") or {}

    def main_city_index(self) -> int:
        """The player's main city index (from the live Entry rst)."""
        if self._state.main_city_index:
            return self._state.main_city_index
        idx = self._player().get("mainCityIndex")
        if idx:
            return int(idx)
        mc = self._state.main_city
        return mc.index if mc else 0

    # ---- resource economy ------------------------------------------------ #
    def _apply_result(self, reply: dict) -> None:
        """Keep GameState current from an action reply (output + build queue)."""
        from nta_agent.state.store import apply_update_output
        out = reply.get("output")
        if isinstance(out, dict):
            apply_update_output(self._state, out)
        if "queues" in reply and isinstance(reply["queues"], list):
            self._state.build_queue = reply["queues"]

    def collect_city_output(self, index: int | None = None) -> dict:
        """Claim accumulated output from a city (default: the main city).

        Safe and beneficial: gathers the player's own produced resources.
        Returns the decoded ``UpdateOutPut`` rewards.
        """
        idx = index if index is not None else self.main_city_index()
        if not idx:
            raise ValueError("no city index to collect from")
        reply = self.session.request("game/HD_ClaimCityOutput", {"index": int(idx)})
        rewards = reply.get("rewards", {})
        if isinstance(rewards, dict):
            from nta_agent.state.store import apply_update_output
            apply_update_output(self._state, rewards)
        return rewards

    # ---- construction ---------------------------------------------------- #
    def upgrade_build(self, index: int, uid: str = "") -> dict:
        """Upgrade the building at a tile index (GAME_HD_UPAREABUILD)."""
        params = {"index": int(index)}
        if uid:
            params["uid"] = uid
        reply = self.session.request("game/HD_UpAreaBuild", params)
        self._apply_result(reply)
        return reply

    # ---- reads ----------------------------------------------------------- #
    def get_area(self, index: int, no_record: bool = True) -> dict:
        return self.session.request(
            "game/HD_GetAreaInfo", {"index": int(index), "noRecord": no_record}
        )

    def get_marches(self) -> dict:
        return self.session.request("game/HD_GetMarchs", {})

    def get_select_armys(self, index: int, type_: int = 0) -> dict:
        return self.session.request("game/HD_GetSelectArmys", {"index": int(index), "type": type_})

    def select_armies(self, cell_index: int, type_: int = 0) -> list[dict]:
        """The armies (AreaArmyInfo) available to send at ``cell_index``."""
        return self.get_select_armys(cell_index, type_).get("list", []) or []

    # ---- combat ---------------------------------------------------------- #
    def occupy_cell(
        self,
        target: int,
        armies: list[dict],
        *,
        auto_back_type: int = 0,
        same_speed: bool = False,
    ) -> dict:
        """March ``armies`` to occupy/attack cell ``target`` (GAME_HD_OCCUPYCELL).

        ``armies`` are AreaArmyInfo dicts (need ``index`` and ``uid``).
        """
        indexs = [int(a["index"]) for a in armies]
        uids = [str(a["uid"]) for a in armies]
        reply = self.session.request("game/HD_OccupyCell", {
            "indexs": indexs, "uids": uids, "target": int(target),
            "autoBackType": int(auto_back_type), "isSameSpeed": bool(same_speed),
        })
        self._apply_result(reply)
        return reply

    # ---- prediction ------------------------------------------------------ #
    def predict_occupy(self, cell_index: int, my_pawns: list[dict], predictor=None):
        """Predict occupying ``cell_index`` with ``my_pawns`` (pure-API heuristic).

        Fetches the target area, extracts its hostile pawns, and runs the battle
        predictor. Returns a BattlePrediction.
        """
        from nta_agent.execution.predictors.battle import (
            BattlePredictor,
            enemy_pawns_of_area,
        )
        if predictor is None:
            # Prefer the config-driven army-value model; fall back to the hp/lv proxy.
            try:
                predictor = BattlePredictor.from_config()
            except FileNotFoundError:
                predictor = BattlePredictor()
        area = self.get_area(cell_index).get("data", {})
        enemy = enemy_pawns_of_area(area, my_uid=self._state.user.uid)
        return predictor.predict(my_pawns, enemy)
