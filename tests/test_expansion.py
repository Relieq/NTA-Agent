from nta_agent.execution.expansion import owned_neighbors, sort_key

W = 600


def test_owned_neighbors_counts_4dir():
    c = 100 * W + 100
    owned = {c - 1, c + 1, c - W}  # left, right, up owned; down not
    assert owned_neighbors(c, owned, W) == 3
    assert owned_neighbors(c, set(), W) == 0


def test_spiral_prefers_fewest_owned_neighbors_then_loss():
    a = sort_key("spiral", owned_neighbors=1, land_value=10, loss_percent=30)
    b = sort_key("spiral", owned_neighbors=2, land_value=99, loss_percent=0)
    assert a < b  # 1-neighbor beats 2-neighbor regardless of value


def test_octopus_prefers_high_value_then_loss():
    rich = sort_key("octopus", owned_neighbors=3, land_value=50, loss_percent=40)
    poor = sort_key("octopus", owned_neighbors=1, land_value=5, loss_percent=0)
    assert rich < poor  # richer land wins even if harder / more exposed


def test_hybrid_value_then_exposure_then_loss():
    a = sort_key("hybrid", owned_neighbors=2, land_value=50, loss_percent=10)
    b = sort_key("hybrid", owned_neighbors=1, land_value=50, loss_percent=10)
    assert b < a  # same value -> fewer owned neighbours wins


def test_unknown_mode_falls_back_to_loss():
    assert sort_key("none", owned_neighbors=9, land_value=0, loss_percent=5) == (5,)
