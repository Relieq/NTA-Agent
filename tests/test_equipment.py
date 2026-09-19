from nta_agent.execution.equipment import pawn_equipment
from nta_agent.state.schema import GameState


class FakeConfig:
    def __init__(self):
        self._t = {
            "pawnText": {"name_3101": {"vi": "Lính Trường Thương"}},
            "equipText": {"name_6001": {"vi": "Kiếm Sắt"}, "name_6003": {"vi": "Đao Hồi Máu"},
                          "effect_6001": {"vi": "<color=#fff>+10% công</c>"}},
            "equipBase": {6001: {"id": 6001, "exclusive_pawn": ""},
                          6003: {"id": 6003, "exclusive_pawn": "3999"}},  # exclusive to another pawn
        }

    def table(self, name):
        return self._t.get(name, {})


def _state():
    st = GameState(source="api")
    st.raw = {"player": {
        "configPawnMap": {"3101": {"equipUid": "e1", "skinId": 0, "attackSpeed": 6}},
        "equips": [{"uid": "e1", "id": 6001}, {"uid": "e2", "id": 6003}],
    }}
    return st


def test_pawn_equipment_row_and_compat_filtering():
    rows = pawn_equipment(_state(), FakeConfig())
    assert len(rows) == 1
    r = rows[0]
    assert r["pawn_id"] == 3101 and r["pawn_name"] == "Lính Trường Thương"
    assert r["current_equip_uid"] == "e1" and r["current_equip_name"] == "Kiếm Sắt"
    assert r["current_equip_desc"] == "+10% công"  # effect, markup stripped
    assert r["skin_id"] == 0 and r["attack_speed"] == 6
    # e1 (6001, general) is an option with its effect; e2 (6003, excl to 3999) filtered
    assert r["options"] == [{"uid": "e1", "id": 6001, "name": "Kiếm Sắt", "desc": "+10% công"}]


def test_unknown_names_fall_back():
    st = GameState(source="api")
    st.raw = {"player": {"configPawnMap": {"3102": {"equipUid": "", "skinId": 0, "attackSpeed": 0}},
                          "equips": [{"uid": "x", "id": 9999}]}}
    rows = pawn_equipment(st, FakeConfig())
    assert rows[0]["pawn_name"] == "#3102"
    assert rows[0]["current_equip_uid"] == "" and rows[0]["current_equip_name"] == ""
    assert rows[0]["current_equip_desc"] == ""
    # unknown equip -> compatible, no effect text
    assert rows[0]["options"] == [{"uid": "x", "id": 9999, "name": "#9999", "desc": ""}]


def test_lists_unlocked_pawn_type_without_config():
    """pawnSlots with a chosen id but no configPawnMap -> still shown so it can be
    geared, and an equip whose live shape lacks `id` derives it from the uid."""
    st = GameState(source="api")
    st.raw = {"player": {
        "pawnSlots": {"1": {"id": 3101, "lv": 1},
                      "2": {"selectIds": [3301, 3405], "lv": 2}},  # pending -> no id
        "configPawnMap": None,
        "equips": [{"uid": "6001_1", "attrs": [{"attr": [0, 2, 4]}]}],  # no `id` field
    }}
    rows = pawn_equipment(st, FakeConfig())
    assert [r["pawn_id"] for r in rows] == [3101]           # only the chosen slot
    r = rows[0]
    assert r["current_equip_uid"] == "" and r["current_equip_name"] == ""
    # equip id derived from uid "6001_1" -> 6001 (common) offered as an option
    assert r["options"] == [{"uid": "6001_1", "id": 6001, "name": "Kiếm Sắt", "desc": "+10% công"}]
