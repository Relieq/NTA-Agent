from types import SimpleNamespace

from nta_agent.execution.heuristics import Leveling
from nta_agent.state.schema import GameState, User

MAIN = 100 * 600 + 100


def _state(exp_book=5, queues=None):
    st = GameState(source="api")
    st.user = User(uid="me")
    st.main_city_index = MAIN
    st.resources.exp_book = exp_book
    st.raw = {"player": {"pawnLvingQueues": queues}}
    return st


def _army(uid, index, pawns):
    return {"uid": uid, "index": index, "pawns": [{"uid": u, "id": 3101, "lv": lv} for u, lv in pawns]}


class FakeActions:
    def __init__(self, armies):
        self._armies = armies
        self.calls = []

    def main_city_index(self):
        return MAIN

    def get_player_armys(self):
        return self._armies

    def pawn_lving(self, index, army_uid, pawn_uid):
        self.calls.append(("level", index, army_uid, pawn_uid)); return {}

    def exchange_pawn_army(self, index, army_uid, uid1, uid2, army_uid2=None):
        self.calls.append(("swap", army_uid, uid1, uid2, army_uid2)); return {}


def _prof(**kw):
    lv = {"enabled": True, "target_lv": 10, "army_uid": "L", "farm_uid": "F"}
    lv.update(kw)
    return SimpleNamespace(leveling=lv)


def test_inert_when_disabled():
    acts = FakeActions([_army("L", MAIN, [("a", 3)]), _army("F", MAIN, [("f", 3)])])
    rule = Leveling(profile=_prof(enabled=False))
    assert rule.applies(_state(), acts) is False


def test_levels_lowest_pawn_in_leveling_army():
    acts = FakeActions([_army("L", MAIN, [("a", 3), ("b", 7)]), _army("F", MAIN, [("f", 10)])])
    rule = Leveling(profile=_prof())
    assert rule.applies(_state(exp_book=5), acts) is True
    rule.act(acts)
    assert acts.calls == [("level", MAIN, "L", "a")]


def test_swaps_when_farm_home():
    acts = FakeActions([_army("L", MAIN, [("ready", 10)]), _army("F", MAIN, [("f_low", 4)])])
    rule = Leveling(profile=_prof())
    assert rule.applies(_state(), acts) is True
    rule.act(acts)
    assert acts.calls == [("swap", "F", "f_low", "ready", "L")]


def test_skips_pawn_already_in_queue():
    acts = FakeActions([_army("L", MAIN, [("a", 3)]), _army("F", MAIN, [("f", 10)])])
    rule = Leveling(profile=_prof())
    q = {"pawnUIDMap": {"a": 1}}
    assert rule.applies(_state(queues=q), acts) is False  # only pawn is queued


def test_inert_when_armies_missing():
    acts = FakeActions([_army("X", MAIN, [("a", 3)])])
    rule = Leveling(profile=_prof())
    assert rule.applies(_state(), acts) is False


def test_profile_roundtrip_leveling(tmp_path):
    from nta_agent.execution.profile import load_profile, save_profile
    p = load_profile("none")
    p.leveling["enabled"] = True
    p.leveling["target_lv"] = 8
    path = tmp_path / "p.json"
    save_profile(p, path)
    assert load_profile(path).leveling == {"enabled": True, "target_lv": 8,
                                           "army_uid": "", "farm_uid": ""}
