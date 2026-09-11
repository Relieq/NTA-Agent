"""ClaimTasks rule: sweep player task lists and claim completed rewards.

Server-authoritative: the rule attempts a claim; the fake server here accepts
or rejects per id, and the rule backs off rejected ids.
"""
from __future__ import annotations

from dataclasses import dataclass, field

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
