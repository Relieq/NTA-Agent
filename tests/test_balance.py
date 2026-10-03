"""Dig wear levelling: the pawns that lost the most hp swap places with the same-type pawns
that still have a lot (player 2026-10-03: 'lính mất máu nhiều tráo với lính máu nhiều'), so the
group goes on without a trip to the city. Pure helpers + the dig integration."""
from types import SimpleNamespace

from nta_agent.execution.advisor import Plan
from nta_agent.execution.balance import apply_swaps, balance_swaps
from nta_agent.execution.heuristics import OccupyCell


def _p(uid, cur, mx=100, pid=3201):
    return {"uid": uid, "id": pid, "hp": {0: cur, 1: mx}}


def test_the_most_wounded_front_pawn_swaps_with_the_healthiest_one_behind_it():
    pawns = [_p("a", 30), _p("b", 80), _p("c", 100), _p("d", 100)]
    steps = balance_swaps(pawns)
    assert steps[0] == [("a", "c")]                                # a (-70) <-> the nearest full-hp pawn
    assert len(steps) == 2 and steps[1] == [("a", "c"), ("b", "d")]   # b (-20) can pair up too


def test_prefixes_grow_by_one_pair_most_wounded_first():
    pawns = [_p("a", 20), _p("b", 50), _p("c", 100), _p("d", 100)]
    steps = balance_swaps(pawns)
    assert len(steps) == 2 and steps[0] == [steps[1][0]]           # k=1 is the first pair of k=2
    assert steps[0][0][0] == "a"                                   # the biggest loss goes first


def test_never_swaps_with_a_pawn_ahead_or_of_another_type_or_not_healthier():
    assert balance_swaps([_p("c", 100), _p("a", 30)]) == []        # healthy one is already in front
    assert balance_swaps([_p("a", 30), _p("c", 100, pid=3305)]) == []   # different type
    assert balance_swaps([_p("a", 90), _p("c", 80)]) == []         # not healthier
    assert balance_swaps([_p("a", 100), _p("c", 100)]) == []       # nobody wounded
    assert balance_swaps([{"id": 3201, "hp": {0: 1, 1: 100}}, _p("c", 100)]) == []   # no uid


def test_apply_swaps_returns_the_new_order_without_touching_the_input():
    pawns = [_p("a", 30), _p("b", 100), _p("c", 100)]
    out = apply_swaps(pawns, [("a", "c")])
    assert [p["uid"] for p in out] == ["c", "b", "a"]
    assert [p["uid"] for p in pawns] == ["a", "b", "c"]


# ---- dig integration ------------------------------------------------------------------------
W = 600
CELL = 100 * W + 104
CANDS = [SimpleNamespace(index=CELL)]


def _rule(max_loss=0):
    prof = SimpleNamespace(occupy={"max_loss": max_loss},
                           army={"group": ["g1"], "presets": {}, "active": ""})
    r = OccupyCell(profile=prof)
    r.hard = []
    r.dig_hard_sink = r.hard.append
    r.events = []
    r.on_event = lambda k, d=None: r.events.append((k, d))
    return r


def _plans_for(order):
    def plans_for(i):
        return [Plan(armies=[{"uid": "g1", "index": i - 1, "pawns": [dict(p) for p in order]}],
                     target=i, label="g1", prediction=None)]
    return plans_for


def _predict(plan):
    pawns = plan.armies[0]["pawns"]
    front_hurt = pawns[0]["hp"][0] < pawns[0]["hp"][1]
    return SimpleNamespace(win=True, loss_percent=11.0 if front_hurt else 0.0)


def test_a_wounded_front_pawn_is_rotated_instead_of_going_home():
    r = _rule()
    order = [_p("a", 30), _p("b", 100), _p("c", 100)]
    out = r._dig_select(CANDS, _plans_for(order), _predict, CELL)
    assert out == "balance"
    assert r.hard == []
    assert [k for k, _ in r.events] == ["dig_balance"]
    ((uid, index, swaps),) = r._balance
    assert uid == "g1" and index == CELL - 1 and swaps[0][0] == "a"

    class Acts:
        def __init__(self):
            self.calls = []

        def exchange_pawn_army(self, idx, army_uid, u1, u2, army_uid2=None):
            self.calls.append((idx, army_uid, u1, u2))
    acts = Acts()
    r.act(acts)
    assert acts.calls == [(CELL - 1, "g1") + tuple(swaps[0])] and r._balance is None


def test_without_a_healthy_partner_it_still_waits_to_heal():
    r = _rule()
    order = [_p("a", 30), _p("b", 40)]                     # nobody healthier behind it
    assert r._dig_select(CANDS, _plans_for(order), _predict, CELL) is None
    assert "dig_heal_wait" in [k for k, _ in r.events] and r.hard == []


def test_a_refused_swap_falls_back_to_healing_and_is_not_retried_at_once():
    r = _rule()
    order = [_p("a", 30), _p("b", 100)]
    assert r._dig_select(CANDS, _plans_for(order), _predict, CELL) == "balance"

    class Refuse:
        def exchange_pawn_army(self, *a, **k):
            raise RuntimeError("game/HD_ExchangePawnArmy: ecode.500000")
    r.act(Refuse())
    assert r._balance is None
    assert r._dig_select(CANDS, _plans_for(order), _predict, CELL) is None   # heal path now
    assert "dig_heal_wait" in [k for k, _ in r.events]
