"""Recruit rule: unlocked-pawn gating, army room / new army, affordability (fakes)."""
from dataclasses import dataclass, field

from nta_agent.execution.heuristics import Recruit
from nta_agent.state.schema import Building, GameState


@dataclass
class FakeActions:
    state: GameState
    armys: list
    calls: list = field(default_factory=list)
    def building_uid(self, bid):
        for b in self.state.builds:
            if b.id == bid: return b.uid
        return ""
    def get_area(self, index, no_record=True):
        return {"data": {"armys": self.armys}}
    def drill_pawn(self, build_uid, pawn_id, *, index=None, army_uid="", army_name=""):
        self.calls.append((build_uid, pawn_id, army_uid, army_name)); return {}


def _state(unlocked, cereal=9999):
    st = GameState(source="api"); st.main_city_index = 109726
    st.builds = [Building(index=109726, id=2004, lv=1, uid="bar")]
    st.resources.cereal = cereal
    st.raw = {"player": {"pawnSlots": {str(i+1): {"id": p, "lv": 1} for i, p in enumerate(unlocked)}}}
    return st


def test_skips_when_no_unlocked_pawn():
    r = Recruit(config=False)  # config unavailable -> affordability skipped
    assert r.applies(_state([]), FakeActions(_state([]), armys=[])) is False


def test_recruits_into_army_with_room():
    st = _state([3101])
    act = FakeActions(st, armys=[{"uid": "A", "pawns": [{}, {}], "state": None}])
    r = Recruit(config=False)
    assert r.applies(st, act) is True
    r.act(act)
    assert act.calls == [("bar", 3101, "A", "")]


def test_creates_new_army_when_all_full():
    st = _state([3101])
    full = {"uid": "A", "pawns": [{}] * 9, "state": None}
    act = FakeActions(st, armys=[full])
    r = Recruit(config=False)
    assert r.applies(st, act) is True
    r.act(act)
    assert act.calls[0][2] == "" and act.calls[0][3] == "D2"  # new army


def test_blocks_at_army_cap():
    st = _state([3101])
    armys = [{"uid": f"A{i}", "pawns": [{}] * 9, "state": None} for i in range(4)]
    r = Recruit(config=False, max_armies=4)
    assert r.applies(st, FakeActions(st, armys=armys)) is False
