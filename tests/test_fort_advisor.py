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
