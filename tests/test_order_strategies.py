from nta_agent.execution.order_strategies import (
    candidate_orders,
    colocated_orders,
    is_archer_army,
)


def _army(uid, ids, index=0):
    return {"uid": uid, "pawns": [{"id": i} for i in ids], "index": index}


def test_is_archer_army_by_majority_pawntype():
    assert is_archer_army(_army("a", [3305, 3305, 3101])) is True
    assert is_archer_army(_army("b", [3101, 3101, 3305])) is False
    assert is_archer_army(_army("c", [])) is False


def test_candidate_orders_includes_archers_first_tanks_first_and_singles():
    cung = _army("cung", [3305, 3305])
    tank = _army("tank", [3101, 3101])
    labels = {lbl for lbl, _ in candidate_orders([tank, cung])}
    assert "archers-first" in labels
    assert "tanks-first" in labels
    assert "single:cung" in labels and "single:tank" in labels
    af = next(order for lbl, order in candidate_orders([tank, cung]) if lbl == "archers-first")
    assert [a["uid"] for a in af] == ["cung", "tank"]


def test_candidate_orders_tank_first_policy_forces_melee_lead():
    cung = _army("cung", [3305, 3305])   # archers
    tank = _army("tank", [3101, 3101])   # melee/tank
    orders = candidate_orders([cung, tank], order="tank_first")
    labels = {lbl for lbl, _ in orders}
    assert "tanks-first" in labels and "archers-first" not in labels
    tf = next(o for lbl, o in orders if lbl == "tanks-first")
    assert [a["uid"] for a in tf] == ["tank", "cung"]   # tank leads (frame-0 front)
    assert "single:cung" in labels                       # singles still offered


def test_candidate_orders_dps_first_policy_forces_archer_lead():
    cung = _army("cung", [3305, 3305])
    tank = _army("tank", [3101, 3101])
    orders = candidate_orders([cung, tank], order="dps_first")
    labels = {lbl for lbl, _ in orders}
    assert "archers-first" in labels and "tanks-first" not in labels
    af = next(o for lbl, o in orders if lbl == "archers-first")
    assert [a["uid"] for a in af] == ["cung", "tank"]    # archers lead


def test_colocated_orders_passes_order_policy_through():
    cung = _army("cung", [3305, 3305], index=100)
    tank = _army("tank", [3101, 3101], index=100)
    labels = {lbl for lbl, _ in colocated_orders([cung, tank], order="tank_first")}
    assert "tanks-first" in labels and "archers-first" not in labels


def test_candidate_orders_homogeneous_group_uses_as_selected():
    a, b = _army("a", [3101]), _army("b", [3101])
    labels = {lbl for lbl, _ in candidate_orders([a, b])}
    assert "as-selected" in labels
    assert "archers-first" not in labels


def test_colocated_orders_never_mixes_different_cells():
    """Armies at different indices must never share a multi-army plan — scattered
    origins arrive in staggered waves and lose pawns the sim can't predict. Only
    same-cell armies combine; every army still gets a single-army plan."""
    a = _army("a", [3101, 3101], index=100)
    b = _army("b", [3101, 3101], index=100)   # same cell as a
    c = _army("c", [3101, 3101], index=250)   # different cell
    plans = colocated_orders([a, b, c])
    orders = [tuple(x["uid"] for x in order) for _, order in plans]
    # a+b (co-located) may combine; c is alone
    assert ("a", "b") in orders or ("b", "a") in orders
    # every army has a single-army plan
    assert ("a",) in orders and ("b",) in orders and ("c",) in orders
    # NO plan mixes c with a or b
    for o in orders:
        assert not ("c" in o and len(o) > 1), f"scattered plan leaked: {o}"


def test_colocated_orders_single_cell_matches_candidate_orders_uids():
    a = _army("a", [3305, 3305], index=7)
    b = _army("b", [3101, 3101], index=7)
    plans = colocated_orders([a, b])
    orders = {tuple(x["uid"] for x in order) for _, order in plans}
    assert ("a", "b") in orders or ("b", "a") in orders   # co-located combine
    assert ("a",) in orders and ("b",) in orders
