from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self):
        self.state = GameState(source="api")
        self.state.raw = {}
        self.sent = []

    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params))
        return {}


def test_add_build_sends_route():
    s = FakeSession()
    Actions(s).add_build(109726, 2016)
    assert s.sent[0] == ("game/HD_AddAreaBuild", {"index": 109726, "id": 2016})


def test_create_city_sends_route():
    s = FakeSession()
    Actions(s).create_city(331273, 2102)   # Cứ Điểm / fort
    assert s.sent[0] == ("game/HD_CreateCity", {"index": 331273, "id": 2102})
