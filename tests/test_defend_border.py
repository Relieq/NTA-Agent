"""P2 defend_border must respect occupy.max_loss like farming/expansion do.

Live 2026-09-25: with max_loss=0 the rule picked 143/145 plans the engine sim
predicted as lossy (up to 55%, ~7 predicted deaths each)."""
from types import SimpleNamespace

from nta_agent.execution.advisor import Plan
from nta_agent.execution.heuristics import OccupyCell

W = 600
ENEMY = {100 * W + 105}                     # enemy cell at (105,100)
NEAR = SimpleNamespace(index=100 * W + 104)  # contested: 1 cell from the enemy


def _rule(max_loss):
    return OccupyCell(profile=SimpleNamespace(occupy={"max_loss": max_loss}))


def _plans_for(i):
    return [Plan(armies=[{"uid": "a", "index": i - 3}], target=i, label="x", prediction=None)]


def _predict(loss):
    return lambda plan: SimpleNamespace(win=True, loss_percent=loss)


def test_lossy_defense_is_refused_at_max_loss_zero():
    assert _rule(0)._defensive_select([NEAR], _plans_for, _predict(18.9), ENEMY) is None


def test_clean_defense_still_claims_the_contested_cell():
    plan = _rule(0)._defensive_select([NEAR], _plans_for, _predict(0.0), ENEMY)
    assert plan is not None and plan.target == NEAR.index


def test_defense_within_a_raised_cap_is_allowed():
    assert _rule(20)._defensive_select([NEAR], _plans_for, _predict(18.9), ENEMY) is not None
    assert _rule(20)._defensive_select([NEAR], _plans_for, _predict(20.1), ENEMY) is None
