from nta_agent.execution.captcha import CaptchaRequired
from nta_agent.runtime import runner
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.state.schema import GameState
from tests.test_captcha import FakeConfig


class FakeSession:
    def __init__(self):
        self.state = GameState(source="api")
        self.closed = False

    def sync(self):
        return self.state

    def request(self, route, params=None, timeout=15):
        if route == "game/HD_GetAntiCheatQuestion":
            return {"item": "item_1", "options": [10, 11, 12], "surplusTime": 30}
        if route == "game/HD_AntiCheatAnswer":
            return {"rst": True, "wrongCount": 0}
        raise AssertionError(route)

    def close(self):
        self.closed = True


class BoomEngine:
    def tick(self, state, actions):
        raise CaptchaRequired("x: ecode.500221")


def test_runner_wires_captcha_solver(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.GameConfig, "load", staticmethod(lambda *a, **k: FakeConfig()))
    cfg = RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path),
                                  "NTA_TICK_INTERVAL": "0"})
    sess = FakeSession()
    runner.run(cfg, ticks=1, session=sess, engine=BoomEngine())
    events = cfg.event_log_path.read_text(encoding="utf-8")
    assert "captcha_solved" in events
