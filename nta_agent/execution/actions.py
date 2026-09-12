"""High-level game actions — the "hands" translate intents into API calls.

Each method wraps one or more ``_C2S`` requests behind a typed, verified call and
keeps :class:`GameState` in step with the result. Higher layers (rules, brain)
call these; they never touch the codec or MQTT client directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nta_agent.io.api.session import GameSession

# StudyType tp -> the player slot-map field it updates (verified in client).
TP_SLOT_KEY = {1: "policySlots", 2: "pawnSlots", 3: "equipSlots"}


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

    # ---- recruiting ------------------------------------------------------ #
    def drill_pawn(
        self,
        build_uid: str,
        pawn_id: int,
        *,
        index: int | None = None,
        army_uid: str = "",
        army_name: str = "",
    ) -> dict:
        """Recruit a pawn at a spawn building (GAME_HD_DRILLPAWN).

        ``army_uid`` empty + ``army_name`` set creates a new army; otherwise the
        pawn joins the given army. Defaults to the main city.
        """
        idx = index if index is not None else self.main_city_index()
        reply = self.session.request("game/HD_DrillPawn", {
            "index": int(idx), "buildUid": str(build_uid), "id": int(pawn_id),
            "armyUid": str(army_uid), "armyName": str(army_name),
        })
        self._apply_result(reply)
        return reply

    def building_uid(self, build_id: int) -> str:
        """The uid of the player's building with ``build_id`` (0/'' if none)."""
        for b in self._state.builds:
            if b.id == build_id:
                return b.uid
        return ""

    # ---- task rewards ---------------------------------------------------- #
    def _apply_task_reply(self, reply: dict, list_updates: dict[str, str]) -> dict:
        """Apply a claim reply: credit ``rewards`` and refresh player task lists.

        ``list_updates`` maps a reply key (e.g. ``"tasks"``) to the player key it
        replaces (e.g. ``"guideTasks"``).
        """
        rewards = reply.get("rewards", {})
        if isinstance(rewards, dict):
            from nta_agent.state.store import apply_update_output
            apply_update_output(self._state, rewards)
        player = (self._state.raw or {}).setdefault("player", {})
        for reply_key, player_key in list_updates.items():
            if isinstance(reply.get(reply_key), list):
                player[player_key] = reply[reply_key]
        return rewards

    def claim_task(self, task_id: int) -> dict:
        """Claim a completed guide/chapter task (GAME_HD_CLAIMTASKREWARD)."""
        reply = self.session.request("game/HD_ClaimTaskReward", {"id": int(task_id)})
        return self._apply_task_reply(reply, {"tasks": "guideTasks", "todayTasks": "todayTasks"})

    def claim_other_task(self, task_id: int, treasure_index: int = 0, select_index: int = 0) -> dict:
        """Claim a completed 'other' task (GAME_HD_CLAIMOTHERTASKREWARD)."""
        reply = self.session.request("game/HD_ClaimOtherTaskReward", {
            "id": int(task_id), "treasureIndex": int(treasure_index), "selectIndex": int(select_index),
        })
        return self._apply_task_reply(reply, {"otherTasks": "otherTasks"})

    def claim_today_task(self, task_id: int, treasure_index: int = 0, select_index: int = 0) -> dict:
        """Claim a completed today/daily task (GAME_HD_CLAIMTODAYTASKREWARD)."""
        reply = self.session.request("game/HD_ClaimTodayTaskReward", {
            "id": int(task_id), "treasureIndex": int(treasure_index), "selectIndex": int(select_index),
        })
        return self._apply_task_reply(reply, {"todayTasks": "todayTasks"})

    # ---- ceri: unlock pawn / policy / equip (human-reserved) ------------- #
    def study_select(self, lv: int, ceri_id: int, tp: int) -> dict:
        """Pick a ceri option (GAME_HD_StudySelect). Applies returned slots."""
        reply = self.session.request("game/HD_StudySelect",
                                     {"lv": int(lv), "id": int(ceri_id), "tp": int(tp)})
        slots = reply.get("slots")
        key = TP_SLOT_KEY.get(int(tp))
        if isinstance(slots, dict) and key:
            player = (self._state.raw or {}).setdefault("player", {})
            player[key] = slots
        return reply

    def ceri_reset(self, lv: int, tp: int) -> dict:
        """Reroll the ceri options for a track/level (GAME_HD_CeriResetSelect)."""
        return self.session.request("game/HD_CeriResetSelect", {"lv": int(lv), "tp": int(tp)})

    # ---- captcha (anti-cheat) ------------------------------------------- #
    def get_anticheat_question(self) -> dict:
        """Fetch the current anti-cheat captcha (GAME_HD_GetAntiCheatQuestion)."""
        return self.session.request("game/HD_GetAntiCheatQuestion", {})

    def answer_anticheat(self, answer: int) -> dict:
        """Submit a captcha answer (GAME_HD_AntiCheatAnswer)."""
        return self.session.request("game/HD_AntiCheatAnswer", {"answer": int(answer)})

    # ---- equipment (gear assignment) ------------------------------------ #
    def change_pawn_equip(self, pawn_id: int, equip_uid: str,
                          skin_id: int = 0, attack_speed: int = 0) -> dict:
        """Assign an owned equip to a pawn config (GAME_HD_ChangeConfigPawnEquip)."""
        return self.session.request("game/HD_ChangeConfigPawnEquip", {
            "id": int(pawn_id), "equipUid": str(equip_uid),
            "skinId": int(skin_id), "attackSpeed": int(attack_speed),
        })

    # ---- army reads ----------------------------------------------------- #
    def get_player_armys(self) -> list[dict]:
        """All of the player's armies with their pawns (GAME_HD_GetPlayerArmys)."""
        reply = self.session.request("game/HD_GetPlayerArmys", {})
        return reply.get("list", []) or []

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
    def predict_occupy(self, cell_index: int, my_pawns: list[dict], predictor=None, *, use_sim=True):
        """Predict occupying ``cell_index`` with ``my_pawns``.

        Prefers the headless engine sim (authoritative, matches the in-game
        forecast) when the sidecar is reachable; otherwise runs the stats
        heuristic. Returns a BattlePrediction.
        """
        from nta_agent.execution.predictors.battle import (
            BattlePredictor,
            enemy_pawns_of_area,
        )
        area = self.get_area(cell_index).get("data", {})
        if predictor is None and use_sim:
            # Try the real engine first; fall back to stats on any unavailability.
            from nta_agent.execution.predictors.sim_bridge import SimUnavailable, get_bridge
            if get_bridge().available():
                from nta_agent.execution.predictors.sim_predictor import SimBattlePredictor
                army = {"index": self.main_city_index(), "uid": "", "name": "D1", "pawns": my_pawns}
                dist = abs(self.main_city_index() % 600 - cell_index % 600) + abs(
                    self.main_city_index() // 600 - cell_index // 600)
                try:
                    return SimBattlePredictor().predict_target(
                        self._state, army, target_index=cell_index,
                        land_id=int(area.get("landId", 0) or 0), distance=dist,
                    )
                except SimUnavailable:
                    pass
        if predictor is None:
            # Prefer the config-driven army-value model; fall back to the hp/lv proxy.
            try:
                predictor = BattlePredictor.from_stats()
            except FileNotFoundError:
                predictor = BattlePredictor()
        enemy = enemy_pawns_of_area(area, my_uid=self._state.user.uid)
        return predictor.predict(my_pawns, enemy)
