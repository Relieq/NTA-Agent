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


def test_exchange_pawn_army_swaps_two_pawns():
    s = FakeSession()
    Actions(s).exchange_pawn_army(109726, "armyA", "p1", "p2")
    route, params = s.sent[0]
    assert route == "game/HD_ExchangePawnArmy"
    assert params == {"index": 109726, "armyUid1": "armyA", "uid1": "p1",
                      "armyUid2": "armyA", "uid2": "p2"}


def test_exchange_pawn_army_across_armies():
    s = FakeSession()
    Actions(s).exchange_pawn_army(109726, "armyA", "p1", "p2", army_uid2="armyB")
    _, params = s.sent[0]
    assert params["armyUid1"] == "armyA" and params["armyUid2"] == "armyB"


def test_treasure_open_and_claim_routes():
    s = FakeSession()
    Actions(s).open_army_treasure(109725, "armyA")
    Actions(s).claim_army_treasure(109725, "armyA")
    assert s.sent[0] == ("game/HD_OpenArmyTreasure", {"index": 109725, "auid": "armyA"})
    assert s.sent[1] == ("game/HD_ClaimArmyTreasure", {"index": 109725, "auid": "armyA"})
