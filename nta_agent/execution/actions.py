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

    def add_build(self, index: int, build_id: int) -> dict:
        """Construct a new building; the server auto-places it (GAME_HD_AddAreaBuild)."""
        return self.session.request("game/HD_AddAreaBuild",
                                    {"index": int(index), "id": int(build_id)})

    # ---- reads ----------------------------------------------------------- #
    def get_area(self, index: int, no_record: bool = True) -> dict:
        return self.session.request(
            "game/HD_GetAreaInfo", {"index": int(index), "noRecord": no_record}
        )

    def get_marches(self) -> dict:
        return self.session.request("game/HD_GetMarchs", {})

    def get_map_chunk(self, chunk_id: int) -> dict:
        """Fetch a packed map chunk: cells: map<playerUid, PlayerCellBytesInfo>."""
        return self.session.request("game/HD_GetMapChunk", {"chunkId": int(chunk_id)})

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
        """Reroll the ceri options for a track/level (GAME_HD_CeriResetSelect).

        The reply carries the fresh ``selectIds``/``resetCount`` directly (not a
        slot map), so apply them onto the matching pending slot — otherwise the
        local state keeps the old options and the reroll looks like a no-op.
        """
        reply = self.session.request("game/HD_CeriResetSelect", {"lv": int(lv), "tp": int(tp)})
        key = TP_SLOT_KEY.get(int(tp))
        select_ids = reply.get("selectIds")
        player = (self._state.raw or {}).get("player") if self._state else None
        if player and key and isinstance(select_ids, list):
            for slot in (player.get(key) or {}).values():
                if (isinstance(slot, dict) and int(slot.get("lv", 0) or 0) == int(lv)
                        and (slot.get("id") or 0) <= 0):
                    slot["selectIds"] = select_ids
                    if "resetCount" in reply:
                        slot["resetCount"] = reply["resetCount"]
        return reply

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
        """Set the equip CONFIG for a pawn type (GAME_HD_ChangeConfigPawnEquip).

        This is the default applied to pawns drilled AFTER it — existing pawns keep
        their gear. Use ``change_pawn_attr(..., sync_equip=1)`` to also equip the
        pawns already on the field."""
        return self.session.request("game/HD_ChangeConfigPawnEquip", {
            "id": int(pawn_id), "equipUid": str(equip_uid),
            "skinId": int(skin_id), "attackSpeed": int(attack_speed),
        })

    def change_pawn_attr(self, index: int, army_uid: str, pawn_uid: str,
                         equip_uid: str, *, sync_equip: int = 1,
                         skin_id: int = 0, attack_speed: int = 0) -> dict:
        """Equip an EXISTING pawn (GAME_HD_ChangePawnAttr). ``sync_equip=1`` applies
        the equip to every pawn of the same type across all non-marching armies (the
        engine's changePawnEquip mode 1), =2 to the pawn's army, =0 to just it."""
        return self.session.request("game/HD_ChangePawnAttr", {
            "index": int(index), "armyUid": str(army_uid), "uid": str(pawn_uid),
            "equipUid": str(equip_uid), "syncEquip": int(sync_equip),
            "skinId": int(skin_id), "attackSpeed": int(attack_speed),
        })

    def forge_equip(self, equip_uid: str) -> dict:
        """Forge/recast an equip (GAME_HD_ForgeEquip). Costs iron unless a free
        recast is available (only from policy). Reply carries the new equip
        attrs + iron + nextForgeFree/recastCount."""
        reply = self.session.request("game/HD_ForgeEquip", {"uid": str(equip_uid)})
        self._apply_result(reply)
        return reply

    def lock_equip_effect(self, equip_uid: str, effect: int) -> dict:
        """Lock an equip effect (GAME_HD_LockEquipEffect). Costs fixator."""
        return self.session.request("game/HD_LockEquipEffect",
                                    {"uid": str(equip_uid), "effect": int(effect)})

    # ---- army reads ----------------------------------------------------- #
    def get_player_armys(self) -> list[dict]:
        """All of the player's armies with their pawns (GAME_HD_GetPlayerArmys)."""
        reply = self.session.request("game/HD_GetPlayerArmys", {})
        return reply.get("list", []) or []

    def rename_army(self, index: int, army_uid: str, name: str) -> dict:
        """Rename an army (GAME_HD_ModifyAmryName — the game's own misspelling).

        The client enforces name length <= 12 and no newline (toast.text_len_limit_name);
        mirror that here so we never send a request the server will reject."""
        name = str(name).strip()
        if not name:
            raise ValueError("army name is empty")
        if len(name) > 12 or "\n" in name:
            raise ValueError("army name too long (>12) or has a newline: %r" % name)
        return self.session.request(
            "game/HD_ModifyAmryName",
            {"index": int(index), "armyUid": str(army_uid), "name": name})

    # ---- battle records (read-only ground truth) ------------------------ #
    def get_battle_records_list(self) -> list[dict]:
        """List the player's stored battles (GAME_HD_GetBattleRecordsList)."""
        reply = self.session.request("game/HD_GetBattleRecordsList", {})
        return reply.get("list", []) or []

    def get_battle_record(self, uid: str) -> dict:
        """Fetch one battle's full frame record (GAME_HD_GetBattleRecord)."""
        reply = self.session.request("game/HD_GetBattleRecord", {"uid": str(uid)})
        return reply.get("record", {}) or {}

    # ---- treasures (chests from occupying cells) ------------------------ #
    def open_army_treasure(self, index: int, army_uid: str) -> dict:
        """Open an army's earned treasures (GAME_HD_OpenArmyTreasure)."""
        return self.session.request("game/HD_OpenArmyTreasure",
                                    {"index": int(index), "auid": str(army_uid)})

    def claim_army_treasure(self, index: int, army_uid: str) -> dict:
        """Claim an army's opened treasures (GAME_HD_ClaimArmyTreasure)."""
        return self.session.request("game/HD_ClaimArmyTreasure",
                                    {"index": int(index), "auid": str(army_uid)})

    def open_armys_treasure(self, targets: list[dict]) -> dict:
        """Batch-open earned treasures (GAME_HD_OpenArmysTreasure).

        ``targets`` = [{"index": int, "auid": str}, ...].
        """
        return self.session.request("game/HD_OpenArmysTreasure", {"targets": targets})

    def claim_armys_treasure(self, targets: list[dict]) -> dict:
        """Batch-claim opened treasures (GAME_HD_ClaimArmysTreasure)."""
        return self.session.request("game/HD_ClaimArmysTreasure", {"targets": targets})

    # ---- formation (tank troop order) ----------------------------------- #
    def move_area_pawns(self, index: int, army_uid: str, assignment: dict) -> dict:
        """Set the grid positions of an army's pawns (GAME_HD_MoveAreaPawns).

        ``assignment`` maps pawn uid -> {"x","y"} point.
        """
        pawns = [{"uid": str(u), "point": {"x": int(p["x"]), "y": int(p["y"])}}
                 for u, p in assignment.items()]
        return self.session.request("game/HD_MoveAreaPawns",
                                    {"index": int(index), "armyUid": str(army_uid), "pawns": pawns})

    def exchange_pawn_army(self, index: int, army_uid: str, uid1: str, uid2: str,
                           army_uid2: str | None = None) -> dict:
        """Swap two pawns' slots (GAME_HD_ExchangePawnArmy).

        Within one army (default) this reorders ``army.pawns`` — the tank
        troop-order lever. Pass ``army_uid2`` to swap across two armies.
        """
        return self.session.request("game/HD_ExchangePawnArmy", {
            "index": int(index), "armyUid1": str(army_uid), "uid1": str(uid1),
            "armyUid2": str(army_uid2 or army_uid), "uid2": str(uid2),
        })

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

    def cure_injury_pawn(self, index: int, army_uid: str, army_name: str,
                         pawn_uid: str) -> dict:
        """Revive a dead pawn into an army at a city (GAME_HD_CureInjuryPawn).

        ``army_uid`` empty + ``army_name`` set creates a new army; otherwise the
        revived pawn joins that army (must be stationed at ``index``). Costs
        resources + a curing-queue slot + time. Optimistically drops the pawn
        from the local ``injuryPawns`` so it isn't retried before the next sync.
        """
        reply = self.session.request("game/HD_CureInjuryPawn", {
            "index": int(index), "armyUid": str(army_uid),
            "armyName": str(army_name), "pawnUid": str(pawn_uid),
        })
        self._apply_result(reply)
        player = self._player()
        inj = player.get("injuryPawns")
        if isinstance(inj, list):
            player["injuryPawns"] = [p for p in inj if str(p.get("uid")) != str(pawn_uid)]
        return reply

    def change_pawn_army(self, index: int, army_uid: str, pawn_uid: str,
                         new_army_uid: str = "", *, is_new_create: bool = False,
                         army_name: str = "", only_change: bool = True) -> dict:
        """Move a pawn to another army (GAME_HD_ChangePawnArmy).

        ``is_new_create`` creates a brand-new army for the pawn (agent's leveling
        army); otherwise it moves into ``new_army_uid``.

        Create path mirrors the verified sibling APIs (``DrillPawn``,
        ``CureInjuryPawn``) which create with an EMPTY target + ``armyName``: we
        omit ``newArmyUid`` entirely when creating, because sending
        ``newArmyUid=""`` made the server validate a non-existent army first and
        reject with ecode.500011 ("Đội quân không tồn tại")."""
        params = {"index": int(index), "armyUid": str(army_uid), "uid": str(pawn_uid)}
        if is_new_create:
            params["isNewCreate"] = True
            if army_name:
                params["armyName"] = str(army_name)
        else:
            params["newArmyUid"] = str(new_army_uid)
            params["onlyChangeArmy"] = bool(only_change)
        reply = self.session.request("game/HD_ChangePawnArmy", params)
        self._apply_result(reply)
        return reply

    def dismiss_army(self, index: int, army_uid: str, pawn_id: int = 0) -> dict:
        """Dismiss an army (GAME_HD_DismissArmy). ``pawn_id`` 0 = whole army."""
        return self.session.request("game/HD_DismissArmy",
                                    {"index": int(index), "armyUid": str(army_uid), "id": int(pawn_id)})

    def dismiss_pawn(self, index: int, army_uid: str, pawn_uid: str) -> dict:
        """Dismiss a SINGLE pawn by uid (GAME_HD_DismissPawn) — the normal way to drop
        individual soldiers (returns a small resource refund). An army that reaches 0
        pawns is auto-removed by the server."""
        return self.session.request("game/HD_DismissPawn",
                                    {"index": int(index), "armyUid": str(army_uid), "uid": str(pawn_uid)})

    def pawn_lving(self, index: int, army_uid: str, pawn_uid: str) -> dict:
        """Normal (exp-book) pawn level-up (GAME_HD_PawnLving). Queued/timed; locks
        the army (LVING). Reply carries updated queues + army."""
        reply = self.session.request("game/HD_PawnLving", {
            "index": int(index), "auid": str(army_uid), "puid": str(pawn_uid)})
        self._apply_result(reply)
        return reply

    def move_cell_army(
        self,
        armies: list[dict],
        target: int,
        *,
        same_speed: bool = False,
    ) -> dict:
        """March ``armies`` to ``target`` without attacking (GAME_HD_MoveCellArmy).

        Used to route wounded armies to a fort/city to heal. ``armies`` are
        AreaArmyInfo dicts (need ``index`` and ``uid``).
        """
        indexs = [int(a["index"]) for a in armies]
        uids = [str(a["uid"]) for a in armies]
        reply = self.session.request("game/HD_MoveCellArmy", {
            "indexs": indexs, "uids": uids, "target": int(target),
            "isSameSpeed": bool(same_speed),
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
