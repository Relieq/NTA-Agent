from types import SimpleNamespace

from nta_agent.brain.digest import digest
from nta_agent.execution.profile import load_profile


def test_digest_is_compact_and_has_armies_and_profile():
    st = SimpleNamespace(
        main_city_index=7,
        resources=SimpleNamespace(cereal=10, timber=20, stone=30, iron=0, gold=1,
                                  stamina=50, exp_book=0, up_scroll=0, fixator=0),
        raw={})
    armies = [{"uid": "A", "name": "Đội 1", "pawns": [{"id": 3101}, {"id": 3101}, {"id": 3305}]}]
    d = digest(st, load_profile("none"), armies)
    assert d["main_city_index"] == 7
    assert d["resources"]["cereal"] == 10
    assert d["armies"][0]["uid"] == "A"
    assert d["armies"][0]["composition"] == {"3101": 2, "3305": 1}
    assert "occupy" in d["profile"] and "army" in d["profile"]
