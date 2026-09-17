from nta_agent.execution.army_health import army_is_wounded, army_wound_frac


def _army(*hps):
    return {"pawns": [{"hp": list(h)} for h in hps]}


def test_healthy_army_not_wounded():
    a = _army((100, 100), (50, 50))
    assert army_is_wounded(a) is False
    assert army_wound_frac(a) == 0.0


def test_wounded_army_detected():
    a = _army((100, 100), (20, 50))
    assert army_is_wounded(a) is True
    assert abs(army_wound_frac(a) - (30 / 150)) < 1e-9


def test_missing_or_empty_hp_is_safe():
    assert army_is_wounded({"pawns": [{}]}) is False        # no hp -> treat as full
    assert army_is_wounded({}) is False                      # no pawns
    assert army_wound_frac({"pawns": []}) == 0.0             # no max -> 0, not div0
    assert army_is_wounded({"pawns": [{"hp": 40}]}) is False  # scalar hp, max unknown


def test_curhp_maxhp_shape():
    # Engine's real serialization: pawns carry scalar curHp/maxHp.
    healthy = {"pawns": [{"curHp": 100, "maxHp": 100}]}
    wounded = {"pawns": [{"curHp": 30, "maxHp": 100}]}
    assert army_is_wounded(healthy) is False
    assert army_is_wounded(wounded) is True
    assert abs(army_wound_frac(wounded) - 0.7) < 1e-9
