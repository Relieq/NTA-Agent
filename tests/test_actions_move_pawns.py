from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self, reply=None):
        self.state = GameState(source="api")
        self.state.raw = {}
        self._reply = reply or {}
        self.sent = []

    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params))
        return self._reply


def test_move_area_pawns_sends_route_and_pawns():
    s = FakeSession()
    Actions(s).move_area_pawns(109725, "army1", {"p1": {"x": 6, "y": 7}, "p2": {"x": 9, "y": 7}})
    route, params = s.sent[0]
    assert route == "game/HD_MoveAreaPawns"
    assert params["index"] == 109725 and params["armyUid"] == "army1"
    assert {"uid": "p1", "point": {"x": 6, "y": 7}} in params["pawns"]
    assert {"uid": "p2", "point": {"x": 9, "y": 7}} in params["pawns"]
