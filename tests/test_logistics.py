"""Tests for the army-logistics planner (dồn/kéo về/sẵn sàng) + the Logistics rule."""
from types import SimpleNamespace

from nta_agent.execution.heuristics import Logistics
from nta_agent.execution.logistics import plan_logistics, ready_armies
from nta_agent.state.schema import GameState, User


def _pawn(uid, hp):  # hp as live protobuf map {0:cur,1:max}
    return {"uid": uid, "hp": {0: hp, 1: 100}}


def _army(uid, index, n_or_hps, state=0):
    hps = n_or_hps if isinstance(n_or_hps, list) else [100] * n_or_hps
    return {"uid": uid, "index": index, "state": state,
            "pawns": [_pawn(f"{uid}p{i}", h) for i, h in enumerate(hps)]}


MAIN = 1000
FORT = 2000


def test_consolidate_moves_high_hp_into_keeper():
    # two idle armies on the same FIELD cell; keeper has 6, donor has 4 (hps vary).
    keeper = _army("K", 5555, 6)
    # donor is HEALTHY overall (wound_frac < 0.2) but pawn hp varies for ordering
    donor = _army("D", 5555, [80, 95, 90, 85])  # 4 pawns
    act = plan_logistics([keeper, donor], MAIN, [FORT], target=9)
    assert act is not None and act.kind == "consolidate"
    assert act.index == 5555 and act.to_uid == "K" and act.from_uid == "D"
    # room = 9-6 = 3 -> the 3 HIGHEST-hp donor pawns (95,90,85), leaving the 80
    assert set(act.pawn_uids) == {"Dp1", "Dp2", "Dp3"}


def test_bring_home_short_army_when_no_group():
    # single idle field army under target, no one to consolidate with -> bring home
    a = _army("A", 5555, 5)
    act = plan_logistics([a], MAIN, [FORT], target=9)
    assert act is not None and act.kind == "bring_home" and act.army["uid"] == "A"


def test_skips_fort_exclude_wounded_and_city():
    at_fort = _army("F", FORT, 4)
    excluded = _army("X", 5555, 4)
    wounded = _army("W", 5556, [5, 5, 5, 5])  # wound_frac high
    at_city = _army("C", MAIN, 4)              # Recruit handles city armies
    act = plan_logistics([at_fort, excluded, wounded, at_city], MAIN, [FORT],
                         target=9, exclude=["X"], heal_skip_frac=0.2)
    assert act is None


def test_none_when_all_full():
    a = _army("A", 5555, 9)
    b = _army("B", 5556, 9)
    assert plan_logistics([a, b], MAIN, [FORT], target=9) is None


def test_min_shortfall_respected():
    a = _army("A", 5555, 8)  # shortfall 1
    assert plan_logistics([a], MAIN, [FORT], target=9, min_shortfall=2) is None


def test_marching_army_ignored():
    a = _army("A", 5555, 4, state=1)  # MARCH
    assert plan_logistics([a], MAIN, [FORT], target=9) is None


def test_ready_armies_are_full_idle_at_city():
    full_city = _army("R", MAIN, 9)
    part_city = _army("P", MAIN, 5)
    full_field = _army("Q", 5555, 9)
    marching = _army("M", MAIN, 9, state=1)
    ready = ready_armies([full_city, part_city, full_field, marching], MAIN, target=9)
    assert [a["uid"] for a in ready] == ["R"]


# --- Logistics rule ---------------------------------------------------------- #
def _state(main):
    st = GameState(source="api")
    st.user = User(uid="me")
    st.main_city_index = main
    st.raw = {"player": {"mainCityIndex": main, "fortAutoSupports": []}}
    return st


class FakeActions:
    def __init__(self, armies, main):
        self._armies, self._main = armies, main
        self.moved, self.changed = [], []

    def get_player_armys(self):
        return self._armies

    def main_city_index(self):
        return self._main

    def move_cell_army(self, armies, target, **kw):
        self.moved.append(([a["uid"] for a in armies], target))
        return {}

    def change_pawn_army(self, index, army_uid, pawn_uid, new_army_uid, **kw):
        self.changed.append((army_uid, pawn_uid, new_army_uid))
        return {}


def _prof(**over):
    lg = {"enabled": True, "target": 9, "heal_skip_frac": 0.2, "exclude": [],
          "min_shortfall": 1, "redeploy": {}}
    lg.update(over)
    return SimpleNamespace(logistics=lg)


def test_rule_disabled_by_default():
    st = _state(MAIN)
    acts = FakeActions([_army("A", 5555, 5)], MAIN)
    rule = Logistics(check_every=0, profile=SimpleNamespace(logistics={"enabled": False}))
    assert rule.applies(st, acts) is False


def test_rule_brings_home_field_army():
    st = _state(MAIN)
    acts = FakeActions([_army("A", 5555, 5)], MAIN)
    rule = Logistics(check_every=0, profile=_prof())
    assert rule.applies(st, acts) is True
    rule.act(acts)
    assert acts.moved == [(["A"], MAIN)]


def test_rule_skips_locked_army():
    # an army the ArmyComposer owns must not be brought home / consolidated.
    st = _state(MAIN)
    acts = FakeActions([_army("A", 5555, 5)], MAIN)
    rule = Logistics(check_every=0, profile=_prof())
    rule.locked_source = lambda: {"A"}
    assert rule.applies(st, acts) is False      # A locked -> nothing to do
    assert acts.moved == []


def test_rule_consolidates_pawns():
    st = _state(MAIN)
    keeper = _army("K", 5555, 6)
    donor = _army("D", 5555, [80, 95, 90, 85])
    acts = FakeActions([keeper, donor], MAIN)
    rule = Logistics(check_every=0, profile=_prof())
    assert rule.applies(st, acts) is True
    rule.act(acts)
    assert {c[1] for c in acts.changed} == {"Dp1", "Dp2", "Dp3"}
    assert all(c[0] == "D" and c[2] == "K" for c in acts.changed)


def test_rule_redeploy_consumes_instruction():
    st = _state(MAIN)
    prof = _prof(redeploy={"R": 7777})
    acts = FakeActions([_army("R", MAIN, 9)], MAIN)
    rule = Logistics(check_every=0, profile=prof)
    assert rule.applies(st, acts) is True
    rule.act(acts)
    assert acts.moved == [(["R"], 7777)]
    assert prof.logistics["redeploy"] == {}  # one-shot consumed


def test_rule_redeploy_to_own_cell_is_dropped_not_moved():
    # brain mistake: redeploy a city army to the main city (where it already is).
    st = _state(MAIN)
    prof = _prof(redeploy={"R": MAIN})
    acts = FakeActions([_army("R", MAIN, 9)], MAIN)
    rule = Logistics(check_every=0, profile=prof)
    # no valid redeploy, no field armies -> nothing to do; bad order dropped
    assert rule.applies(st, acts) is False
    assert prof.logistics["redeploy"] == {}
    assert acts.moved == []


def test_rule_redeploy_stale_uid_dropped_then_consolidates():
    st = _state(MAIN)
    prof = _prof(redeploy={"GHOST": 7777})
    keeper = _army("K", 5555, 6)
    donor = _army("D", 5555, [80, 95, 90, 85])
    acts = FakeActions([keeper, donor], MAIN)
    rule = Logistics(check_every=0, profile=prof)
    # stale redeploy dropped, then falls through to consolidation
    assert rule.applies(st, acts) is True
    assert prof.logistics["redeploy"] == {}
    rule.act(acts)
    assert {c[1] for c in acts.changed} == {"Dp1", "Dp2", "Dp3"}


# --- brain seam -------------------------------------------------------------- #
def test_sanitize_logistics_redeploy_valid_uid_only():
    from nta_agent.brain.guard import sanitize_edits
    from nta_agent.execution.profile import load_profile
    prof = load_profile("/nonexistent")  # defaults
    edits = {"logistics": {"enabled": True, "target": 9,
                           "redeploy": {"R": 7777, "GHOST": 5, "R2": 0}}}
    clean = sanitize_edits(edits, prof, valid_army_uids=["R", "R2"])
    assert clean["logistics"]["enabled"] is True
    # GHOST dropped (unknown uid); R2 dropped (index 0 invalid); R kept
    assert clean["logistics"]["redeploy"] == {"R": 7777}


def test_apply_edits_merges_logistics():
    from nta_agent.execution.profile import apply_edits, load_profile
    prof = load_profile("/nonexistent")
    assert apply_edits(prof, {"logistics": {"enabled": True, "redeploy": {"R": 42}}})
    assert prof.logistics["enabled"] is True
    assert prof.logistics["redeploy"] == {"R": 42}


def test_digest_lists_ready_to_redeploy():
    from nta_agent.brain.digest import digest
    from nta_agent.execution.profile import load_profile
    st = _state(MAIN)
    prof = load_profile("/nonexistent")
    armies = [_army("R", MAIN, 9), _army("Q", 5555, 4)]
    d = digest(st, prof, armies=armies)
    assert d["ready_to_redeploy"] == ["R"]
    assert {r["uid"]: r["index"] for r in d["armies"]} == {"R": MAIN, "Q": 5555}


def test_digest_rally_points_from_farm_group():
    from nta_agent.brain.digest import digest
    from nta_agent.execution.profile import load_profile
    st = _state(MAIN)
    prof = load_profile("/nonexistent")
    prof.army["group"] = ["F1"]  # farm group
    armies = [_army("F1", 5555, 9), _army("G", 5555, 6),  # 2 armies at 5555
              _army("R", MAIN, 9)]                         # ready, not farm
    d = digest(st, prof, armies=armies)
    # rally at the farm cell 5555 only; 2 armies there -> 3 free slots of 5
    assert d["rally_points"] == [{"index": 5555, "farm_armies": 1, "free_slots": 3}]
