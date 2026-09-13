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
