"""Approach warning: enemy footprint near the main city, and whether it grew."""
from nta_agent.execution.threat import approach_summary

W = 600
MAIN = 544 * W + 79            # block (79..80, 544..545)


def test_near_enemies_measured_to_2x2_block():
    enemy = {553 * W + 79,      # 8 rows below the block -> dist 8
             546 * W + 81,      # diagonal next to block -> 1+1 = 2
             100 * W + 100}     # far away
    s = approach_summary(enemy, {}, MAIN, W, radius=8)
    assert s["near_count"] == 2
    assert s["min_dist"] == 2
    assert s["nearest_xy"] == [81, 546]


def test_approaching_flags_only_when_closer_or_more():
    enemy = {553 * W + 79}                                   # dist 8
    first = approach_summary(enemy, {}, MAIN, W, radius=8)
    assert first["approaching"] is True                      # new within radius
    same = approach_summary(enemy, {}, MAIN, W, radius=8, prev=first)
    assert same["approaching"] is False                      # static neighbour -> quiet
    closer = approach_summary(enemy | {549 * W + 79}, {}, MAIN, W, radius=8, prev=same)
    assert closer["approaching"] is True and closer["min_dist"] == 4


def test_enemy_city_counts_and_none_near():
    s = approach_summary(set(), {547 * W + 79: 2}, MAIN, W, radius=8)
    assert s["near_count"] == 1 and s["has_city"] is True
    none = approach_summary({100 * W + 100}, {}, MAIN, W, radius=8)
    assert none["near_count"] == 0 and none["approaching"] is False and none["min_dist"] is None
