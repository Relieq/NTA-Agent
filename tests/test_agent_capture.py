"""Agent enters a do-nothing safe mode while our main city is captured."""
from types import SimpleNamespace

from nta_agent.execution.agent import Agent


class Sess:
    def __init__(self, player):
        self.state = SimpleNamespace(raw={"player": player})
    def sync(self):
        return self.state


class Engine:
    def __init__(self):
        self.ticks = 0
    def tick(self, state, actions):
        self.ticks += 1
        return ["occupy_cell"]


def test_captured_skips_rules_and_emits_once_then_resumes():
    events = []
    sess = Sess({"captureInfo": {"uid": "36781907", "time": 1}})
    eng = Engine()
    a = Agent(session=sess, engine=eng, on_event=lambda k, d: events.append((k, d)))
    assert a.tick() == ["captured"]
    assert a.tick() == ["captured"]
    assert eng.ticks == 0                                   # no rule may act
    assert [k for k, _ in events] == ["captured"]           # surfaced once, not every tick
    assert events[0][1]["attacker"] == "36781907"
    # player re-created the city -> captureInfo cleared -> resume normally
    sess.state.raw["player"].pop("captureInfo")
    assert a.tick() == ["occupy_cell"]
    assert eng.ticks == 1
    assert [k for k, _ in events] == ["captured", "capture_cleared"]
