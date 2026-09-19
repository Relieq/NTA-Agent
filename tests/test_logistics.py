"""Tests for the army-logistics planner (dồn/kéo về/sẵn sàng)."""
from nta_agent.execution.logistics import plan_logistics, ready_armies


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
