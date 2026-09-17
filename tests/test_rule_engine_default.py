from nta_agent.execution.heuristics import RuleEngine


def test_default_has_heal_routing_before_occupy():
    eng = RuleEngine.default()
    names = [type(r).__name__ for r in eng.rules]
    assert "HealRouting" in names
    assert names.index("HealRouting") < names.index("OccupyCell")
