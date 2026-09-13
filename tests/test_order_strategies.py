from nta_agent.execution.order_strategies import candidate_orders, is_archer_army


def _army(uid, ids):
    return {"uid": uid, "pawns": [{"id": i} for i in ids]}


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


def test_candidate_orders_homogeneous_group_uses_as_selected():
    a, b = _army("a", [3101]), _army("b", [3101])
    labels = {lbl for lbl, _ in candidate_orders([a, b])}
    assert "as-selected" in labels
    assert "archers-first" not in labels
