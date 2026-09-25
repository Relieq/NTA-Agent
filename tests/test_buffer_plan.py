"""buffer_plan: leveling via buffer armies — pure planning."""
from __future__ import annotations

from nta_agent.execution.buffer_plan import (
    demand,
    level_step,
    meeting_cell,
    pawn_cost,
    pick_target,
    propose,
    swap_pairs,
)

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



def _imp(u, lv=1):
    return {"uid": u, "id": 3305, "lv": lv}


def _group():
    return [{"uid": f"G{i}", "pawns": [_imp(f"g{i}{k}") for k in range(9)]} for i in range(4)]


def test_propose_live_example_one_imp_buffer_from_spares():
    spares = [{"uid": "D5", "name": "D5", "pawns": [_imp(f"d5{k}") for k in range(6)] +
               [{"uid": f"d5c{k}", "id": 3201, "lv": 1} for k in range(3)]},
              {"uid": "D1", "name": "D1", "pawns": [_imp(f"d1{k}") for k in range(4)]}]
    p = propose(_group(), spares, 3, rows=ROWS, barracks_lv=13, exp_book=49,
                army_count=9, army_cap=9)
    (b,) = p["buffers"]
    assert b["base_uid"] == "D5" and b["types"] == {3305: 9} and b["name"] == "Nâng Cấp 1"
    assert len(b["merge"]) == 3 and all(m["from_uid"] == "D1" for m in b["merge"])
    # D5 is full (9): each IMP brought in hands one of its 3201 back (exchange)
    assert sorted(m["swap_out"] for m in b["merge"]) == ["d5c0", "d5c1", "d5c2"]
    assert b["recruit"] == {}
    assert p["books_needed"] == 2 * 36 + 2 * 9 and p["books_have"] == 49
    assert p["dismiss"] == []          # D5 reused: no new army slot needed
    assert p["notes"]                  # books short -> said so


def test_propose_recruits_a_new_buffer_and_suggests_dismissals_at_the_cap():
    spares = [{"uid": "S1", "name": "S1", "pawns": [{"uid": "c1", "id": 3201, "lv": 1}]},
              {"uid": "S2", "name": "S2", "pawns": [{"uid": "c2", "id": 3201, "lv": 1},
                                                    {"uid": "c3", "id": 3201, "lv": 1}]}]
    p = propose(_group(), spares, 3, rows=ROWS, barracks_lv=13, exp_book=500,
                army_count=6, army_cap=6)
    (b,) = p["buffers"]
    assert b["base_uid"] == "" and b["recruit"] == {3305: 9}
    assert p["dismiss"] == ["S1"]      # one slot needed; the smallest spare goes
    assert not p["notes"]


def test_propose_nothing_to_do_when_all_at_target():
    g = [{"uid": "G", "pawns": [_imp("x", lv=3)]}]
    p = propose(g, [], 3, rows=ROWS, barracks_lv=13, exp_book=0, army_count=1, army_cap=5)
    assert p["buffers"] == [] and p["books_needed"] == 0


def test_swap_pairs_same_type_weakest_first():
    main = {"uid": "M", "pawns": [{"uid": "m1", "id": 3305, "lv": 2}, {"uid": "m2", "id": 3305, "lv": 1},
                                  {"uid": "m3", "id": 3202, "lv": 1}]}
    buf = {"uid": "B", "pawns": [{"uid": "b1", "id": 3305, "lv": 3}, {"uid": "b2", "id": 3305, "lv": 3},
                                 {"uid": "b3", "id": 3305, "lv": 2}]}
    assert swap_pairs(main, buf, 3) == [("m2", "b1"), ("m1", "b2")]   # no 3202 ready; b3 not ready


def test_pick_target_most_pairs_then_weakest():
    buf = {"uid": "B", "pawns": [{"uid": f"b{k}", "id": 3305, "lv": 3} for k in range(3)]}
    a = {"uid": "A", "pawns": [{"uid": "a1", "id": 3305, "lv": 2}]}
    b = {"uid": "B2", "pawns": [{"uid": "x1", "id": 3305, "lv": 1}, {"uid": "x2", "id": 3305, "lv": 1}]}
    c = {"uid": "C", "pawns": [{"uid": "c1", "id": 3202, "lv": 1}]}
    assert pick_target([a, b, c], buf, 3) == "B2"
    assert pick_target([c], buf, 3) is None


def test_meeting_cell_is_owned_adjacent_with_room():
    W = 600
    c = 10 * W + 10
    owned = {c - 1, c + 1, c + W}
    assert meeting_cell(c, owned, {c - 1: 5, c + 1: 2}) == c + 1
    assert meeting_cell(c, owned, {c - 1: 5, c + 1: 5, c + W: 5}) is None
    assert meeting_cell(c, set(), {}) is None
