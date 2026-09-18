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


def test_pawn_lving_action_shape():
    s = FakeSession({})
    a = Actions(session=s)
    a.pawn_lving(72100, "A", "p1")
    assert s.sent[-1] == ("game/HD_PawnLving", {"index": 72100, "auid": "A", "puid": "p1"})


def test_change_pawn_army_and_dismiss_shapes():
    s = FakeSession({})
    a = Actions(session=s)
    a.change_pawn_army(72100, "F", "p1", "", is_new_create=True, army_name="Nâng Cấp")
    assert s.sent[-1] == ("game/HD_ChangePawnArmy",
                          {"index": 72100, "armyUid": "F", "uid": "p1", "newArmyUid": "",
                           "isNewCreate": True, "armyName": "Nâng Cấp"})
    a.change_pawn_army(72100, "F", "p1", "L", only_change=True)
    assert s.sent[-1] == ("game/HD_ChangePawnArmy",
                          {"index": 72100, "armyUid": "F", "uid": "p1", "newArmyUid": "L",
                           "onlyChangeArmy": True})
    a.dismiss_army(72100, "L", 0)
    assert s.sent[-1] == ("game/HD_DismissArmy", {"index": 72100, "armyUid": "L", "id": 0})
