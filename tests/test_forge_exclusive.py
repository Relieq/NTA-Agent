"""forge.py with exclusive equips: craft the chosen one, lock-then-recast, budgets."""
from __future__ import annotations

from nta_agent.execution.forge import craft_candidates, forge_view, next_recast

BASES = {6005: {"exclusive_pawn": "", "forge_cost": "2,0,357|3,0,357|9,0,3", "effect": "8"},
         6101: {"exclusive_pawn": 3101, "forge_cost": "2,0,869|3,0,869|9,0,12", "effect": "21|22"}}
POOLS = {6101: [21, 3, 8, 15]}                 # per-match pool (not equipBase.effect)
RES = {"timber": 5000, "stone": 5000, "iron": 500, "fixator": 20}


def _eq(uid, effects, lock=0):
    return {"uid": uid, "lockEffect": lock,
            "attrs": [{"attr": [2, *e]} for e in effects]}


def _row(t):
    return {"value": "1,200", "odds": "0,50"}


def _next(equips, targets, res=RES, **kw):
    return next_recast(equips, BASES.get, _row, targets, res, pools=POOLS, **kw)


def test_crafts_a_chosen_exclusive_only_when_asked():
    slots = {"10": {"id": 6101, "lv": 10}, "1": {"id": 6005, "lv": 1}}
    assert [c["id"] for c in craft_candidates(slots, BASES.get, set())] == [6005]
    assert sorted(c["id"] for c in craft_candidates(slots, BASES.get, set(), exclusive=True)) == [6005, 6101]


def test_recasts_without_fixators_until_one_wanted_line_appears():
    e = _eq("6101_10", [(15, 5, 0), (8, 10, 0)])
    tgt = {"6101_10": {"budget": 100, "fixator_budget": 5, "mins": {"3.value": 150, "21.value": 5}}}
    d = _next([e], tgt)
    assert d.kind == "recast" and d.fixator == 0 and d.iron == 12


def test_locks_the_first_satisfied_line_then_pays_fixators():
    e = _eq("6101_10", [(3, 160, 0), (8, 10, 0)])                      # 3 met, 21 missing
    tgt = {"6101_10": {"budget": 100, "fixator_budget": 5, "mins": {"3.value": 150, "21.value": 5}}}
    d = _next([e], tgt)
    assert d.kind == "lock" and d.lock_effect == 3
    locked = {**e, "lockEffect": 3}
    d2 = _next([locked], tgt)
    assert d2.kind == "recast" and d2.fixator == 1


def test_a_low_value_wanted_line_is_not_locked():
    e = _eq("6101_10", [(3, 100, 0), (8, 10, 0)])                      # 3 there but < 150
    tgt = {"6101_10": {"budget": 100, "fixator_budget": 5, "mins": {"3.value": 150}}}
    assert _next([e], tgt).kind == "recast"


def test_stops_on_fixator_budget_or_stock_and_when_done():
    locked = _eq("6101_10", [(3, 160, 0), (8, 10, 0)], lock=3)
    tgt = {"6101_10": {"budget": 100, "fixator_budget": 0, "mins": {"3.value": 150, "21.value": 5}}}
    assert _next([locked], tgt) is None                                # no fixator budget
    tgt["6101_10"]["fixator_budget"] = 5
    assert _next([locked], tgt, res={**RES, "fixator": 0}) is None     # no fixators in stock
    done = _eq("6101_10", [(3, 160, 0), (21, 6, 0)], lock=3)
    assert _next([done], tgt) is None


def test_never_recasts_an_equip_locked_on_an_unwanted_line():
    e = _eq("6101_10", [(15, 5, 0), (8, 10, 0)], lock=15)             # player locked 15 by hand
    tgt = {"6101_10": {"budget": 100, "fixator_budget": 5, "mins": {"3.value": 150}}}
    assert _next([e], tgt) is None


def test_no_pool_no_exclusive_recast_and_smelting_blocks():
    e = _eq("6101_10", [(15, 5, 0), (8, 10, 0)])
    tgt = {"6101_10": {"budget": 100, "fixator_budget": 5, "mins": {"3.value": 150}}}
    assert next_recast([e], BASES.get, _row, tgt, RES, pools={}) is None
    assert _next([e], tgt, smelting=True) is None


def test_view_shows_exclusive_rows_with_the_match_pool():
    e = _eq("6101_10", [(3, 160, 0), (8, 10, 0), (21, 3, 0, 6005)], lock=3)
    rows = forge_view([e], BASES.get, _row, {}, pools=POOLS)
    (r,) = rows
    assert r["exclusive"] is True and r["pawn_id"] == 3101
    assert [p["type"] for p in r["possible"]] == [21, 3, 8, 15]         # from the match, not 21|22
    assert r["lock_effect"] == 3 and r["fixator_per_recast"] == 2      # lock + smelted 21 in pool
    assert [x["type"] for x in r["effects"] if x.get("smelted")] == [21]


# ---- stop at ANY 2 wanted lines (user 2026-09-27) ------------------------------
MANY = {"6101_10": {"budget": 100, "fixator_budget": 5,
                    "mins": {"3.value": 150, "21.value": 5, "8.value": 30, "15.value": 9}}}


def test_two_wanted_random_lines_of_many_is_done():
    from nta_agent.execution.forge import target_met
    e = _eq("6101_10", [(21, 6, 0), (8, 40, 0)])       # any 2 of the 4 wanted, both met
    assert target_met(e, MANY["6101_10"], _row) is True
    assert _next([e], MANY) is None


def test_one_wanted_line_locks_then_rolls_the_other_toward_any_wanted():
    e = _eq("6101_10", [(21, 6, 0), (99, 1, 0)])       # 21 met, the other unwanted
    d = _next([e], MANY)
    assert d.kind == "lock" and d.lock_effect == 21
    d2 = _next([{**e, "lockEffect": 21}], MANY)
    assert d2.kind == "recast" and d2.fixator == 1


def test_a_wanted_effect_below_its_minimum_does_not_count():
    from nta_agent.execution.forge import target_met
    e = _eq("6101_10", [(21, 6, 0), (8, 20, 0)])       # 8 rolled but under 30
    assert target_met(e, MANY["6101_10"], _row) is False


def test_smelted_lines_do_not_count_toward_the_two():
    from nta_agent.execution.forge import target_met
    # 21 random + met; 8 only via smelting -> still one random line to roll
    e = {"uid": "6101_10", "lockEffect": 0,
         "attrs": [{"attr": [2, 21, 6, 0]}, {"attr": [2, 99, 1, 0]}, {"attr": [2, 8, 40, 0, 6005]}]}
    assert target_met(e, {"mins": {"21.value": 5, "8.value": 30}}, _row) is False


def test_a_single_wanted_effect_needs_only_that_line():
    from nta_agent.execution.forge import target_met
    e = _eq("6101_10", [(21, 6, 0), (99, 1, 0)])
    assert target_met(e, {"mins": {"21.value": 5}}, _row) is True
