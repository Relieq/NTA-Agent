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


def test_skips_locked_army():
    # an army locked by the ArmyComposer must NOT be recruited into (it drives that
    # army's composition). Without the lock it would recruit into A; with it, it won't.
    st = _state([3101])
    act = FakeActions(st, armys=[{"uid": "A", "pawns": [{}, {}], "state": None}])
    r = Recruit(config=False)
    r.locked_source = lambda: {"A"}
    r.applies(st, act)
    r.act(act)
    assert all(c[2] != "A" for c in act.calls)   # never recruits into the locked army


def test_creates_new_army_when_all_full():
    st = _state([3101])
    full = {"uid": "A", "pawns": [{}] * 9, "state": None}
    act = FakeActions(st, armys=[full])
    r = Recruit(config=False)
    assert r.applies(st, act) is True
    r.act(act)
    assert act.calls[0][2] == "" and act.calls[0][3] == "D1"  # new army (first unused name)


def test_blocks_at_army_cap():
    st = _state([3101])
    armys = [{"uid": f"A{i}", "pawns": [{}] * 9, "state": None} for i in range(4)]
    r = Recruit(config=False, max_armies=4)
    assert r.applies(st, FakeActions(st, armys=armys)) is False


@dataclass
class FailingActions(FakeActions):
    """drill_pawn raises ecode.500019 (army full) for the given army uids."""
    full_uids: set = field(default_factory=set)

    def drill_pawn(self, build_uid, pawn_id, *, index=None, army_uid="", army_name=""):
        if army_uid in self.full_uids:
            from nta_agent.io.api.client import ApiError
            raise ApiError("game/HD_DrillPawn: ecode.500019")
        self.calls.append((build_uid, pawn_id, army_uid, army_name)); return {}


def test_500019_marks_army_full_and_does_not_retry_it():
    st = _state([3101])
    # rule thinks army A (2 pawns) has room, but the server says it's full.
    act = FailingActions(st, armys=[{"uid": "A", "pawns": [{}, {}], "state": None}],
                         full_uids={"A"})
    r = Recruit(config=False)
    assert r.applies(st, act) is True          # optimistically picks A
    r.act(act)                                  # 500019 swallowed, A marked full
    assert act.calls == []                      # nothing recruited
    # next pass: A is known-full -> skip it and create a new army instead
    assert r.applies(st, act) is True
    r.act(act)
    assert act.calls == [("bar", 3101, "", "D1")]


def test_full_mark_cleared_when_army_pawn_count_changes():
    st = _state([3101])
    act = FailingActions(st, armys=[{"uid": "A", "pawns": [{}, {}], "state": None}],
                         full_uids={"A"})
    r = Recruit(config=False, max_armies=1)  # can't create new army -> only A
    assert r.applies(st, act) is True
    r.act(act)                                # A marked full at 2 pawns
    assert r.applies(st, act) is False        # A still full at 2 -> nothing to do
    # a pawn leaves A (count changes) -> stale full mark dropped, A eligible again
    act.armys[0]["pawns"] = [{}]
    assert r.applies(st, act) is True


def test_500054_stops_creating_new_armies():
    from nta_agent.io.api.client import ApiError
    st = _state([3101])

    class FullActions(FakeActions):
        def drill_pawn(self, build_uid, pawn_id, *, index=None, army_uid="", army_name=""):
            if not army_uid:  # creating a new army -> server: at army cap
                raise ApiError("game/HD_DrillPawn: ecode.500054")
            self.calls.append((build_uid, pawn_id, army_uid, army_name)); return {}

    # one full army -> rule wants to create a new one -> 500054 -> learn the cap
    act = FullActions(st, armys=[{"uid": "A", "pawns": [{}] * 9, "state": None}])
    r = Recruit(config=False)
    assert r.applies(st, act) is True
    r.act(act)                       # 500054 -> _max_army_count learned
    assert act.calls == []
    assert r.applies(st, act) is False   # won't try to create a new army again


def test_new_army_name_avoids_armies_outside_the_city():
    """Live 2026-09-25: 4 armies named 'D1' — the name was picked from the CITY's
    armies only, so a 'D1' out on the map didn't count."""
    st = _state([3101])
    full = [{"uid": f"c{i}", "name": f"D{i+2}", "pawns": [{}] * 9, "state": None} for i in range(2)]

    class Everywhere(FakeActions):
        def get_player_armys(self):
            return full + [{"uid": "far", "name": "D1", "pawns": [{}] * 9, "state": 2}]
    act = Everywhere(st, armys=full)
    r = Recruit(config=False)
    assert r.applies(st, act) is True
    r.act(act)
    assert act.calls[-1][3] == "D4"          # D1 (far away), D2, D3 (in city) are taken


def test_stands_down_while_a_strike_group_is_recruiting():
    """The composer needs the cereal + drill queue for the group (2026-09-25:
    6x ecode 500018 'recruit slots full' while the generic rule filled other armies)."""
    st = _state([3101])
    act = FakeActions(st, armys=[{"uid": "A", "pawns": [{}, {}], "state": None}])
    r = Recruit(config=False, locked_source=lambda: {"strike1"})
    assert r.applies(st, act) is False
