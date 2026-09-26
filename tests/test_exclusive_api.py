"""Exclusive equipment: game API wrappers + smelt notify."""
from __future__ import annotations

from nta_agent.execution import Actions
from tests.test_actions import FakeSession, _state_with_main_city


def _acts(route, reply):
    st = _state_with_main_city(1)
    s = FakeSession(state=st, replies={route: reply})
    return Actions(s), s, st


def test_world_random_info_flattens_the_per_match_pools():
    acts, s, _ = _acts("game/HD_GetWorldRandomInfo", {
        "exclusiveMap": {6101: {"arr": [21, 3, 8]}, "6102": {"arr": [5]}},
        "pawnCostMap": {3305: 40}})
    info = acts.get_world_random_info()
    assert info == {"exclusive": {6101: [21, 3, 8], 6102: [5]}, "pawn_cost": {3305: 40}}
    assert s.calls == [("game/HD_GetWorldRandomInfo", {})]


def test_smelting_sends_main_uid_and_vice_ids_and_marks_busy():
    acts, s, st = _acts("game/HD_SmeltingEquip", {
        "currSmeltEquip": {"uid": "6101_10", "viceIds": [6005], "needTime": 60000}, "fixator": 3})
    acts.smelting_equip("6101_10", [6005])
    assert s.calls == [("game/HD_SmeltingEquip", {"mainUid": "6101_10", "viceIds": [6005]})]
    assert st.raw["player"]["currSmeltEquip"]["uid"] == "6101_10"


def test_restore_smelt_sends_main_uid_and_replaces_the_equip():
    acts, s, st = _acts("game/HD_RestoreSmeltEquip",
                        {"equip": {"uid": "6101_10", "attrs": [{"attr": [2, 21, 5, 0]}]}})
    st.raw["player"]["equips"] = [{"uid": "6101_10", "attrs": [{"attr": [2, 3, 9, 0, 6005]}]}]
    acts.restore_smelt_equip("6101_10")
    assert s.calls == [("game/HD_RestoreSmeltEquip", {"mainUid": "6101_10"})]
    assert st.raw["player"]["equips"] == [{"uid": "6101_10", "attrs": [{"attr": [2, 21, 5, 0]}]}]


def test_smelt_equip_ret_notify_clears_busy_and_upserts():
    from nta_agent.state import apply_notify, from_entry_rst
    st = from_entry_rst({"player": {"uid": "1",
        "equips": [{"uid": "6101_10", "attrs": [{"attr": [2, 21, 5, 0]}]}],
        "currSmeltEquip": {"uid": "6101_10"}}})
    apply_notify(st, {"list": [{"type": 64, "data_64": {
        "uid": "6101_10", "attrs": [{"attr": [2, 21, 5, 0]}, {"attr": [2, 3, 150, 20, 6005]}]}}]})
    p = st.raw["player"]
    assert not p.get("currSmeltEquip")
    assert len(p["equips"]) == 1 and len(p["equips"][0]["attrs"]) == 2


def test_lock_marks_the_equip_locked_in_state():
    # the server replies data=null; without mirroring lockEffect the Forge rule would
    # see "not locked" next tick and send the lock again forever, never recasting
    acts, s, st = _acts("game/HD_LockEquipEffect", {})
    st.raw["player"]["equips"] = [{"uid": "6117_10", "attrs": [], "lockEffect": 0}]
    acts.lock_equip_effect("6117_10", 9)
    assert s.calls == [("game/HD_LockEquipEffect", {"uid": "6117_10", "effect": 9})]
    assert st.raw["player"]["equips"][0]["lockEffect"] == 9
