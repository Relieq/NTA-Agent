from nta_agent.execution.heuristics import _unused_army_name


def test_picks_first_unused_d_name():
    assert _unused_army_name([]) == "D1"
    assert _unused_army_name([{"name": "D1"}]) == "D2"
    # count-based would give D2 (collision); helper finds the free D-slot
    assert _unused_army_name([{"name": "1"}, {"name": "D2"}]) == "D1"
    assert _unused_army_name([{"name": "D1"}, {"name": "D3"}]) == "D2"
    assert _unused_army_name([{"name": "Cứu Hộ"}, {"name": "D1"}, {"name": "D2"}]) == "D3"
