from nta_agent.execution.ledger import FailureLedger


def test_record_returns_id_and_persists(tmp_path):
    p = tmp_path / "failures.json"
    led = FailureLedger(p, cap=100)
    eid = led.record("battle_loss", {"cell": 79542, "self_dead": 1})
    assert eid and led.has(eid)
    assert not led.has("nope")
    # reload from disk sees it
    led2 = FailureLedger(p, cap=100)
    assert led2.has(eid)
    assert led2.recent(5)[0].kind == "battle_loss"


def test_cap_keeps_most_recent(tmp_path):
    led = FailureLedger(tmp_path / "f.json", cap=3)
    ids = [led.record("res_depletion", {"rule": "recruit", "resource": "cereal"})
           for _ in range(5)]
    assert len(led.all()) == 3
    assert led.has(ids[-1]) and not led.has(ids[0])


def test_recent_filters_by_kind(tmp_path):
    led = FailureLedger(tmp_path / "f.json")
    led.record("battle_loss", {"self_dead": 2})
    led.record("res_depletion", {"rule": "build"})
    assert len(led.recent(10, kind="battle_loss")) == 1


def test_aggregate_res_windows(tmp_path):
    led = FailureLedger(tmp_path / "f.json")
    led.record("res_depletion", {"rule": "recruit", "resource": "cereal"})
    led.record("res_depletion", {"rule": "forge", "resource": "cereal"})
    led.record("res_depletion", {"rule": "build", "resource": "stone"})
    agg = led.aggregate_res(window_s=3600)
    assert agg == {"cereal": 2, "stone": 1}
    assert led.aggregate_res(window_s=0) == {}   # nothing within a 0s window
