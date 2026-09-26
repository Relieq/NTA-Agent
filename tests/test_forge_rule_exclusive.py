"""Forge rule with exclusive equips: craft chosen ones, lock, pay fixators, wait while smelting."""
from types import SimpleNamespace

from nta_agent.execution.heuristics import Forge
from nta_agent.state.schema import GameState, Resources, User

BASE = {6101: {"id": 6101, "exclusive_pawn": 3101, "forge_cost": "9,0,12", "forge_cost_novice": "9,0,12",
               "effect": "21|22"}}
POOLS = {6101: [21, 3, 8]}


class Cfg:
    def table(self, name):
        return BASE if name == "equipBase" else {}


class Acts:
    def __init__(self, reply=None):
        self.calls = []
        self.reply = reply or {}

    def forge_equip(self, uid):
        self.calls.append(("forge", uid))
        return self.reply

    def lock_equip_effect(self, uid, effect):
        self.calls.append(("lock", uid, effect))
        return {}


def _state(equips=(), slots=None, fixator=10, smelting=False):
    st = GameState(source="api")
    st.user = User(uid="me")
    st.resources = Resources(cereal=999, timber=999, stone=999, iron=500, gold=0, stamina=0,
                             fixator=fixator)
    st.raw = {"player": {"equipSlots": slots or {}, "equips": list(equips),
                         "currSmeltEquip": {"uid": "x"} if smelting else None}}
    return st


def _eq(effects, lock=0):
    return {"uid": "6101_10", "lockEffect": lock, "attrs": [{"attr": [2, *e]} for e in effects]}


def _rule(targets, spent=None):
    r = Forge(config=Cfg(), profile=SimpleNamespace(forge={"enabled": True}))
    r.targets_source = lambda: targets
    r.pools_source = lambda: POOLS
    r.spend_fn = lambda uid, iron, fixator=0: (spent if spent is not None else []).append((uid, iron, fixator))
    return r


TGT = {"6101_10": {"budget": 100, "fixator_budget": 5, "mins": {"3.value": 150, "21.value": 5}}}


def test_crafts_the_exclusive_the_player_chose():
    r = _rule({})
    acts = Acts()
    assert r.applies(_state(slots={"10": {"id": 6101, "lv": 10}}), acts)
    r.act(acts)
    assert acts.calls == [("forge", "6101_10")]


def test_locks_a_satisfied_wanted_line_before_recasting():
    r = _rule(TGT)
    acts = Acts()
    assert r.applies(_state([_eq([(3, 160, 0), (8, 1, 0)])]), acts)
    r.act(acts)
    assert acts.calls == [("lock", "6101_10", 3)]


def test_recast_after_lock_debits_iron_and_fixator():
    spent = []
    r = _rule(TGT, spent)
    acts = Acts(reply={"cost": [{"type": 9, "count": 12}, {"type": 14, "count": 1}]})
    assert r.applies(_state([_eq([(3, 160, 0), (8, 1, 0)], lock=3)]), acts)
    r.act(acts)
    assert acts.calls == [("forge", "6101_10")] and spent == [("6101_10", 12, 1)]


def test_fixator_mismatch_stops_that_equip_and_warns():
    events = []
    r = _rule(TGT)
    r.on_event = lambda k, d=None: events.append((k, d))
    acts = Acts(reply={"cost": [{"type": 9, "count": 12}, {"type": 14, "count": 2}]})
    st = _state([_eq([(3, 160, 0), (8, 1, 0)], lock=3)])
    r.applies(st, acts)
    r.act(acts)
    assert any(k == "forge_fixator_mismatch" for k, _ in events)
    r._cooldown = 0
    assert r.applies(st, acts) is False               # that equip is on hold now


def test_nothing_while_smelting():
    r = _rule(TGT)
    assert r.applies(_state([_eq([(15, 1, 0), (8, 1, 0)])], slots={"10": {"id": 6101, "lv": 10}},
                            smelting=True), Acts()) is False
