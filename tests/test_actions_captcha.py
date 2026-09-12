from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self, reply):
        self.state = GameState(source="api")
        self._reply = reply
        self.sent = []

    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params))
        return self._reply


def test_get_anticheat_question():
    s = FakeSession({"item": "item_1", "options": [1, 2], "surplusTime": 30})
    out = Actions(s).get_anticheat_question()
    assert s.sent[0] == ("game/HD_GetAntiCheatQuestion", {})
    assert out["item"] == "item_1"


def test_answer_anticheat():
    s = FakeSession({"rst": True, "wrongCount": 0})
    out = Actions(s).answer_anticheat(12)
    assert s.sent[0] == ("game/HD_AntiCheatAnswer", {"answer": 12})
    assert out["rst"] is True
