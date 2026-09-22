from nta_agent.execution.occupy_planner import full_hp_pawns, heal_convenient

W = 600
def idx(x, y): return y * W + x


def test_full_hp_restores_cur_to_max():
    pawns = [{"uid": "a", "hp": {0: 3, 1: 10}}, {"uid": "b", "hp": [5, 20]}, {"uid": "c"}]
    out = full_hp_pawns(pawns)
    assert out[0]["hp"] == [10, 10] and out[1]["hp"] == [20, 20]
    assert "hp" not in out[2]           # unknown max -> left as-is
    assert pawns[0]["hp"] == {0: 3, 1: 10}   # original untouched


def test_convenient_when_army_near_node():
    city = idx(100, 100)
    army = idx(102, 101)               # 3 cells from city (<4)
    assert heal_convenient(army, idx(120, 100), [city], radius=4)


def test_convenient_when_route_passes_near_node():
    city = idx(100, 100)
    army = idx(90, 100); target = idx(120, 100)   # straight line passes through city
    assert heal_convenient(army, target, [city], radius=4)


def test_not_convenient_when_far_and_route_bypasses():
    city = idx(100, 100)
    army = idx(100, 130); target = idx(140, 130)  # far below, route stays on y=130
    assert not heal_convenient(army, target, [city], radius=4)
