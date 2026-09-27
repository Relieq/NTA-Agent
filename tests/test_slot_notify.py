"""Ceri slot notifies (85 policy / 86 equip / 87 pawn): a new 'pick 1 of 3' offered
mid-session must reach state — they were ignored, so offers only showed after a
restart (live 2026-09-27)."""
from __future__ import annotations

from nta_agent.execution.decisions import pending_decisions
from nta_agent.state import apply_notify, from_entry_rst


class Cfg:
    def table(self, name):
        return {"pawnText": {"name_3101": {"vi": "A"}, "name_3102": {"vi": "B"},
                             "name_3103": {"vi": "C"}}}.get(name, {})


def test_new_pawn_offer_mid_session_becomes_a_pending_decision():
    st = from_entry_rst({"player": {"uid": "1", "pawnSlots": {1: {"lv": 1, "id": 3201}}}})
    assert pending_decisions(st, Cfg()) == []
    apply_notify(st, {"list": [{"type": 87, "data_87": {
        1: {"lv": 1, "id": 3201}, 10: {"lv": 10, "selectIds": [3101, 3102, 3103]}}}]})
    (d,) = pending_decisions(st, Cfg())
    assert d.track == "pawn" and d.lv == 10 and [o["name"] for o in d.options] == ["A", "B", "C"]


def test_policy_and_equip_slot_notifies_replace_their_maps():
    st = from_entry_rst({"player": {"uid": "1"}})
    apply_notify(st, {"list": [{"type": 85, "data_85": {5: {"lv": 5, "selectIds": [1, 2, 3]}}}]})
    apply_notify(st, {"list": [{"type": 86, "data_86": {10: {"lv": 10, "id": 6117}}}]})
    player = st.raw["player"]
    assert player["policySlots"] == {5: {"lv": 5, "selectIds": [1, 2, 3]}}
    assert player["equipSlots"] == {10: {"lv": 10, "id": 6117}}
