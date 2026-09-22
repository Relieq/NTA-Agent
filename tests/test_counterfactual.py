from nta_agent.execution.counterfactual import (
    best_counterfactual_order,
    detect_aoe,
    summarize_record,
)
from nta_agent.execution.predictors.sim_bridge import SimUnavailable


class FakeBridge:
    def __init__(self, replay=None, cf=None, fail=False):
        self._replay, self._cf, self._fail = replay, cf, fail

    def replay(self, record):
        if self._fail:
            raise SimUnavailable("x")
        return self._replay

    def counterfactual(self, record, orders):
        if self._fail:
            raise SimUnavailable("x")
        return self._cf


def test_detect_aoe_true_when_one_attacker_hits_many_same_frame():
    hits = [{"by": "q1", "target": "a", "frame": 10},
            {"by": "q1", "target": "b", "frame": 10}]
    assert detect_aoe(hits) is True


def test_detect_aoe_false_for_single_target():
    assert detect_aoe([{"by": "q1", "target": "a", "frame": 10},
                       {"by": "q1", "target": "a", "frame": 12}]) is False


def test_summarize_record_adds_aoe_flag():
    br = FakeBridge(replay={"summary": {"self_dead": 1}, "enemy_ids": [4116],
                            "hits": [{"by": "q1", "target": "a", "frame": 1},
                                     {"by": "q1", "target": "b", "frame": 1}]})
    out = summarize_record(br, {"any": "record"})
    assert out["aoe"] is True
    assert out["enemy_ids"] == [4116]


def test_best_counterfactual_picks_lowest_self_dead():
    cf = {"by_order": {"tank_first": {"self_dead": 0}, "dps_first": {"self_dead": 1},
                       "auto": {"self_dead": 1}}}
    out = best_counterfactual_order(FakeBridge(cf=cf), {"any": "record"})
    assert out == {"best_order": "tank_first", "self_dead": 0}


def test_counterfactual_none_on_sim_unavailable():
    assert best_counterfactual_order(FakeBridge(fail=True), {}) is None
    assert summarize_record(FakeBridge(fail=True), {}) is None


def test_best_counterfactual_none_on_empty():
    assert best_counterfactual_order(FakeBridge(cf={"by_order": {}}), {}) is None
