from nta_agent.execution.predictors.sim_input import build_forecast_input
from nta_agent.state.schema import GameState


def test_forecast_input_preserves_army_order_and_marchtime():
    st = GameState(source="api")
    st.raw = {}
    st.user.uid = "57696053"
    armies = [
        {"uid": "cung", "name": "Cung", "index": 1, "marchTime": 0,
         "pawns": [{"uid": "c1", "id": 3305, "lv": 1}]},
        {"uid": "tank", "name": "Tank", "index": 1, "marchTime": 5000,
         "pawns": [{"uid": "t1", "id": 3101, "lv": 1}]},
    ]
    out = build_forecast_input(st, armies, target_index=109725, land_id=0, distance=1)
    assert [a["uid"] for a in out["armies"]] == ["cung", "tank"]
    assert out["armies"][1]["marchTime"] == 5000
    assert out["armies"][0]["pawns"][0]["id"] == 3305
    assert out["targetCellIndex"] == 109725


def test_forecast_input_passes_pawn_point_when_present():
    st = GameState(source="api"); st.raw = {}; st.user.uid = "1"
    armies = [{"uid": "a", "index": 1, "marchTime": 0,
               "pawns": [{"uid": "p1", "id": 3101, "lv": 1, "point": {"x": 6, "y": 7}}]}]
    out = build_forecast_input(st, armies, target_index=9, land_id=0, distance=1)
    assert out["armies"][0]["pawns"][0]["point"] == {"x": 6, "y": 7}


def test_forecast_injects_config_equip_onto_pawns():
    """A pawn's own equip is empty; the sim must apply the per-type config loadout
    (configPawnMap -> equips) so the engine sees the pawn's real strength."""
    st = GameState(source="api"); st.user.uid = "1"
    st.raw = {"player": {
        "configPawnMap": {"3101": {"equipUid": "6005_1"}},
        "equips": [{"uid": "6005_1", "attrs": [{"attr": [2, 3, 178, 25]}]}],  # no `id` field
    }}
    armies = [{"uid": "a", "index": 1, "marchTime": 0,
               "pawns": [{"uid": "p1", "id": 3101, "lv": 1, "equip": {}}]}]
    out = build_forecast_input(st, armies, target_index=9, land_id=0, distance=1)
    eq = out["armies"][0]["pawns"][0]["equip"]
    assert eq == {"uid": "6005_1", "id": 6005, "attrs": [{"attr": [2, 3, 178, 25]}]}


def test_forecast_prefers_pawn_own_equip_over_config():
    st = GameState(source="api"); st.user.uid = "1"
    st.raw = {"player": {"configPawnMap": {"3101": {"equipUid": "6005_1"}},
                         "equips": [{"uid": "6005_1", "attrs": []}]}}
    own = {"uid": "9999_1", "id": 9999, "attrs": []}
    armies = [{"uid": "a", "index": 1, "marchTime": 0,
               "pawns": [{"uid": "p1", "id": 3101, "lv": 1, "equip": own}]}]
    out = build_forecast_input(st, armies, target_index=9, land_id=0, distance=1)
    assert out["armies"][0]["pawns"][0]["equip"] == own
