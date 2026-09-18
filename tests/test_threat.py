from nta_agent.execution.threat import (
    convex_hull,
    detect_incursions,
    point_in_hull,
)

W = 600


def idx(x, y):
    return y * W + x


def test_convex_hull_square():
    pts = [(0, 0), (0, 4), (4, 0), (4, 4), (2, 2)]  # interior point excluded
    hull = convex_hull(pts)
    assert set(hull) == {(0, 0), (0, 4), (4, 0), (4, 4)}
    assert (2, 2) not in hull


def test_convex_hull_degenerate():
    assert convex_hull([(1, 1)]) == [(1, 1)]
    assert convex_hull([(1, 1), (2, 2)]) == [(1, 1), (2, 2)]  # collinear/2 pts


def test_point_in_hull_inside_edge_outside():
    hull = convex_hull([(0, 0), (0, 4), (4, 0), (4, 4)])
    assert point_in_hull((2, 2), hull) is True    # inside
    assert point_in_hull((0, 2), hull) is True    # on edge
    assert point_in_hull((5, 2), hull) is False   # outside


def test_detect_incursion_inside_hull():
    # owned forms a 4x4 block; enemy sits INSIDE the hull -> threat (inside)
    owned = {idx(x, y) for x in range(10, 14) for y in range(10, 14)}
    enemy = {idx(11, 11)}  # inside
    out = detect_incursions(owned, enemy, main=idx(10, 10), map_width=W)
    assert out["summary"]["count"] == 1
    t = out["threats"][0]
    assert t["inside_hull"] is True and t["index"] == idx(11, 11)


def test_detect_incursion_adjacent_border():
    owned = {idx(x, y) for x in range(10, 14) for y in range(10, 14)}
    enemy = {idx(14, 11)}  # just outside east edge, adjacent to owned (13,11)
    out = detect_incursions(owned, enemy, main=idx(10, 10), map_width=W)
    assert out["summary"]["count"] == 1
    assert out["threats"][0]["adjacent"] is True


def test_far_enemy_is_not_a_threat():
    owned = {idx(x, y) for x in range(10, 14) for y in range(10, 14)}
    enemy = {idx(100, 100)}  # far away, outside hull, not adjacent
    out = detect_incursions(owned, enemy, main=idx(10, 10), map_width=W)
    assert out["summary"]["count"] == 0


def test_enemy_city_flagged_and_ranked_first():
    owned = {idx(x, y) for x in range(10, 14) for y in range(10, 14)}
    enemy = {idx(14, 11), idx(11, 11)}
    cities = {idx(14, 11): 1}  # the adjacent one is a city
    out = detect_incursions(owned, enemy, cities, main=idx(10, 10), map_width=W)
    assert out["summary"]["has_enemy_city"] is True
    assert out["threats"][0]["is_city"] is True  # city ranked first
