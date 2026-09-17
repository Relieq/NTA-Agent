"""fort_advisor.recommend_forts: deterministic border-expansion geometry."""
from nta_agent.execution.fort_advisor import recommend_forts

W = 600


def idx(x, y):
    return y * W + x


def test_excludes_cells_within_radius_and_existing_forts():
    main = idx(100, 100)
    owned = {idx(102, 100), idx(105, 100), idx(100, 103)}  # all within radius 6
    recs = recommend_forts(main, owned, forts=[], map_width=W, max_forts=3, radius=6)
    assert recs == []


def test_recommends_frontier_cell_outside_radius():
    main = idx(100, 100)
    owned = {idx(120, 100), idx(102, 100)}  # 120 is far (frontier), 102 is near
    recs = recommend_forts(main, owned, forts=[], map_width=W, max_forts=1, radius=6)
    assert len(recs) == 1
    assert recs[0]["index"] == idx(120, 100)
    assert recs[0]["x"] == 120 and recs[0]["y"] == 100
    assert "reason" in recs[0]


def test_respects_max_forts_cap():
    main = idx(100, 100)
    owned = {idx(120, 100), idx(100, 120), idx(80, 100)}
    recs = recommend_forts(main, owned, forts=[], map_width=W, max_forts=2, radius=6)
    assert len(recs) == 2


def test_spreads_picks_in_different_directions():
    main = idx(100, 100)
    # two clusters: east and south, each with a near + far cell
    owned = {idx(120, 100), idx(119, 100), idx(100, 120), idx(100, 119)}
    recs = recommend_forts(main, owned, forts=[], map_width=W, max_forts=2, radius=6)
    picked = {(r["x"], r["y"]) for r in recs}
    # should cover both directions, not two adjacent east cells
    assert (120, 100) in picked
    assert (100, 120) in picked


def test_excludes_cells_that_are_already_forts():
    main = idx(100, 100)
    owned = {idx(120, 100)}
    recs = recommend_forts(main, owned, forts=[idx(120, 100)], map_width=W,
                           max_forts=1, radius=6)
    assert recs == []


def test_recommend_forts_excludes_rejected():
    main = idx(100, 100)
    owned = {idx(120, 100), idx(100, 120)}
    recs = recommend_forts(main, owned, forts=[], rejected={idx(120, 100)},
                           map_width=W, max_forts=2, radius=6)
    idxs = {r["index"] for r in recs}
    assert idx(120, 100) not in idxs
    assert idx(100, 120) in idxs


def test_plan_forts_accept_is_anchor_excluded_and_counts_cap():
    from nta_agent.execution.fort_advisor import plan_forts
    main = idx(100, 100)
    a = idx(120, 100)  # accepted
    owned = {a, idx(100, 120), idx(80, 100)}
    recs, accepted = plan_forts(main, owned, existing_forts=[],
                                decisions={a: "accepted"}, cap=2, map_width=W)
    assert accepted == [a]
    assert a not in {r["index"] for r in recs}   # accepted excluded
    assert len(recs) <= 1                          # cap 2 - 1 accepted = 1 slot


def test_plan_forts_reject_excluded():
    from nta_agent.execution.fort_advisor import plan_forts
    main = idx(100, 100)
    r = idx(120, 100)
    owned = {r, idx(100, 120)}
    recs, accepted = plan_forts(main, owned, existing_forts=[],
                                decisions={r: "rejected"}, cap=5, map_width=W)
    assert accepted == []
    assert r not in {x["index"] for x in recs}


def test_plan_forts_no_decisions_matches_recommend():
    from nta_agent.execution.fort_advisor import plan_forts
    main = idx(100, 100)
    owned = {idx(120, 100), idx(100, 120)}
    recs, accepted = plan_forts(main, owned, existing_forts=[], decisions={},
                                cap=5, map_width=W)
    base = recommend_forts(main, owned, forts=[], map_width=W, max_forts=5, radius=6)
    assert [r["index"] for r in recs] == [r["index"] for r in base]
    assert accepted == []
