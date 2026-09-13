from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self, reply):
        self.state = GameState(source="api")
        self.state.raw = {}
        self._reply = reply
        self.sent = []

    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params))
        return self._reply


def test_get_battle_records_list_sends_route_and_returns_list():
    s = FakeSession({"list": [{"uid": "b1", "index": 109725, "isWin": True}]})
    out = Actions(s).get_battle_records_list()
    assert s.sent[0] == ("game/HD_GetBattleRecordsList", {})
    assert out == [{"uid": "b1", "index": 109725, "isWin": True}]


def test_get_battle_record_sends_uid_and_returns_record():
    s = FakeSession({"record": {"uid": "b1", "frames": [{"type": 0}]}})
    out = Actions(s).get_battle_record("b1")
    assert s.sent[0] == ("game/HD_GetBattleRecord", {"uid": "b1"})
    assert out == {"uid": "b1", "frames": [{"type": 0}]}


def test_get_battle_records_list_empty_when_missing():
    s = FakeSession({})
    assert Actions(s).get_battle_records_list() == []
