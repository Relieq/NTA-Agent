from nta_agent.brain.policies import BrainPolicy


def test_fires_on_cadence_until_budget():
    p = BrainPolicy(every_ticks=10, max_calls=2)
    assert p.should_call(10, 0) is True
    assert p.should_call(15, 0) is False   # not on cadence
    assert p.should_call(20, 1) is True
    assert p.should_call(30, 2) is False   # budget exhausted
    assert p.should_call(0, 0) is False    # tick 0 never fires
