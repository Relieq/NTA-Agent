from nta_agent.runtime import runner
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.control import write_control


class Spy:
    def __init__(self): self.n = 0
    def tick(self, state): self.n += 1


def _safe(fn, *a): fn(*a)


def test_run_services_skips_when_paused(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    write_control(cfg.control_path, paused=True)
    svc, brain, forts = Spy(), Spy(), Spy()
    acted = runner.run_services(object(), cfg, svc, brain, forts, _safe)
    assert acted is False
    assert (svc.n, brain.n, forts.n) == (0, 0, 0)


def test_run_services_acts_when_running(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)  # no control.json -> run
    svc, brain, forts = Spy(), Spy(), Spy()
    acted = runner.run_services(object(), cfg, svc, brain, forts, _safe)
    assert acted is True
    assert (svc.n, brain.n, forts.n) == (1, 1, 1)
