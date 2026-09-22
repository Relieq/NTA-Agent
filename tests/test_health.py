from nta_agent.execution.health import HealthMonitor


def test_is_stale_after_threshold():
    t = [1000.0]
    hm = HealthMonitor(stale_after=90, clock=lambda: t[0])
    assert not hm.is_stale(950.0)      # 50s old
    t[0] = 1100.0
    assert hm.is_stale(950.0)          # 150s old > 90


def test_recover_counters_and_degraded():
    t = [0.0]
    hm = HealthMonitor(clock=lambda: t[0], degrade_after=3)
    hm.note_recover_fail(); hm.note_recover_fail()
    assert not hm.degraded
    hm.note_recover_fail()
    assert hm.degraded                 # 3 consecutive fails -> degraded
    t[0] = 500.0
    hm.note_recover_ok()
    assert not hm.degraded
    assert hm.recover_count == 1 and hm.last_recover_ts == 500.0


def test_status_shape():
    hm = HealthMonitor(clock=lambda: 200.0)
    st = hm.status(last_activity=170.0, connected=True)
    assert st["connected"] is True
    assert st["last_activity_age"] == 30.0
    assert st["recover_count"] == 0
    assert st["degraded"] is False
