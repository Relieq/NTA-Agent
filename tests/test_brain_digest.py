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


def test_digest_includes_presets_active_notes():
    from nta_agent.execution.profile import load_profile
    p = load_profile("none")
    p.army["presets"]["turtle"] = {"group": ["A"]}
    p.army["active"] = "turtle"
    p.notes = ["early: timber"]
    st = SimpleNamespace(main_city_index=1,
                         resources=SimpleNamespace(**{k: 0 for k in
                             ("cereal", "timber", "stone", "iron", "gold", "stamina",
                              "exp_book", "up_scroll", "fixator")}),
                         raw={})
    d = digest(st, p, [])
    assert "turtle" in d["profile"]["army"]["presets"]
    assert d["profile"]["army"]["active"] == "turtle"
    assert d["notes"] == ["early: timber"]


def test_digest_includes_build():
    from nta_agent.execution.profile import load_profile
    p = load_profile("none")
    p.build["order"] = [2002]
    st = SimpleNamespace(main_city_index=1,
                         resources=SimpleNamespace(**{k: 0 for k in
                             ("cereal", "timber", "stone", "iron", "gold", "stamina",
                              "exp_book", "up_scroll", "fixator")}),
                         raw={})
    assert digest(st, p, [])["profile"]["build"]["order"] == [2002]


def test_digest_includes_injured_and_territory():
    st = SimpleNamespace(
        main_city_index=7,
        resources=SimpleNamespace(cereal=1, timber=1, stone=1, iron=0, gold=0,
                                  stamina=0, exp_book=0, up_scroll=0, fixator=0),
        raw={"player": {"injuryPawns": [{"uid": "d1"}, {"uid": "d2"}]}})
    terr = {"owned": 23, "enemy_cells": 100, "nearest_enemy_dist": 4}
    d = digest(st, load_profile("none"), [], territory=terr)
    assert d["injured"] == 2
    assert d["territory"]["nearest_enemy_dist"] == 4
    assert "revive" in d["profile"]


def test_digest_includes_pending_decisions():
    st = SimpleNamespace(main_city_index=7,
        resources=SimpleNamespace(cereal=1, timber=1, stone=1, iron=0, gold=0,
                                  stamina=0, exp_book=0, up_scroll=0, fixator=0), raw={})
    decisions = [{"track": "pawn", "lv": 3,
                  "options": [{"id": 6001, "name": "Cung"}, {"id": 6002, "name": "Thương"}]}]
    d = digest(st, load_profile("none"), [], decisions=decisions)
    assert d["decisions"][0]["track"] == "pawn"
    assert d["decisions"][0]["options"][0]["name"] == "Cung"
