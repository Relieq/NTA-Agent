"""Army-composition assessor: feasibility + deficit for a target composition."""

from nta_agent.execution.army_composer import assess_composition, count_owned


def _army(uid, ids, index=100):
    """ids: list of pawn ids (a hero pawn is a dict {'id':..,'hero':True})."""
    pawns = []
    for i, x in enumerate(ids):
        if isinstance(x, dict):
            pawns.append({"uid": f"{uid}p{i}", **x})
        else:
            pawns.append({"uid": f"{uid}p{i}", "id": x, "lv": 1})
    return {"uid": uid, "index": index, "pawns": pawns}


def test_count_owned_excludes_heroes():
    armies = [_army("a", [3206, 3206, {"id": 3206, "hero": True}]),
              _army("b", [3206, 3101])]
    assert count_owned(armies, 3206) == 3   # 2 in a (hero excluded) + 1 in b
    assert count_owned(armies, 3101) == 1


def test_feasible_when_enough_owned_and_unlocked():
    # target: 1 army of 9x 3206; own 9 already; unlocked.
    armies = [_army("a", [3206] * 9)]
    rep = assess_composition([{"pawn_id": 3206, "armies": 1, "size": 9}],
                             armies, unlocked_ids={3206}, army_cap=4)
    assert rep.feasible is True
    assert rep.issues == []
    assert rep.targets[0].deficit == 0


def test_deficit_reported_when_short_but_unlocked():
    # target 4x9=36 of 3305; own 1; unlocked -> feasible via recruiting, deficit 35.
    armies = [_army("a", [3305])]
    rep = assess_composition([{"pawn_id": 3305, "armies": 4, "size": 9}],
                             armies, unlocked_ids={3305}, army_cap=9)
    assert rep.targets[0].deficit == 35
    assert rep.feasible is True                       # recruitable
    assert any("35" in s for s in rep.issues)         # surfaced for the brain


def test_infeasible_when_locked_and_short():
    # need to recruit 3305 but it's NOT unlocked -> infeasible, issue names it.
    armies = [_army("a", [3305])]
    rep = assess_composition([{"pawn_id": 3305, "armies": 4, "size": 9}],
                             armies, unlocked_ids=set(), army_cap=9)
    assert rep.feasible is False
    assert any("3305" in s and "unlock" in s.lower() for s in rep.issues)


def test_locked_but_enough_owned_is_feasible():
    # locked type but we already own enough -> no recruiting needed -> feasible.
    armies = [_army("a", [3206] * 9)]
    rep = assess_composition([{"pawn_id": 3206, "armies": 1, "size": 9}],
                             armies, unlocked_ids=set(), army_cap=4)
    assert rep.feasible is True


def test_over_army_cap_is_infeasible():
    # 5 target armies but cap is 4 -> can't hold the group.
    armies = [_army("a", [3206] * 9)]
    target = [{"pawn_id": 3206, "armies": 1, "size": 9},
              {"pawn_id": 3305, "armies": 4, "size": 9}]
    rep = assess_composition(target, armies, unlocked_ids={3206, 3305}, army_cap=4)
    assert rep.total_target_armies == 5
    assert rep.over_cap is True
    assert rep.feasible is False
    assert any("cap" in s.lower() or "slot" in s.lower() for s in rep.issues)


def test_full_request_1_tank_4_imp():
    # the user's request: 1x 3206 + 4x 3305; own plenty 3206, ~1 3305; cap 9.
    armies = [_army("a", [3206] * 9), _army("b", [3206] * 9),
              _army("c", [3305, 3101, 3101])]
    target = [{"pawn_id": 3206, "armies": 1, "size": 9},
              {"pawn_id": 3305, "armies": 4, "size": 9}]
    rep = assess_composition(target, armies, unlocked_ids={3206, 3305}, army_cap=9)
    assert rep.feasible is True                       # cap ok, both unlocked
    t3206 = next(t for t in rep.targets if t.pawn_id == 3206)
    t3305 = next(t for t in rep.targets if t.pawn_id == 3305)
    assert t3206.deficit == 0                         # own 18 >= 9
    assert t3305.deficit == 35                        # own 1, need 36
