import pytest

from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self, reply=None):
        self.state = GameState(source="api")
        self._reply = reply or {}
        self.sent = []

    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params))
        return self._reply


def test_rename_army_sends_modify_route():
    s = FakeSession({"rst": True})
    Actions(s).rename_army(79542, "a1", "Đội 1")
    assert s.sent[0] == ("game/HD_ModifyAmryName",
                         {"index": 79542, "armyUid": "a1", "name": "Đội 1"})


def test_rename_army_rejects_too_long_name():
    s = FakeSession()
    with pytest.raises(ValueError):
        Actions(s).rename_army(1, "a1", "x" * 13)   # >12 chars
    assert s.sent == []                              # never hit the network


def test_rename_army_rejects_newline():
    s = FakeSession()
    with pytest.raises(ValueError):
        Actions(s).rename_army(1, "a1", "Đội\n1")
    assert s.sent == []


def test_rename_army_rejects_empty():
    with pytest.raises(ValueError):
        Actions(FakeSession()).rename_army(1, "a1", "  ")
