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


class BusyActions:
    """forge_equip raises 500058 (a forge already running)."""
    def forge_equip(self, uid):
        from nta_agent.io.api.client import ApiError
        raise ApiError("game/HD_ForgeEquip: ecode.500058")


def test_forge_500058_quiet_backoff():
    st = _state({"1": {"id": 6005, "lv": 1}}, iron=100)
    rule = Forge(config=FakeConfig(BASE), profile=SimpleNamespace(forge={"enabled": True}))
    assert rule.applies(st, BusyActions()) is True
    rule.act(BusyActions())              # 500058 -> swallowed, no raise
    assert rule._cooldown == rule.forge_cooldown


class LowResActions:
    """forge_equip raises 500012 (not enough iron)."""
    def forge_equip(self, uid):
        from nta_agent.io.api.client import ApiError
        raise ApiError("game/HD_ForgeEquip: ecode.500012")


def test_forge_500012_quiet_backoff():
    st = _state({"1": {"id": 6005, "lv": 1}}, iron=100)  # thinks affordable, then rejected
    rule = Forge(config=FakeConfig(BASE), profile=SimpleNamespace(forge={"enabled": True}))
    assert rule.applies(st, LowResActions()) is True
    rule.act(LowResActions())            # 500012 -> swallowed, no raise
    assert rule._cooldown == rule.res_cooldown


def test_forge_equip_reply_marks_busy_and_free_flag():
    """HD_ForgeEquip reply carries currForgeEquip (+ nextForgeFree for a recast):
    mirror them into player state so the rule sees the forge as busy at once."""
    from types import SimpleNamespace

    from nta_agent.execution.actions import Actions
    from nta_agent.state import from_entry_rst
    st = from_entry_rst({"player": {"uid": "1",
        "equips": [{"uid": "6001_1", "id": 6001, "nextForgeFree": False}]}})
    sess = SimpleNamespace(state=st, request=lambda route, p: {
        "currForgeEquip": {"uid": "6001_1", "needTime": 296650}, "nextForgeFree": True})
    Actions(sess).forge_equip("6001_1")
    p = st.raw["player"]
    assert p["currForgeEquip"]["uid"] == "6001_1"
    assert p["equips"][0]["nextForgeFree"] is True


class FakeConfig2:
    """equipBase + equipEffect tables."""
    def __init__(self, base, effect):
        self._t = {"equipBase": base, "equipEffect": effect}
    def table(self, name):
        return self._t.get(name, {})


RBASE = {6001: {"id": 6001, "exclusive_pawn": "", "forge_cost": "2,0,100|3,0,100|9,0,3"}}
REFF = {3: {"id": 3, "value": "150,180", "odds": "20,40"}}


def _eq(value, odds, free=False):
    return {"uid": "6001_1", "id": 6001, "attrs": [{"attr": [2, 3, value, odds]}],
            "nextForgeFree": free}


def _rrule(targets, spent, events):
    return Forge(config=FakeConfig2(RBASE, REFF), profile=SimpleNamespace(forge={"enabled": True}),
                 targets_source=lambda: targets,
                 spend_fn=lambda uid, iron: spent.append((uid, iron)),
                 on_event=lambda k, d: events.append((k, d)))


def test_recast_toward_target_and_spend_iron_budget():
    spent, events = [], []
    st = _state({}, equips=[_eq(150, 20)], iron=50)          # quality 0.0
    rule = _rrule({"6001_1": {"threshold": 0.8, "budget": 9}}, spent, events)
    acts = FakeActions()
    assert rule.applies(st, acts) is True
    rule.act(acts)
    assert acts.forged == ["6001_1"]
    assert spent == [("6001_1", 3)]                           # iron part only
    assert any(k == "forge_recast" and d["quality"] == 0.0 for k, d in events)


def test_no_recast_once_target_met():
    st = _state({}, equips=[_eq(177, 38)], iron=50)          # (0.9+0.9)/2 = 0.9
    rule = _rrule({"6001_1": {"threshold": 0.8, "budget": 9}}, [], [])
    assert rule.applies(st, FakeActions()) is False


def test_no_recast_while_forge_busy_or_budget_gone():
    st = _state({}, equips=[_eq(150, 20)], iron=50)
    st.raw["player"]["currForgeEquip"] = {"uid": "6001_1"}
    assert _rrule({"6001_1": {"threshold": 1, "budget": 9}}, [], []).applies(st, FakeActions()) is False
    st2 = _state({}, equips=[_eq(150, 20)], iron=50)
    assert _rrule({"6001_1": {"threshold": 1, "budget": 2}}, [], []).applies(st2, FakeActions()) is False


def test_free_recast_spends_nothing():
    spent = []
    st = _state({}, equips=[_eq(150, 20, free=True)], iron=0)
    rule = _rrule({"6001_1": {"threshold": 1, "budget": 0}}, spent, [])
    acts = FakeActions()
    assert rule.applies(st, acts) is True
    rule.act(acts)
    assert acts.forged == ["6001_1"] and spent == []


def test_crafted_equip_without_id_is_not_recrafted():
    """Live EquipInfo omits `id`; the crafted set must derive it from the uid or the
    rule re-"crafts" (= pays for a recast of) an equip that already exists."""
    st = _state({"1": {"id": 6005, "lv": 1}}, equips=[{"uid": "6005_1", "attrs": []}], iron=99)
    rule = Forge(config=FakeConfig(BASE), profile=SimpleNamespace(forge={"enabled": True}))
    assert rule.applies(st, FakeActions()) is False
