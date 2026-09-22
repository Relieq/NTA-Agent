from types import SimpleNamespace

import pytest

from nta_agent.execution.heuristics import ReviveInjured
from nta_agent.state.schema import GameState, User

MAIN = 100 * 600 + 100


def _state(injured, cereal=1000):
    st = GameState(source="api")
    st.user = User(uid="me")
    st.main_city_index = MAIN
    st.resources.cereal = cereal
    st.raw = {"player": {"mainCityIndex": MAIN, "injuryPawns": injured}}
    return st


class FakeActions:
    def __init__(self, armies, fail=False):
        self._armies = armies
        self.fail = fail
        self.cured = []

    def main_city_index(self):
        return MAIN

    def get_player_armys(self):
        return self._armies

    def cure_injury_pawn(self, index, army_uid, army_name, pawn_uid):
        if self.fail:
            raise RuntimeError("game/HD_CureInjuryPawn: ecode.500019")
        self.cured.append((index, army_uid, army_name, pawn_uid))
        return {}


def test_revives_into_home_army_with_room():
    st = _state([{"uid": "d1", "id": 3101, "lv": 1}])
    acts = FakeActions([{"uid": "A", "name": "D1", "index": MAIN, "pawns": [{}] * 3}])
    rule = ReviveInjured()
    assert rule.applies(st, acts) is True
    rule.act(acts)
    assert acts.cured == [(MAIN, "A", "D1", "d1")]


def test_creates_new_army_when_all_full():
    st = _state([{"uid": "d1", "id": 3101, "lv": 1}])
    acts = FakeActions([{"uid": "A", "name": "D1", "index": MAIN, "pawns": [{}] * 9}])
    rule = ReviveInjured()
    rule.applies(st, acts)
    rule.act(acts)
    assert acts.cured == [(MAIN, "", "Cứu Hộ", "d1")]


def test_skips_when_no_injured():
    st = _state([])
    acts = FakeActions([{"uid": "A", "name": "D1", "index": MAIN, "pawns": []}])
    assert ReviveInjured().applies(st, acts) is False


def test_skips_below_resource_floor():
    st = _state([{"uid": "d1", "id": 3101, "lv": 1}], cereal=50)
    acts = FakeActions([{"uid": "A", "name": "D1", "index": MAIN, "pawns": []}])
    assert ReviveInjured(min_cereal=200).applies(st, acts) is False


def test_disabled_via_profile():
    st = _state([{"uid": "d1", "id": 3101, "lv": 1}])
    acts = FakeActions([{"uid": "A", "name": "D1", "index": MAIN, "pawns": []}])

    prof = SimpleNamespace(revive={"enabled": False})
    assert ReviveInjured(profile=prof).applies(st, acts) is False


def test_ecode_sets_cooldown_and_reraises():
    st = _state([{"uid": "d1", "id": 3101, "lv": 1}])
    acts = FakeActions([{"uid": "A", "name": "D1", "index": MAIN, "pawns": []}], fail=True)
    rule = ReviveInjured()
    rule.applies(st, acts)
    with pytest.raises(RuntimeError):
        rule.act(acts)
    assert rule._cooldown == rule.fail_cooldown
    # next tick is gated by cooldown
    assert rule.applies(st, acts) is False


def test_caps_per_tick():
    st = _state([{"uid": "d1", "id": 3101, "lv": 2}, {"uid": "d2", "id": 3101, "lv": 1}])
    acts = FakeActions([{"uid": "A", "name": "D1", "index": MAIN, "pawns": [{}]}])
    rule = ReviveInjured(max_per_tick=1)
    rule.applies(st, acts)
    rule.act(acts)
    assert len(acts.cured) == 1 and acts.cured[0][3] == "d1"  # highest lv first


def test_500054_army_cap_backs_off_quietly():
    """When all city armies are full and the army cap is reached, revive can't
    create a new army (500054) — back off quietly (longer), don't re-raise/spam."""
    st = _state([{"uid": "d1", "id": 3101, "lv": 1}])

    class CapActions(FakeActions):
        def cure_injury_pawn(self, index, army_uid, army_name, pawn_uid):
            raise RuntimeError("game/HD_CureInjuryPawn: ecode.500054")

    acts = CapActions([{"uid": "A", "name": "D1", "index": MAIN, "pawns": [{}] * 9}])
    rule = ReviveInjured()
    assert rule.applies(st, acts) is True
    rule.act(acts)                       # must NOT raise
    assert rule._cooldown == rule.full_cooldown
