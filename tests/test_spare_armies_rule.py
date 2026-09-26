"""SpareArmies rule: gather spares home, sort them pure, warn when they can't win."""
from __future__ import annotations

import json
from types import SimpleNamespace

from nta_agent.execution.heuristics import SpareArmies
from nta_agent.state.schema import GameState, User

MAIN = 100 * 600 + 100


def _a(uid, types, index=MAIN, state=0, name=None):
    return {"uid": uid, "name": name or uid, "index": index, "state": state,
            "pawns": [{"uid": f"{uid}-{k}", "id": t, "lv": 1} for k, t in enumerate(types)]}


def _state():
    st = GameState(source="api")
    st.user = User(uid="me")
    st.main_city_index = MAIN
    st.raw = {"player": {}}
    return st


class Acts:
    def __init__(self, armies):
        self.armies = armies
        self.calls = []

    def get_player_armys(self):
        return self.armies

    def move_cell_army(self, armies, target, **kw):
        self.calls.append(("move", sorted(a["uid"] for a in armies), target))

    def change_pawn_army(self, index, army_uid, pawn_uid, new_army_uid="", **kw):
        self.calls.append(("change", army_uid, pawn_uid, new_army_uid))

    def exchange_pawn_army(self, index, army_uid, uid1, uid2, army_uid2=None):
        self.calls.append(("exchange", army_uid, uid1, uid2, army_uid2))


def _prof():
    return SimpleNamespace(army={"group": ["G1"], "presets": {}, "active": ""},
                           occupy={"max_loss": 0}, leveling={})


def _rule(tmp_path, predict=None):
    return SpareArmies(profile=_prof(), advice_path=tmp_path / "spares.json",
                       predict=predict or (lambda st, armies: None), eval_every=1)


def _tick(rule, acts):
    rule._cooldown = 0
    if rule.applies(_state(), acts):
        rule.act(acts)


G1 = _a("G1", [3305] * 9, index=MAIN + 50)   # the farm group: never touched


def test_gathers_idle_spares_home_and_leaves_the_group_alone(tmp_path):
    acts = Acts([G1, _a("D6", [3201] * 9, index=MAIN + 7), _a("D7", [3201] * 9, index=MAIN + 9),
                 _a("D1", [3305] * 4, index=MAIN + 3, state=1)])      # D1 marching: later
    _tick(_rule(tmp_path), acts)
    assert acts.calls == [("move", ["D6", "D7"], MAIN)]


def test_sorts_spares_at_the_city_one_op_a_tick_and_reserves_them(tmp_path):
    d6 = _a("D6", [3201] * 8 + [3305])
    d7 = _a("D7", [3201] * 8 + [3305])
    d1 = _a("D1", [3201] * 3 + [3202] + [3305] * 5)
    rule = _rule(tmp_path)
    acts = Acts([G1, d6, d7, d1])
    _tick(rule, acts)
    assert len(acts.calls) == 1 and acts.calls[0][0] == "exchange"
    assert rule.reserved_uids() == {"D6", "D7", "D1"}          # not sent out mid-sort


def test_warns_once_when_even_together_they_cannot_win(tmp_path):
    spares = [_a("D6", [3201] * 9), _a("D7", [3201] * 9)]
    events = []
    rule = _rule(tmp_path, predict=lambda st, armies: None)     # no clean target anywhere
    rule.stuck_after_s = 0                                      # unused long enough
    rule.on_event = lambda k, d=None: events.append(k)
    acts = Acts([G1] + spares)
    _tick(rule, acts)
    _tick(rule, acts)
    adv = json.loads((tmp_path / "spares.json").read_text(encoding="utf-8"))
    assert adv["status"] == "stuck" and sorted(adv["armies"]) == ["D6", "D7"]
    assert events.count("spare_stuck") == 1                     # not spammed
    assert rule.reserved_uids() == set()


def test_clean_target_clears_the_warning(tmp_path):
    spares = [_a("D6", [3201] * 9), _a("D7", [3201] * 9)]
    rule = _rule(tmp_path, predict=lambda st, armies: {"target": 5, "loss": 0.0})
    _tick(rule, Acts([G1] + spares))
    adv = json.loads((tmp_path / "spares.json").read_text(encoding="utf-8"))
    assert adv["status"] == "ok" and adv["target"] == 5


def test_colocated_spares_in_the_field_are_not_dragged_home(tmp_path):
    # after an attack the spares stand together on the captured cell: sort/attack
    # from there instead of marching home every time
    field = MAIN + 30
    acts = Acts([G1, _a("D6", [3201] * 9, index=field), _a("D7", [3201] * 9, index=field)])
    _tick(_rule(tmp_path, predict=lambda st, a: {"target": 1, "loss": 0}), acts)
    assert acts.calls == []


def test_no_stuck_warning_while_spares_are_being_used(tmp_path):
    events = []
    rule = _rule(tmp_path, predict=lambda st, a: None)
    rule.stuck_after_s = 1800
    rule.on_event = lambda k, d=None: events.append(k)
    busy = Acts([G1, _a("D6", [3201] * 9, state=2), _a("D7", [3201] * 9)])  # D6 fighting
    _tick(rule, busy)
    idle = Acts([G1, _a("D6", [3201] * 9), _a("D7", [3201] * 9)])
    _tick(rule, idle)                          # just used -> no warning yet
    assert "spare_stuck" not in events
    rule._last_used -= 1801                    # idle for 30 min+
    _tick(rule, idle)
    assert events.count("spare_stuck") == 1
