from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self, reply):
        self.state = GameState(source="api")
        self.state.raw = {"player": {"pawnSlots": {}, "policySlots": {}, "equipSlots": {}}}
        self._reply = reply
        self.sent = []

    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params))
        return self._reply


def test_study_select_sends_and_applies_slots():
    reply = {"slots": {"0": {"selectIds": [], "id": 3101, "resetCount": 0, "lv": 1}}}
    s = FakeSession(reply)
    out = Actions(s).study_select(lv=1, ceri_id=5, tp=2)
    assert s.sent[0] == ("game/HD_StudySelect", {"lv": 1, "id": 5, "tp": 2})
    assert out is reply
    assert s.state.raw["player"]["pawnSlots"] == reply["slots"]


def test_ceri_reset_sends_and_returns():
    reply = {"gold": 100, "selectIds": [7, 8, 9], "resetCount": 1, "useGold": False}
    s = FakeSession(reply)
    out = Actions(s).ceri_reset(lv=2, tp=1)
    assert s.sent[0] == ("game/HD_CeriResetSelect", {"lv": 2, "tp": 1})
    assert out["selectIds"] == [7, 8, 9]


def test_ceri_reset_applies_new_options_to_pending_slot():
    # Fresh selectIds/resetCount must land on the matching pending slot, else the
    # reroll is a no-op in local state and the UI keeps showing the old options.
    reply = {"gold": 0, "selectIds": [7, 8, 9], "resetCount": 3, "useGold": False}
    s = FakeSession(reply)
    s.state.raw["player"]["policySlots"] = {
        "5": {"selectIds": [1, 2, 3], "id": 0, "resetCount": 2, "lv": 5},
        "3": {"selectIds": [], "id": 1027, "resetCount": 0, "lv": 3},  # already chosen
    }
    Actions(s).ceri_reset(lv=5, tp=1)
    slot = s.state.raw["player"]["policySlots"]["5"]
    assert slot["selectIds"] == [7, 8, 9]
    assert slot["resetCount"] == 3
    # the already-chosen slot at a different lv is untouched
    assert s.state.raw["player"]["policySlots"]["3"]["id"] == 1027
