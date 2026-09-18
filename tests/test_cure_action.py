from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self, player):
        self.state = GameState(source="api")
        self.state.raw = {"player": player}
        self.sent = []

    def request(self, route, params):
        self.sent.append((route, params))
        return {}


def test_cure_injury_pawn_request_and_optimistic_remove():
    player = {"injuryPawns": [{"uid": "d1"}, {"uid": "d2"}]}
    s = FakeSession(player)
    a = Actions(session=s)
    a.cure_injury_pawn(72100, "A", "D1", "d1")
    route, params = s.sent[-1]
    assert route == "game/HD_CureInjuryPawn"
    assert params == {"index": 72100, "armyUid": "A", "armyName": "D1", "pawnUid": "d1"}
    # cured pawn dropped locally so it isn't retried
    assert [p["uid"] for p in player["injuryPawns"]] == ["d2"]


def test_forge_and_lock_action_shapes():
    s = FakeSession({})
    a = Actions(session=s)
    a.forge_equip("e1")
    a.lock_equip_effect("e1", 2)
    assert s.sent[-2] == ("game/HD_ForgeEquip", {"uid": "e1"})
    assert s.sent[-1] == ("game/HD_LockEquipEffect", {"uid": "e1", "effect": 2})
