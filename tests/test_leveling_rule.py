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


def test_inplace_levels_farm_pawn_when_no_buffer():
    # No leveling army can be created (ChangePawnArmy -> ecode.500011), so the
    # lowest under-target farm pawn is leveled IN PLACE in its own army.
    acts = FakeActions([_army("F1", [("a", 3), ("b", 12)])])
    rule = Leveling(profile=_prof())
    assert rule.applies(_state(), acts) is True
    rule.act(acts)
    assert acts.calls == [("level", "F1", "a")]   # PawnLving on the farm army


def test_inplace_skips_marching_farm_army():
    # a farm army that is out (state=march) can't be leveled in place
    farm = _army("F1", [("a", 3)]); farm["state"] = 1
    acts = FakeActions([farm])
    rule = Leveling(profile=_prof())
    assert rule.applies(_state(), acts) is False


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


def test_quiet_backoff_on_already_queued():
    """A 500079 (pawn already in the leveling queue — state-freshness retry) is a
    benign transient: swallow it quietly and set a cooldown, don't raise/spam."""
    class RaisingActions(FakeActions):
        def pawn_lving(self, index, army_uid, pawn_uid):
            raise RuntimeError("game/HD_PawnLving: ecode.500079")
    acts = RaisingActions([_army("F1", [("a", 3)])])
    rule = Leveling(profile=_prof())
    assert rule.applies(_state(), acts) is True
    rule.act(acts)                      # must NOT raise
    assert rule._cooldown == rule.quiet_cooldown


def test_raises_on_real_leveling_error():
    class RaisingActions(FakeActions):
        def pawn_lving(self, index, army_uid, pawn_uid):
            raise RuntimeError("game/HD_PawnLving: ecode.500033")
    acts = RaisingActions([_army("F1", [("a", 3)])])
    rule = Leveling(profile=_prof())
    assert rule.applies(_state(), acts) is True
    errored = []
    rule.on_event = lambda k, d: errored.append((k, d))
    try:
        rule.act(acts)
    except RuntimeError:
        pass
    else:
        raise AssertionError("should have raised on a real error")
    assert any(k == "leveling_error" for k, _ in errored)


def test_quiet_backoff_on_low_resources():
    """500012 (out of exp-books; a stale estimate let it try) is a benign wait,
    not an error — quiet, with the longer resource cooldown."""
    class RaisingActions(FakeActions):
        def pawn_lving(self, index, army_uid, pawn_uid):
            raise RuntimeError("game/HD_PawnLving: ecode.500012")
    acts = RaisingActions([_army("F1", [("a", 3)])])
    rule = Leveling(profile=_prof())
    assert rule.applies(_state(), acts) is True
    rule.act(acts)                       # must NOT raise
    assert rule._cooldown == rule.res_cooldown


def test_no_new_leveling_on_the_dig_group_while_a_dig_is_on():
    # live 2026-09-25: in-place leveling kept Đội 1 (the dig tank) in the drill
    # ground pawn after pawn and the dig waited 30+ min for it
    acts = FakeActions([_army("F1", [("a", 3), ("b", 12)])])
    rule = Leveling(profile=_prof())
    rule.dig_live_source = lambda: True
    assert rule.applies(_state(), acts) is False
    rule._cooldown = 0
    rule.dig_live_source = lambda: False          # dig over -> leveling resumes
    assert rule.applies(_state(), acts) is True


def test_leveling_army_keeps_leveling_during_a_dig():
    lv = _army("L", [("x", 2)], name=LEVEL_ARMY_NAME)
    acts = FakeActions([_army("F1", [("a", 3)]), lv])
    rule = Leveling(profile=_prof())
    rule.dig_live_source = lambda: True
    assert rule.applies(_state(), acts) is True
    rule.act(acts)
    assert acts.calls == [("level", "L", "x")]    # its own buffer army, not the group


def test_direct_leveling_is_inert_for_a_buffer_group():
    prof = _prof()
    prof.leveling["groups"] = [{"armies": ["F1"], "mode": "buffer", "target_lv": 10}]
    acts = FakeActions([_army("F1", [("a", 3)])])
    assert Leveling(profile=prof).applies(_state(), acts) is False


def test_direct_group_uses_its_own_armies_and_target():
    prof = _prof(group=())                       # no active formation group...
    prof.leveling["groups"] = [{"armies": ["F1"], "mode": "direct", "target_lv": 10}]
    acts = FakeActions([_army("F1", [("a", 3)])])
    rule = Leveling(profile=prof)
    assert rule.applies(_state(), acts) is True  # ...the direct group still levels
