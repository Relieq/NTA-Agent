"""dig_planner: min-time chain of occupies to a chosen cell (pure, no I/O)."""
from __future__ import annotations

from itertools import pairwise

from nta_agent.execution.dig_planner import (
    W,
    enemy_distance_map,
    place_forts,
    plan_path,
    retarget,
)


def I(x, y):
    return y * W + x


def always(_):
    return True


def unit(_):
    return 10.0


def test_straight_line_path_excludes_owned_and_ends_at_target():
    p = plan_path({I(10, 10)}, I(14, 10), unit, passable=always, margin=3)
    assert p.reason == "ok"
    assert p.path == [I(11, 10), I(12, 10), I(13, 10), I(14, 10)]
    assert p.total_s == 40.0


def test_target_already_owned_is_an_empty_ok_plan():
    p = plan_path({I(5, 5)}, I(5, 5), unit, passable=always)
    assert p.reason == "ok" and p.path == [] and p.total_s == 0


def test_detours_around_obstacles_and_other_owners():
    wall = {I(12, y) for y in range(8, 13)}          # x=12, y 8..12
    p = plan_path({I(10, 10)}, I(14, 10), unit,
                  passable=lambda i: i not in wall, margin=4)
    assert p.reason == "ok"
    assert not set(p.path) & wall
    assert len(p.path) == 4 + 2 * 3   # go round the wall end (y=7 or 13)
    # a cell owned by a non-hostile player is not diggable either
    p2 = plan_path({I(10, 10)}, I(12, 10), unit, passable=always,
                   others={I(11, 10)}, margin=2)
    assert I(11, 10) not in p2.path and len(p2.path) == 4


def test_prefers_cheaper_cells_over_fewer_cells():
    slow = {I(11, 10), I(12, 10), I(13, 10)}
    cost = lambda i: 100.0 if i in slow else 10.0
    p = plan_path({I(10, 10)}, I(14, 10), cost, passable=always, margin=2)
    assert not set(p.path) & slow
    assert p.total_s == 60.0


def test_enemy_buffer_forbids_and_penalises_nearby_cells():
    enemy = {I(12, 13)}
    # buffer 2: every cell within Manhattan 2 of the enemy is forbidden
    p = plan_path({I(10, 10)}, I(14, 10), unit, passable=always,
                  enemy=enemy, buffer=2, penalty_s=0.0, margin=4)
    assert p.reason == "ok"
    d = enemy_distance_map(enemy, p.path, limit=10)
    assert all(d[c] > 2 for c in p.path)
    # the straight row y=10 is distance 3 from the enemy -> allowed but penalised
    p0 = plan_path({I(10, 10)}, I(14, 10), unit, passable=always,
                   enemy=enemy, buffer=2, penalty_s=5.0, margin=4)
    assert p0.path == [I(11, 10), I(12, 10), I(13, 10), I(14, 10)]
    # (12,10) is at d=3 -> 2*penalty; (11,10),(13,10) at d=4 -> 1*penalty
    assert p0.total_s == 40.0 + 10.0 + 5.0 + 5.0
    # a large penalty makes a detour away from the enemy worth it
    far = plan_path({I(10, 10)}, I(14, 10), unit, passable=always,
                    enemy=enemy, buffer=2, penalty_s=100.0, margin=4)
    assert far.total_s < p0.total_s + 1000 and I(12, 10) not in far.path


def test_no_path_when_target_sealed():
    ring = {I(19, 10), I(21, 10), I(20, 9), I(20, 11)}
    p = plan_path({I(10, 10)}, I(20, 10), unit,
                  passable=lambda i: i not in ring, margin=3)
    assert p.reason == "no_path" and p.path == []


def test_blocked_by_hard_when_every_route_needs_a_hard_cell():
    # a corridor: only row y=10 is passable; one cell on it is unbeatable
    passable = lambda i: i // W == 10
    hard = I(12, 10)
    cost = lambda i: None if i == hard else 10.0
    p = plan_path({I(10, 10)}, I(14, 10), cost, passable=passable, margin=2)
    assert p.reason == "blocked_by_hard"
    assert p.hard == [hard]
    assert p.path == [I(11, 10), I(12, 10), I(13, 10), I(14, 10)]


def test_hard_cells_are_bypassed_when_a_detour_exists():
    hard = I(12, 10)
    cost = lambda i: None if i == hard else 10.0
    p = plan_path({I(10, 10)}, I(14, 10), cost, passable=always, margin=2)
    assert p.reason == "ok" and hard not in p.path and p.hard == []


def test_retarget_picks_nearest_free_safe_cell():
    target = I(30, 30)
    enemy = {target, I(31, 30)}
    got = retarget(target, owned={I(10, 10)}, passable=always, enemy=enemy, buffer=1)
    assert got is not None
    d = enemy_distance_map(enemy, [got], limit=5)
    assert d[got] > 1
    gx, gy = got % W, got // W
    assert abs(gx - 30) + abs(gy - 30) == 2  # (28,30),(30,28),(30,32)... nearest ring outside buffer
    # nothing within the radius -> None
    assert retarget(target, owned=set(), passable=lambda i: False, enemy=set(), radius=3) is None


def test_place_forts_every_seven_prefers_low_level_land():
    main = [I(0, 0), I(1, 0), I(0, 1), I(1, 1)]      # 2x2 city block
    path = [I(x, 0) for x in range(2, 30)]            # a long straight dig east
    lv = {I(9, 0): 3, I(10, 0): 1, I(11, 0): 2}
    forts = place_forts(path, main, lambda i: lv.get(i, 2), every=7)
    assert forts, "a 28-cell dig must place forts"
    # first fort in the window 7..9 from the city, on the lv1 cell
    assert forts[0] == I(10, 0)
    # every later fort is again 7..9 cells beyond the previous one
    xs = [f % W for f in forts]
    assert all(7 <= b - a <= 9 for a, b in pairwise(xs))
    # a short dig inside reach needs none
    assert place_forts([I(2, 0), I(3, 0)], main, lambda i: 1) == []
