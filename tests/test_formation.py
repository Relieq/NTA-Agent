from nta_agent.execution.formation import candidate_orderings, swaps_for


def _pawn(uid, hp):
    return {"uid": uid, "id": 3101, "lv": 1, "hp": [hp, hp]}


def _army(pawns):
    return {"uid": "t", "index": 100, "pawns": pawns}


def test_beefy_first_orders_pawns_by_hp_desc():
    army = _army([_pawn("sml", 50), _pawn("big", 200), _pawn("mid", 80)])
    plans = dict(candidate_orderings(army))
    assert "beefy-first" in plans and "keep" in plans
    assert [p["uid"] for p in plans["beefy-first"]] == ["big", "mid", "sml"]


def test_single_pawn_is_keep_only():
    labels = [lbl for lbl, _ in candidate_orderings(_army([_pawn("solo", 50)]))]
    assert labels == ["keep"]


def test_equal_hp_stays_keep_only():
    # all same HP -> beefy-first == current -> only keep offered
    labels = [lbl for lbl, _ in candidate_orderings(_army([_pawn("a", 80), _pawn("b", 80)]))]
    assert labels == ["keep"]


def test_swaps_for_reorders_current_into_target():
    cur = ["sml", "mid", "big"]
    target = ["big", "mid", "sml"]
    swaps = swaps_for(cur, target)
    # apply the swaps and check we reach the target
    order = list(cur)
    for a, b in swaps:
        i, j = order.index(a), order.index(b)
        order[i], order[j] = order[j], order[i]
    assert order == target


def test_swaps_for_noop_when_already_ordered():
    assert swaps_for(["a", "b"], ["a", "b"]) == []
