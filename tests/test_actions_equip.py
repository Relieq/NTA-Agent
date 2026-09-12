from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self):
        self.state = GameState(source="api")
        self.sent = []

    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params))
        return {}


def test_change_pawn_equip():
    s = FakeSession()
    Actions(s).change_pawn_equip(3101, "e1", skin_id=2, attack_speed=6)
    assert s.sent[0] == ("game/HD_ChangeConfigPawnEquip",
                         {"id": 3101, "equipUid": "e1", "skinId": 2, "attackSpeed": 6})
