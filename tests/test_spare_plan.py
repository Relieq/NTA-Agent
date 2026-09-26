"""spare_plan: sort spare armies' pawns into pure single-type armies (pure, no I/O)."""
from __future__ import annotations

from collections import Counter

from nta_agent.execution.spare_plan import apply_ops, purity_ops


def _a(uid, types):
    return {"uid": uid, "pawns": [{"uid": f"{uid}-{k}", "id": t, "lv": 1}
                                  for k, t in enumerate(types)]}


def _types(armies):
    return {a["uid"]: Counter(p["id"] for p in a["pawns"]) for a in armies}


def test_live_example_d6_d7_d1_become_as_pure_as_possible():
    # live 2026-09-26: D6/D7 = 8x3201 + 1 IMP, D1 = mixed
    d6 = _a("D6", [3201] * 8 + [3305])
    d7 = _a("D7", [3201] * 8 + [3305])
    d1 = _a("D1", [3201] * 3 + [3202] + [3305] * 5)
    ops = purity_ops([d6, d7, d1])
    out = apply_ops([d6, d7, d1], ops)
    t = _types(out)
    # 19x3201, 7xIMP, 1x3202: two pure 3201 armies, the rest mixed in one
    assert t["D6"] == {3201: 9} and t["D7"] == {3201: 9}
    assert t["D1"] == {3305: 7, 3201: 1, 3202: 1}
    assert all(op[0] == "exchange" for op in ops)          # full armies -> swaps only


def test_moves_into_room_before_swapping():
    a = _a("A", [3201, 3201])            # room for 7
    b = _a("B", [3201, 3305])
    ops = purity_ops([a, b])
    out = apply_ops([a, b], ops)
    t = _types(out)
    assert t["A"] == {3201: 3} and t["B"] == {3305: 1}
    assert ops == [("move", "B", "B-0", "A")]


def test_already_pure_needs_nothing():
    assert purity_ops([_a("A", [3201] * 9), _a("B", [3305] * 4)]) == []


def test_random_mixes_keep_every_pawn_and_respect_the_cap():
    import random
    rng = random.Random(7)
    for _ in range(200):
        armies = [_a(f"A{i}", [rng.choice([3201, 3202, 3305, 3401])
                               for _ in range(rng.randint(1, 9))]) for i in range(rng.randint(2, 5))]
        before = Counter(p["id"] for a in armies for p in a["pawns"])
        out = apply_ops(armies, purity_ops(armies))
        assert Counter(p["id"] for a in out for p in a["pawns"]) == before
        assert all(len(a["pawns"]) <= 9 for a in out)
        # never less pure than before: count of distinct types per army doesn't grow in total
        assert sum(len({p["id"] for p in a["pawns"]}) for a in out) <= \
            sum(len({p["id"] for p in a["pawns"]}) for a in armies)
