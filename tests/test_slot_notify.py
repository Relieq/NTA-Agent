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


# ---- the rest of the ignored player notifies (audit 2026-09-27) ----------------
def _st():
    return from_entry_rst({"player": {"uid": "1", "injuryPawns": [{"uid": "a", "id": 3305}],
                                      "guideTasks": [{"id": 1, "progress": 0}],
                                      "todayTasks": [{"id": 9, "progress": 1}],
                                      "otherTasks": [], "extraBTQueueCount": 0,
                                      "pawnLevelingQueues": [{"puid": "old"}]}})


def test_injury_add_and_remove():
    st = _st()
    apply_notify(st, {"list": [{"type": 83, "data_83": {"uid": "b", "id": 3206}}]})
    apply_notify(st, {"list": [{"type": 83, "data_83": {"uid": "b", "id": 3206}}]})  # dup
    apply_notify(st, {"list": [{"type": 84, "data_84": "a"}]})
    assert [p["uid"] for p in st.raw["player"]["injuryPawns"]] == ["b"]


def test_task_progress_and_new_tasks():
    st = _st()
    apply_notify(st, {"list": [{"type": 55, "data_55": {
        "guideTasks": [{"id": 1, "progress": 3}, {"id": 2, "progress": 0}],
        "todayTasks": [{"id": 9, "progress": 2}, {"id": 99, "progress": 1}]}}]})
    p = st.raw["player"]
    assert p["guideTasks"] == [{"id": 1, "progress": 3}, {"id": 2, "progress": 0}]
    assert p["todayTasks"] == [{"id": 9, "progress": 2}]     # client adds no unknown today task


def test_today_reset_replaces_today_tasks():
    st = _st()
    apply_notify(st, {"list": [{"type": 52, "data_52": {"todayTasks": [{"id": 10, "progress": 0}],
                                                         "todayOccupyCellCount": 0}}]})
    assert st.raw["player"]["todayTasks"] == [{"id": 10, "progress": 0}]


def test_leveling_queue_replaced_and_extra_build_slot():
    st = _st()
    apply_notify(st, {"list": [{"type": 40, "data_40": []}]})          # queue drained
    apply_notify(st, {"list": [{"type": 95, "data_95": 1}]})
    assert st.raw["player"]["pawnLevelingQueues"] == []
    assert st.raw["player"]["_pawnLevelingQueuesAt"] > 0
    assert st.build_queue_slots == 3
