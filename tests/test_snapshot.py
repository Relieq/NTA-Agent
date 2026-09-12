import json

from nta_agent.runtime.snapshot import state_to_dict, write_snapshot
from nta_agent.state.schema import Building, GameState, User


def _state():
    st = GameState(source="api")
    st.user = User(uid="7")
    st.main_city_index = 109726
    st.resources.cereal = 500
    st.resources.timber = 20
    st.builds = [Building(index=109726, id=2001, lv=2, uid="b1")]
    st.granary_cap = 1000
    st.raw = {"player": {"guideTasks": [{"id": 1}], "otherTasks": [],
                          "todayTasks": [{"id": 2}, {"id": 3}],
                          "pawnSlots": {"0": {"id": 3101}}}}
    return st


def test_state_to_dict_shape_and_json_safe():
    d = state_to_dict(_state())
    assert d["main_city_index"] == 109726
    assert d["resources"]["cereal"] == 500
    assert d["builds"] == [{"index": 109726, "id": 2001, "lv": 2, "uid": "b1"}]
    assert d["granary_cap"] == 1000
    assert d["player"]["guide_tasks"] == 1 and d["player"]["today_tasks"] == 2
    assert d["player"]["pawn_slots"] == [3101]
    assert "raw" not in d
    json.dumps(d)  # must be serializable


def test_write_snapshot_atomic(tmp_path):
    p = tmp_path / "sub" / "state.json"
    write_snapshot(_state(), p)
    assert json.loads(p.read_text())["main_city_index"] == 109726
    assert not (tmp_path / "sub" / "state.json.tmp").exists()
