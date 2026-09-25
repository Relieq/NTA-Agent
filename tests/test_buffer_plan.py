"""buffer_plan: leveling via buffer armies — pure planning."""
from __future__ import annotations

from nta_agent.execution.buffer_plan import demand, level_step, pawn_cost

ROWS = {  # pawnAttr subset (live values 2026-09-25)
    3305001: {"lv_cost": "1,0,346|7,0,1", "lv_time": 488, "lv_cond": "4,2004,1"},
    3305002: {"lv_cost": "1,0,554|7,0,1", "lv_time": 732, "lv_cond": "4,2004,5"},
    3305003: {"lv_cost": "1,0,886|7,0,2", "lv_time": 1098, "lv_cond": "4,2004,10"},
    3202002: {"lv_cost": "1,0,461|7,0,2", "lv_time": 698, "lv_cond": "4,2004,5"},
}


def test_level_step_reads_books_time_and_barracks():
    assert level_step(ROWS, 3305, 1) == {"books": 1, "time_s": 488, "barracks_lv": 1}
    assert level_step(ROWS, 3202, 2) == {"books": 2, "time_s": 698, "barracks_lv": 5}
    assert level_step(ROWS, 3305, 9) is None


def test_pawn_cost_sums_steps_and_stops_at_the_barracks_gate():
    assert pawn_cost(ROWS, 3305, 1, 3, barracks_lv=13) == {"books": 2, "time_s": 1220, "blocked_at": None}
    assert pawn_cost(ROWS, 3305, 1, 4, barracks_lv=6) == {"books": 2, "time_s": 1220, "blocked_at": 3}


def test_demand_groups_weak_pawns_by_type():
    armies = [{"uid": "A", "pawns": [{"uid": "a1", "id": 3305, "lv": 1},
                                     {"uid": "a2", "id": 3305, "lv": 3}]},
              {"uid": "B", "pawns": [{"uid": "b1", "id": 3202, "lv": 2}]}]
    assert demand(armies, target_lv=3) == {3305: [{"uid": "a1", "army_uid": "A", "lv": 1}],
                                           3202: [{"uid": "b1", "army_uid": "B", "lv": 2}]}
