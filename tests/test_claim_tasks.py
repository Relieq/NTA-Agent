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
