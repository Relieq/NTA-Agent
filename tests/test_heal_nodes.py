from nta_agent.execution.army_health import nearest_heal_node
from nta_agent.execution.territory import Fort, Territory


def _terr():
    # main city at index for (100,100); one fort at (110,100). map 600 wide.
    return Territory(main_city=100 * 600 + 100,
                     forts=[Fort(index=100 * 600 + 110, auto_support=True)],
                     garrisons=[], map_width=600)


def test_picks_nearest_eligible_node():
    t = _terr()
    # army at (100,105): main is dist 5, fort is dist 15 -> main wins
    n = nearest_heal_node(105 * 600 + 100, t, occupancy={}, capacity=5)
    assert n == 100 * 600 + 100


def test_skips_full_node():
    t = _terr()
    # main full -> fall back to fort even if farther
    full = {100 * 600 + 100: 5}
    n = nearest_heal_node(105 * 600 + 100, t, occupancy=full, capacity=5)
    assert n == 100 * 600 + 110


def test_none_when_all_full():
    t = _terr()
    full = {100 * 600 + 100: 5, 100 * 600 + 110: 5}
    assert nearest_heal_node(105 * 600 + 100, t, occupancy=full, capacity=5) is None
