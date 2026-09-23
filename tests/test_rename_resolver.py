from nta_agent.execution.rename_resolver import resolve_rename_plan


def _army(uid, *ids):
    return {"uid": uid, "pawns": [{"id": i} for i in ids]}


ARMIES = [
    _army("axe", *([3206] * 9)),          # pure rìu khiên
    _army("imp1", *([3305] * 9)),         # pure IMP x4
    _army("imp2", *([3305] * 9)),
    _army("imp3", *([3305] * 9)),
    _army("imp4", *([3305] * 9)),
    _army("mix", 3206, 3206, 3101),       # mixed (dominant 3206 but NOT pure)
]


def test_resolves_clean_group():
    plan = [{"pawn": 3206, "name": "Đội 1"},
            {"pawn": 3305, "name": "Đội 2"}, {"pawn": 3305, "name": "Đội 3"},
            {"pawn": 3305, "name": "Đội 4"}, {"pawn": 3305, "name": "Đội 5"}]
    renames, q = resolve_rename_plan(plan, ARMIES)
    assert q == ""
    assert {"uid": "axe", "name": "Đội 1"} in renames          # only the PURE 3206
    assert sum(1 for r in renames if r["name"] in ("Đội 2", "Đội 3", "Đội 4", "Đội 5")) == 4
    assert len(renames) == 5
    # the mixed army is never touched
    assert all(r["uid"] != "mix" for r in renames)


def test_ambiguous_count_asks_and_renames_nothing():
    # ask for 2 rìu khiên but only 1 pure 3206 exists -> question, no renames
    plan = [{"pawn": 3206, "name": "A"}, {"pawn": 3206, "name": "B"}]
    renames, q = resolve_rename_plan(plan, ARMIES)
    assert renames == [] and q


def test_too_many_candidates_asks():
    # 1 IMP requested but 4 pure 3305 exist -> ambiguous which one -> ask
    renames, q = resolve_rename_plan([{"pawn": 3305, "name": "X"}], ARMIES)
    assert renames == [] and q


def test_bad_names_ignored():
    renames, q = resolve_rename_plan([{"pawn": 3206, "name": "x" * 13}], ARMIES)
    assert renames == [] and q == ""          # nothing valid to do


def test_deterministic_order_by_uid():
    plan = [{"pawn": 3305, "name": "n1"}, {"pawn": 3305, "name": "n2"},
            {"pawn": 3305, "name": "n3"}, {"pawn": 3305, "name": "n4"}]
    r1, _ = resolve_rename_plan(plan, ARMIES)
    r2, _ = resolve_rename_plan(plan, ARMIES)
    assert r1 == r2 and [r["uid"] for r in r1] == ["imp1", "imp2", "imp3", "imp4"]
