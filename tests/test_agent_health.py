import types

from nta_agent.execution.agent import Agent
from nta_agent.execution.health import HealthMonitor


def _agent(last_activity, *, probe_ok, clock=1000.0):
    hm = HealthMonitor(stale_after=90, clock=lambda: clock)
    sess = types.SimpleNamespace(last_activity=last_activity, _recovered=0)

    def recover():
        sess._recovered += 1
        sess.last_activity = clock
        return True
    sess.recover = recover
    a = Agent(session=sess, engine=types.SimpleNamespace(tick=lambda s, ac: []), health=hm)

    def get_marches():
        if not probe_ok:
            raise ConnectionError("half-open")
        sess.last_activity = clock   # a successful probe proves liveness
        return {}
    a.actions = types.SimpleNamespace(get_marches=get_marches)
    return a, sess, hm


def test_not_stale_skips_probe_and_recover():
    a, sess, _hm = _agent(last_activity=980.0, probe_ok=False)  # 20s old, not stale
    assert a._health_check() is False
    assert sess._recovered == 0


def test_stale_but_probe_ok_no_recover():
    a, sess, _hm = _agent(last_activity=0.0, probe_ok=True)     # 1000s old -> stale
    assert a._health_check() is False       # probe succeeded -> alive
    assert sess._recovered == 0


def test_stale_and_probe_fails_triggers_recover():
    a, sess, hm = _agent(last_activity=0.0, probe_ok=False)    # stale + dead probe
    assert a._health_check() is True
    assert sess._recovered == 1
    assert hm.recover_count == 1            # recovery telemetry updated


def test_no_health_monitor_is_noop():
    sess = types.SimpleNamespace(last_activity=0.0)
    a = Agent(session=sess, engine=types.SimpleNamespace(tick=lambda s, ac: []))
    a.actions = types.SimpleNamespace(get_marches=dict)
    assert a._health_check() is False       # no monitor -> never probes
