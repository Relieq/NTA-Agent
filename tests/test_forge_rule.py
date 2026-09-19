"""Forge rule: auto-craft unlocked common equipment when affordable."""
from types import SimpleNamespace

from nta_agent.execution.heuristics import Forge
from nta_agent.state.schema import GameState, Resources, User


class FakeConfig:
    def __init__(self, base):
        self._base = base
    def table(self, name):
        return self._base if name == "equipBase" else {}


class FakeActions:
    def __init__(self):
        self.forged = []
    def forge_equip(self, uid):
        self.forged.append(uid); return {}


def _state(equip_slots, equips=(), iron=100, room=1):
    st = GameState(source="api")
    st.user = User(uid="me")
    st.room_type = room
    st.resources = Resources(cereal=999, timber=999, stone=999, iron=iron, gold=0, stamina=0)
    st.raw = {"player": {"equipSlots": equip_slots, "equips": list(equips)}}
    return st


BASE = {6005: {"id": 6005, "exclusive_pawn": "", "forge_cost": "9,0,3", "forge_cost_novice": "9,0,3"}}


def test_forge_crafts_affordable_common_slot():
    st = _state({"1": {"id": 6005, "lv": 1}}, iron=3)
    acts = FakeActions()
    rule = Forge(config=FakeConfig(BASE), profile=SimpleNamespace(forge={"enabled": True}))
    assert rule.applies(st, acts) is True
    rule.act(acts)
    assert acts.forged == ["6005_1"]


def test_forge_skips_when_iron_short():
    st = _state({"1": {"id": 6005, "lv": 1}}, iron=1)  # needs 3
    rule = Forge(config=FakeConfig(BASE), profile=SimpleNamespace(forge={"enabled": True}))
    assert rule.applies(st, FakeActions()) is False


def test_forge_skips_already_crafted():
    st = _state({"1": {"id": 6005, "lv": 1}}, equips=[{"id": 6005, "uid": "x"}], iron=100)
    rule = Forge(config=FakeConfig(BASE), profile=SimpleNamespace(forge={"enabled": True}))
    assert rule.applies(st, FakeActions()) is False


def test_forge_skips_when_busy():
    st = _state({"1": {"id": 6005, "lv": 1}}, iron=100)
    st.raw["player"]["currForgeEquip"] = {"uid": "6005_1", "surplusTime": 5000}
    rule = Forge(config=FakeConfig(BASE), profile=SimpleNamespace(forge={"enabled": True}))
    assert rule.applies(st, FakeActions()) is False


def test_forge_disabled():
    st = _state({"1": {"id": 6005, "lv": 1}}, iron=100)
    rule = Forge(config=FakeConfig(BASE), profile=SimpleNamespace(forge={"enabled": False}))
    assert rule.applies(st, FakeActions()) is False
