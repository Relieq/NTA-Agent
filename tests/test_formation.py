from nta_agent.execution.formation import candidate_formations, slot_order


def _pawn(uid, hp, pt):
    return {"uid": uid, "id": 3101, "lv": 1, "hp": [hp, hp], "point": pt}


def _army(pawns, index=100):
    return {"uid": "t", "index": index, "pawns": pawns}


def test_slot_order_front_to_back_toward_target():
    # target to the LEFT (smaller x): front = smaller x. slots at x=6 and x=10.
    army = _army([_pawn("a", 50, {"x": 10, "y": 7}), _pawn("b", 50, {"x": 6, "y": 7})], index=100)
    order = slot_order(army, target=98)  # target left of index -> front is smaller x
    assert order[0]["x"] == 6 and order[1]["x"] == 10


def test_beefy_front_puts_highest_hp_on_front_slot():
    army = _army([_pawn("big", 200, {"x": 10, "y": 7}), _pawn("sml", 50, {"x": 6, "y": 7})], index=100)
    plans = dict(candidate_formations(army, target=98))
    assert "beefy-front" in plans and "keep" in plans
    # front slot is x=6; big (200hp) must be assigned there
    assert plans["beefy-front"]["big"] == {"x": 6, "y": 7}
    assert plans["beefy-front"]["sml"] == {"x": 10, "y": 7}


def test_single_pawn_is_keep_only():
    army = _army([_pawn("solo", 50, {"x": 6, "y": 7})])
    labels = [lbl for lbl, _ in candidate_formations(army, target=98)]
    assert labels == ["keep"]
