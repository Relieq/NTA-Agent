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


def test_pawn_hp_map_normalized_to_list():
    """Live pawns carry hp as a protobuf map {0:cur,1:max}; list() on it returns
    the KEYS ([0,1]) and put every pawn into the sim at 1 hp -> always lost."""
    from nta_agent.execution.predictors.sim_input import _pawn
    assert _pawn({"id": 3101, "lv": 1, "hp": {0: 135, 1: 135}})["hp"] == [135, 135]
    assert _pawn({"id": 3101, "lv": 1, "hp": {"0": 100, "1": 135}})["hp"] == [100, 135]
    assert _pawn({"id": 3101, "lv": 1, "hp": [120, 135]})["hp"] == [120, 135]
    assert _pawn({"id": 3101, "lv": 1})["hp"] is None  # enemy w/o hp -> engine computes


def test_treasures_always_carry_a_rewards_list():
    """The engine's fromSvrTreasureInfo does treasure.rewards.map(...): protobuf omits
    an empty repeated field, so a live {uid,id} treasure crashed the forecast."""
    from nta_agent.execution.predictors.sim_input import _pawn
    p = _pawn({"id": 3305, "lv": 1, "hp": {0: 55, 1: 55},
               "treasures": [{"uid": "t1", "id": 401}, {"uid": "t2", "id": 402, "rewards": [{"id": 1}]}]})
    assert p["treasures"] == [{"uid": "t1", "id": 401, "rewards": []},
                              {"uid": "t2", "id": 402, "rewards": [{"id": 1}]}]


def test_hp_with_only_current_uses_it_as_max():
    from nta_agent.execution.predictors.sim_input import _hp_list
    assert _hp_list({"0": 65}) == [65, 65]


def test_enemy_conf_is_normalised_points_hp_treasures():
    from types import SimpleNamespace

    from nta_agent.execution.predictors.sim_input import build_forecast_input
    st = SimpleNamespace(user=SimpleNamespace(uid="1"), raw={}, main_city_index=0)
    ec = {"armys": [{"uid": "npc", "pawns": [
        {"id": 4111, "point": {"x": 3}, "hp": {"0": 498}},
        {"id": 3201, "point": {"y": 9}, "hp": {"0": 5, "1": 9}, "treasures": [{"uid": "t", "id": 1}]}]}],
        "hp": [6, 6]}
    out = build_forecast_input(st, [], target_index=1, land_id=0, distance=1, enemy_army_conf=ec)
    p0, p1 = out["enemyArmyConf"]["armys"][0]["pawns"]
    assert p0["point"] == {"x": 3, "y": 0} and p0["hp"] == [498, 498]
    assert p1["point"] == {"x": 0, "y": 9} and p1["hp"] == [5, 9]
    assert p1["treasures"] == [{"uid": "t", "id": 1, "rewards": []}]
