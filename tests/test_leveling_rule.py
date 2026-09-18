from types import SimpleNamespace

from nta_agent.execution.heuristics import Leveling
from nta_agent.execution.leveling import LEVEL_ARMY_NAME
from nta_agent.state.schema import GameState, User

MAIN = 100 * 600 + 100


def _state(exp_book=5, queues=None):
    st = GameState(source="api")
    st.user = User(uid="me")
    st.main_city_index = MAIN
    st.resources.exp_book = exp_book
    st.raw = {"player": {"pawnLvingQueues": queues}}
    return st


def _army(uid, pawns, index=MAIN, name=""):
    return {"uid": uid, "index": index, "name": name,
            "pawns": [{"uid": u, "id": 3101, "lv": lv} for u, lv in pawns]}


class FakeActions:
    def __init__(self, armies):
        self._armies = armies
        self.calls = []

    def main_city_index(self):
        return MAIN

    def get_player_armys(self):
        return self._armies

    def pawn_lving(self, index, army_uid, pawn_uid):
        self.calls.append(("level", army_uid, pawn_uid)); return {}

    def exchange_pawn_army(self, index, army_uid, uid1, uid2, army_uid2=None):
        self.calls.append(("swap", army_uid, uid1, uid2, army_uid2)); return {}

    def change_pawn_army(self, index, army_uid, pawn_uid, new_army_uid="", **kw):
        self.calls.append(("pull", army_uid, pawn_uid, new_army_uid,
                           kw.get("is_new_create", False))); return {}

    def dismiss_army(self, index, army_uid, pawn_id=0):
        self.calls.append(("dismiss", army_uid)); return {}


def _prof(group=("F1",), enabled=True, target_lv=10, max_leveling=1):
    return SimpleNamespace(army={"group": list(group), "presets": {}, "active": ""},
                           leveling={"enabled": enabled, "target_lv": target_lv,
                                     "max_leveling": max_leveling})


def test_inert_when_disabled():
    acts = FakeActions([_army("F1", [("a", 3)])])
    assert Leveling(profile=_prof(enabled=False)).applies(_state(), acts) is False


def test_inert_without_farm_group():
    acts = FakeActions([_army("F1", [("a", 3)])])
    assert Leveling(profile=_prof(group=())).applies(_state(), acts) is False


def test_pull_creates_leveling_army():
    acts = FakeActions([_army("F1", [("a", 3), ("b", 12)])])
    rule = Leveling(profile=_prof())
    assert rule.applies(_state(), acts) is True
    rule.act(acts)
    assert acts.calls == [("pull", "F1", "a", "", True)]  # isNewCreate


def test_levels_then_swaps():
    # leveling army exists with a ready pawn + farm has a low pawn -> swap first
    farm = _army("F1", [("f_low", 4)])
    lv = _army("L", [("ready", 10)], name=LEVEL_ARMY_NAME)
    acts = FakeActions([farm, lv])
    rule = Leveling(profile=_prof())
    assert rule.applies(_state(), acts) is True
    rule.act(acts)
    assert acts.calls == [("swap", "F1", "f_low", "ready", "L")]


def test_no_op_when_farm_away():
    acts = FakeActions([_army("F1", [("a", 3)], index=999)])
    rule = Leveling(profile=_prof())
    # farm not home -> no pull/swap; no leveling army -> nothing
    assert rule.applies(_state(exp_book=0), acts) is False
