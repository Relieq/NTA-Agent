from nta_agent.execution.agent import Agent


class FakeEngine:
    def __init__(self): self.ticks = 0
    def tick(self, state, actions): self.ticks += 1; return ["did_something"]


class FakeSession:
    def __init__(self): self.state = object(); self.syncs = 0
    def sync(self): self.syncs += 1; return self.state


def _agent():
    return Agent(FakeSession(), FakeEngine())


def test_pause_syncs_but_does_not_act():
    a = _agent(); seen = []
    a.run(ticks=1, interval=0, control=lambda: "pause",
          on_tick=lambda i, fired, st: seen.append(fired))
    assert a.engine.ticks == 0        # engine.tick NOT called while paused
    assert a.session.syncs == 1       # but state kept fresh
    assert seen == [[]]               # on_tick fired with empty fired list


def test_stop_breaks_immediately():
    a = _agent(); seen = []
    a.run(ticks=5, interval=0, control=lambda: "stop",
          on_tick=lambda i, fired, st: seen.append(i))
    assert a.engine.ticks == 0 and seen == []


def test_run_mode_is_normal():
    a = _agent()
    a.run(ticks=2, interval=0, control=lambda: "run")
    assert a.engine.ticks == 2
