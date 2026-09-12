from nta_agent.execution.agent import Agent
from nta_agent.execution.captcha import CaptchaRequired
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self):
        self.state = GameState(source="api")

    def sync(self):
        return self.state


class BoomEngine:
    def tick(self, state, actions):
        raise CaptchaRequired("game/HD_UpAreaBuild: ecode.500221")


class OkEngine:
    def tick(self, state, actions):
        return ["collect_city_output"]


class FakeSolver:
    def __init__(self, rst=True):
        self.rst = rst
        self.calls = 0

    def solve(self):
        self.calls += 1
        return {"rst": self.rst, "wrongCount": 0}


def _agent(engine, **kw):
    return Agent(FakeSession(), engine, **kw)


def test_tick_solves_captcha_when_solver_present():
    events = []
    solver = FakeSolver(rst=True)
    ag = _agent(BoomEngine(), on_event=lambda k, d=None: events.append(k))
    ag.captcha = solver
    fired = ag.tick()
    assert fired == ["captcha_solved"] and solver.calls == 1
    assert "captcha_solved" in events


def test_tick_detects_without_solver():
    events = []
    ag = _agent(BoomEngine(), on_event=lambda k, d=None: events.append(k))
    fired = ag.tick()
    assert fired == ["captcha_detected"] and "captcha_detected" in events


def test_normal_tick_unaffected():
    ag = _agent(OkEngine())
    assert ag.tick() == ["collect_city_output"]
