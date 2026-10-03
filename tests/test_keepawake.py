"""Keep the PC awake while the agent runs (2026-10-03: Modern Standby froze the agent for 63 min
mid-dig). Windows power APIs through an injected kernel32 so it runs anywhere."""
import time

from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.keepawake import ES_CONTINUOUS, ES_SYSTEM_REQUIRED, KeepAwake


class FakeKernel:
    def __init__(self, fail_request=False):
        self.states = []
        self.requests = []
        self.closed = []
        self.fail_request = fail_request

    def SetThreadExecutionState(self, flags):
        self.states.append(flags)
        return 1

    def PowerCreateRequest(self, ctx):
        if self.fail_request:
            raise OSError("no power requests here")
        return 77

    def PowerSetRequest(self, h, kind):
        self.requests.append((h, kind))
        return 1

    def PowerClearRequest(self, h, kind):
        self.requests.append((h, -kind))
        return 1

    def CloseHandle(self, h):
        self.closed.append(h)
        return 1


def _wait(cond, t=2.0):
    end = time.time() + t
    while time.time() < end and not cond():
        time.sleep(0.01)
    return cond()


def test_holds_the_system_awake_until_stopped_and_then_lets_go():
    k = FakeKernel()
    ka = KeepAwake(kernel=k, renew_s=0.05)
    assert ka.start() is True
    assert _wait(lambda: len(k.states) >= 2)                   # asserted and renewed
    assert all(s == ES_CONTINUOUS | ES_SYSTEM_REQUIRED for s in k.states)
    assert (77, 1) in k.requests                                 # system-required power request
    ka.stop()
    assert k.states[-1] == ES_CONTINUOUS                         # cleared: the PC may sleep again
    assert 77 in k.closed
    assert not ka.active


def test_a_failing_power_request_never_stops_the_execution_state():
    k = FakeKernel(fail_request=True)
    ka = KeepAwake(kernel=k, renew_s=0.05)
    assert ka.start() is True
    assert _wait(lambda: len(k.states) >= 1)
    ka.stop()


def test_disabled_or_unsupported_platforms_do_nothing():
    k = FakeKernel()
    assert KeepAwake(kernel=k, enabled=False).start() is False and k.states == []
    assert KeepAwake(kernel=None).start() is False             # no kernel32 (non-Windows)


def test_config_reads_the_switch_from_env_then_settings(monkeypatch):
    assert RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x"}).keep_awake is True
    assert RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_KEEP_AWAKE": "0"}).keep_awake is False
    from nta_agent import settings
    monkeypatch.setattr(settings, "get", lambda k, d=None: "off" if k == "keep_awake" else
                        ("x" if k == "distinct_id" else d))
    assert RuntimeConfig.from_env({}).keep_awake is False
