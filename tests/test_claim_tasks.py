"""ClaimTasks rule: sweep player task lists and claim completed rewards.

Server-authoritative: the rule attempts a claim; the fake server here accepts
or rejects per id, and the rule backs off rejected ids.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from nta_agent.execution.heuristics import ClaimTasks
from nta_agent.state.schema import GameState


@dataclass
class FakeActions:
    reject: set = field(default_factory=set)   # ids the "server" says aren't complete
    calls: list = field(default_factory=list)

    def _claim(self, kind, task_id):
        self.calls.append((kind, task_id))
        if task_id in self.reject:
            raise RuntimeError("ecode.500xxx COND_NOT_ENOUGH")
        return {"rewards": {}}

    def claim_task(self, task_id):
        return self._claim("guide", task_id)

    def claim_other_task(self, task_id, treasure_index=0, select_index=0):
        return self._claim("other", task_id)

    def claim_today_task(self, task_id, treasure_index=0, select_index=0):
        return self._claim("today", task_id)


def _state(guide=(), other=(), today=()):
    st = GameState(source="api")
    st.raw = {"player": {
        "guideTasks": [{"id": i, "progress": 0} for i in guide],
        "otherTasks": [{"id": i, "progress": 0} for i in other],
        "todayTasks": [{"id": i, "progress": 0} for i in today],
    }}
    return st


def test_claims_a_guide_task():
    st = _state(guide=[101])
    act = FakeActions()
    rule = ClaimTasks()
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls == [("guide", 101)]


def test_claims_each_kind_over_sweeps():
    st = _state(guide=[101], other=[201], today=[301])
    act = FakeActions()
    rule = ClaimTasks(sweep_every=0)  # no throttle for the test
    seen = set()
    for _ in range(6):
        if rule.applies(st, act):
            rule.act(act)
        seen |= {c for c in act.calls}
    kinds = {k for k, _ in act.calls}
    assert kinds == {"guide", "other", "today"}


def test_backs_off_rejected_ids():
    st = _state(guide=[101, 102])
    act = FakeActions(reject={101})
    rule = ClaimTasks(sweep_every=0)
    # sweep until it settles; 101 rejected -> backoff, 102 claimed
    for _ in range(5):
        if rule.applies(st, act):
            rule.act(act)
    assert ("guide", 102) in act.calls
    # 101 should not be retried forever: after backoff, applies stops offering it
    assert rule.applies(st, act) is False


def test_no_tasks_no_apply():
    assert ClaimTasks().applies(_state(), FakeActions()) is False


# ---- 2026-09-27: completed tasks starved behind unfinished ones -----------------
class _Cfg:
    T: ClassVar[dict] = {"guideTask": {1: {"cond": "11001,1,3", "show_progress": 1},
                       2: {"cond": "11001,1,5", "show_progress": 1},
                       3: {"cond": "11002,0,2", "show_progress": 1}}}

    def table(self, name):
        return self.T.get(name, {})


def _st(tasks):
    st = GameState(source="api")
    st.raw = {"player": {"guideTasks": [{"id": i, "progress": p} for i, p in tasks],
                         "otherTasks": [], "todayTasks": []}}
    return st


def test_a_completed_task_is_claimed_first_and_at_once():
    # 1 and 2 unfinished (progress < target), 3 done -> claim 3 right away
    act = FakeActions()
    rule = ClaimTasks(config=_Cfg())
    st = _st([(1, 1), (2, 0), (3, 2)])
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls == [("guide", 3)]


def test_unfinished_tasks_are_not_tried_and_progress_churn_does_not_restart():
    act = FakeActions()
    rule = ClaimTasks(config=_Cfg(), sweep_every=0)
    for p in range(3):                               # progress keeps moving (notify 55)
        st = _st([(1, p % 3), (2, 0)])
        if rule.applies(st, act):
            rule.act(act)
    assert act.calls == []                           # nothing claimable -> no requests
    st = _st([(1, 3), (2, 0)])                       # task 1 reached its target
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls == [("guide", 1)]


# ---- 2026-10-01: progress the CLIENT computes (the server's stays 0) ----------------------------
class _PolicyCfg:
    T: ClassVar[dict] = {"guideTask": {
        10102301: {"cond": "1022,1,1", "show_progress": 1},    # enact 1 policy
        10000401: {"cond": "4,2001,5", "show_progress": 1},    # main city level 5
        10000402: {"cond": "4,2008,9", "show_progress": 1},    # a building to level 9
        55: {"cond": "1022,2,2", "show_progress": 1}},         # study 2 pawn types
        "equipBase": {6001: {"exclusive_pawn": ""}, 6101: {"exclusive_pawn": "3305"}}}

    def table(self, name):
        return self.T.get(name, {})


def _cst(tasks, **player):
    st = GameState(source="api")
    st.raw = {"player": {"guideTasks": [{"id": i} for i in tasks],       # no `progress` at all
                         "otherTasks": [], "todayTasks": [], **player}}
    return st


def test_an_enacted_policy_is_claimed_although_the_server_progress_is_zero():
    act = FakeActions()
    rule = ClaimTasks(config=_PolicyCfg())
    st = _cst([10102301], policySlots={"1": {"id": 0, "lv": 1}})        # a slot offered, none chosen
    assert rule.applies(st, act) is False                                # not done yet
    st = _cst([10102301], policySlots={"1": {"id": 7, "lv": 1}})        # the player chose one
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls == [("guide", 10102301)]


def test_pawn_and_exclusive_study_counts_and_building_levels_are_read_from_our_state():
    from nta_agent.state.schema import Building
    rule = ClaimTasks(config=_PolicyCfg())
    st = _cst([55], pawnSlots={"1": {"id": 3305}, "2": {"id": 3201}})
    rule._state_ref = st
    assert rule._client_progress(1022, 2) == 2
    st2 = _cst([], equipSlots={"1": {"id": 6001}, "2": {"id": 6101}})
    rule._state_ref = st2
    assert rule._client_progress(1022, 3) == 2 and rule._client_progress(1022, 4) == 1
    st3 = _cst([])
    st3.builds = [Building(id=2001, lv=4, uid="a", index=1), Building(id=2001, lv=6, uid="b", index=2)]
    rule._state_ref = st3
    assert rule._client_progress(4, 2001) == 6 and rule._client_progress(4, 2008) == 0
    assert rule._client_progress(99999, 1) is None                       # unknown type: no claim


def test_a_building_level_task_is_claimed_when_the_level_is_reached():
    from nta_agent.state.schema import Building
    act = FakeActions()
    rule = ClaimTasks(config=_PolicyCfg())
    st = _cst([10000401])
    st.builds = [Building(id=2001, lv=5, uid="a", index=1)]
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls == [("guide", 10000401)]


def test_the_first_recheck_comes_soon_after_a_restart_not_half_an_hour_later(monkeypatch):
    import time
    clock = [10_000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    act = FakeActions()
    rule = ClaimTasks(config=_Cfg())
    st = _st([(1, 0)])                                    # unfinished, status 'open'
    assert rule.applies(st, act) is False                  # the agent has just started
    clock[0] += 59
    assert rule.applies(st, act) is False                  # not yet ...
    clock[0] += 2
    assert rule.applies(st, act) is True                   # ... after ~1 minute it is tried
    rule.act(act)
    assert act.calls == [("guide", 1)]


def test_forge_tasks_are_read_from_the_equips_we_own():
    # 'Rèn 1 trang bị' (1039) is judged by the client from the number of crafted equips
    class Cfg(_PolicyCfg):
        T: ClassVar[dict] = {**_PolicyCfg.T, "guideTask": {
            10102102: {"cond": "1039,0,1", "show_progress": 1},
            77: {"cond": "1021,6001,1", "show_progress": 1},
            78: {"cond": "1035,0,1", "show_progress": 1}}}
    act = FakeActions()
    rule = ClaimTasks(config=Cfg())
    assert rule.applies(_cst([10102102], equips=[]), act) is False            # nothing forged yet
    st = _cst([10102102], equips=[{"uid": "6001_1", "id": 6001}])
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls == [("guide", 10102102)]
    rule2 = ClaimTasks(config=Cfg())
    st2 = _cst([77, 78], equips=[{"uid": "6001_1"}])                         # id derived from the uid
    rule2._state_ref = st2
    assert rule2._client_progress(1021, 6001) == 1 and rule2._client_progress(1021, 6002) == 0
    assert rule2._client_progress(1035, 0) == 0                              # no exclusive equip
    st3 = _cst([78], equips=[{"uid": "6101_1", "id": 6101}])
    rule2._state_ref = st3
    assert rule2._client_progress(1035, 0) == 1
