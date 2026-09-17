from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self):
        self.state = GameState(source="api")
        self.sent = []

    def request(self, route, params):
        self.sent.append((route, params))
        return {}


def test_move_cell_army_builds_request():
    s = FakeSession()
    a = Actions(session=s)
    a.move_cell_army([{"index": 10, "uid": "u1"}, {"index": 11, "uid": "u2"}], target=42)
    route, params = s.sent[-1]
    assert route == "game/HD_MoveCellArmy"
    assert params == {"indexs": [10, 11], "uids": ["u1", "u2"], "target": 42, "isSameSpeed": False}
