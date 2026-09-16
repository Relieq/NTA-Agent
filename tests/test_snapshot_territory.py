from nta_agent.runtime.snapshot import state_to_dict
from nta_agent.state.schema import GameState


def test_snapshot_includes_territory():
    st = GameState(source="api")
    st.main_city_index = 60100
    st.raw = {"player": {"mainCityIndex": 60100,
                         "fortAutoSupports": [{"index": 60110, "val": True}],
                         "armyDists": [{"index": 60100, "armys": []}]}}
    d = state_to_dict(st)
    assert d["forts"] == [{"index": 60110, "auto_support": True}]
    assert d["garrisons"] == [60100]
    assert d["map_width"] >= 1
