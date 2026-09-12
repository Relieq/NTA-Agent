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


def test_get_player_armys():
    s = FakeSession({"list": [{"uid": "a1", "name": "Đội 1"}]})
    out = Actions(s).get_player_armys()
    assert s.sent[0] == ("game/HD_GetPlayerArmys", {})
    assert out == [{"uid": "a1", "name": "Đội 1"}]


def test_get_player_armys_empty():
    assert Actions(FakeSession({})).get_player_armys() == []
