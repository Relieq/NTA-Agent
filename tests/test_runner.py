import json

from nta_agent.execution.heuristics import RuleEngine
from nta_agent.runtime import runner
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self):
        self.state = GameState(source="api")
        self.state.resources.cereal = 100
        self.closed = False
        self.synced = 0

    def sync(self):
        self.synced += 1
        self.state.resources.cereal += 1

    def close(self):
        self.closed = True


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x",
                                   "NTA_LOG_DIR": str(tmp_path / "run"),
                                   "NTA_TICK_INTERVAL": "0"})


def test_run_writes_snapshot_and_events_and_closes(tmp_path):
    cfg = _cfg(tmp_path)
    sess = FakeSession()
    runner.run(cfg, ticks=3, session=sess, engine=RuleEngine(rules=[]))
    snap = json.loads(cfg.snapshot_path.read_text())
    assert snap["resources"]["cereal"] >= 103
    rows = [json.loads(x) for x in cfg.event_log_path.read_text().splitlines() if x.strip()]
    assert sum(1 for r in rows if r["kind"] == "tick") == 3
    assert sess.closed is True
