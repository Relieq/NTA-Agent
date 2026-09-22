from nta_agent.execution.occupy_planner import bridge_hop

W = 600
def idx(x, y): return y * W + x


def test_bridge_relays_through_forward_in_zone_cell():
    city = idx(100, 100)
    target = idx(112, 100)              # 12 east — outside the 6-radius zone
    fwd = idx(106, 100)                 # owned, in-zone (<=6 of city), near target
    owned = {idx(101, 100), idx(103, 100), fwd}
    hop = bridge_hop(city, target, owned, [city], radius=6)
    assert hop == fwd                   # stage at the forward in-zone cell


def test_no_bridge_when_target_near_zone():
    city = idx(100, 100)
    target = idx(104, 100)             # within radius 6 -> direct is fine
    owned = {idx(102, 100)}
    assert bridge_hop(city, target, owned, [city], radius=6) is None


def test_no_bridge_when_no_closer_in_zone_cell():
    city = idx(100, 100)
    target = idx(112, 100)
    owned = {idx(99, 100)}             # behind the city, not closer to target
    assert bridge_hop(city, target, owned, [city], radius=6) is None


def test_fort_extends_zone_enables_farther_relay():
    city = idx(100, 100)
    fort = idx(110, 100)               # a fort extends the speed zone east
    target = idx(120, 100)
    fwd = idx(114, 100)                # in-zone via the fort, near target
    owned = {fwd, idx(108, 100)}
    hop = bridge_hop(city, target, owned, [city, fort], radius=6)
    assert hop == fwd
