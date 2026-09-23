"""Capture detection + hostile incoming-march filter (pure)."""
from types import SimpleNamespace

from nta_agent.execution.alerts import capture_info, hostile_marches

ME = "57696053"
MAIN = 544 * 600 + 79          # 2x2 city block (79..80, 544..545)


def _state(player):
    return SimpleNamespace(raw={"player": player}, user=SimpleNamespace(uid=ME),
                           main_city_index=MAIN)


def test_capture_info_detected_from_player():
    st = _state({"captureInfo": {"uid": "36781907", "time": 1790165646776}})
    assert capture_info(st) == {"uid": "36781907", "time": 1790165646776}


def test_capture_info_none_when_free():
    assert capture_info(_state({})) is None
    assert capture_info(_state({"captureInfo": {"uid": ""}})) is None   # cleared
    assert capture_info(SimpleNamespace(raw=None)) is None


def _m(uid, owner, target, target_uid="", is_city=False, surplus=60000):
    return {"uid": uid, "owner": owner, "armyName": "編隊9", "startIndex": target + 600 * 9,
            "targetIndex": target, "targetUid": target_uid, "targetIsCity": is_city,
            "surplusTime": surplus, "_rx": 1000.0}


def test_hostile_marches_flags_enemy_heading_to_our_city_and_cells():
    owned = {MAIN + 2, MAIN + 3}
    marches = {
        "a": _m("a", "36781907", MAIN, is_city=True),           # enemy -> our main city
        "b": _m("b", "36781907", MAIN + 1),                      # enemy -> main-city block cell
        "c": _m("c", "36781907", MAIN + 2),                      # enemy -> an owned cell
        "d": _m("d", "999", 12345, target_uid=ME),               # enemy -> cell server says is ours
        "e": _m("e", ME, MAIN + 3),                              # OUR own march -> ignore
        "f": _m("f", "36781907", 555555),                        # enemy elsewhere -> ignore
    }
    got = hostile_marches(marches, ME, owned, MAIN, now=1030.0)
    assert {h["uid"] for h in got} == {"a", "b", "c", "d"}
    city = next(h for h in got if h["uid"] == "a")
    assert city["target_is_main"] is True
    assert city["eta_s"] == 30.0            # 60s surplus, received 30s ago
    assert city["target_xy"] == [79, 544]
    # main-city strikes sort first (most dangerous), then soonest arrival
    assert got[0]["target_is_main"] is True


def test_hostile_marches_empty():
    assert hostile_marches({}, ME, set(), MAIN) == []
