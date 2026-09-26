"""A reply's `queues` is the build queue ONLY for build actions (2026-09-26): DrillPawn
returns the drill queue and PawnLving the pawn-leveling queue under the same key, and
both used to overwrite state.build_queue."""
from __future__ import annotations

from types import SimpleNamespace

from nta_agent.execution import Actions
from nta_agent.execution.army_health import leveling_pawn_uids
from tests.test_actions import FakeSession, _state_with_main_city

MAIN = 109726
BUILD_Q = [{"uid": "b1", "id": 2001, "lv": 5}]


def _actions(route, reply):
    st = _state_with_main_city(MAIN)
    st.build_queue = list(BUILD_Q)
    s = FakeSession(state=st, replies={route: reply})
    return Actions(s), st


def test_drill_reply_does_not_touch_the_build_queue():
    acts, st = _actions("game/HD_DrillPawn", {"queues": [{"uid": "d1", "id": 3305}]})
    acts.drill_pawn("bar", 3305, army_uid="A")
    assert st.build_queue == BUILD_Q


def test_pawn_lving_reply_updates_the_leveling_queue_not_the_build_queue():
    q = [{"uid": "q1", "index": MAIN, "auid": "A", "puid": "p1", "needTime": 488000,
          "surplusTime": 488000},
         {"uid": "q2", "index": MAIN, "auid": "A", "puid": "p2", "needTime": 488000,
          "surplusTime": 488000}]
    acts, st = _actions("game/HD_PawnLving", {"queues": q, "cost": {"expBook": 1}})
    acts.pawn_lving(MAIN, "A", "p2")
    assert st.build_queue == BUILD_Q
    assert leveling_pawn_uids(st) == {"p1", "p2"}


def test_build_reply_still_sets_the_build_queue():
    new = [{"uid": "b2", "id": 2002, "lv": 3}]
    acts, st = _actions("game/HD_UpAreaBuild", {"queues": new})
    acts.upgrade_build(MAIN, "x")
    assert st.build_queue == new


def test_leveling_queue_is_sequential_and_ages_out():
    # head started at t0 with 100 s left, next waits its full 200 s: at t0+150 the
    # head is done, the second still queued
    st = SimpleNamespace(raw={"player": {
        "pawnLevelingQueues": [{"index": 1, "puid": "a", "needTime": 300000, "surplusTime": 100000},
                               {"index": 1, "puid": "b", "needTime": 200000, "surplusTime": 200000}],
        "_pawnLevelingQueuesAt": 1000.0}})
    assert leveling_pawn_uids(st, now=1050.0) == {"a", "b"}
    assert leveling_pawn_uids(st, now=1150.0) == {"b"}
    assert leveling_pawn_uids(st, now=1400.0) == set()


def test_entry_stamps_when_the_leveling_queue_was_read():
    # live 2026-09-26: the entry queue had no read time -> never aged -> a buffer whose
    # pawns were all lv3 still looked 'queued' and never left the city
    import time

    from nta_agent.state.store import from_entry_rst
    before = time.time()
    st = from_entry_rst({"player": {"mainCityIndex": MAIN, "pawnLevelingQueues": [
        {"index": MAIN, "puid": "p1", "needTime": 488000, "surplusTime": 10000}]}})
    at = st.raw["player"]["_pawnLevelingQueuesAt"]
    assert before <= at <= time.time()
    assert leveling_pawn_uids(st, now=at + 5) == {"p1"}
    assert leveling_pawn_uids(st, now=at + 60) == set()
