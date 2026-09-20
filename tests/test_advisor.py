from dataclasses import dataclass

from nta_agent.execution.advisor import best_occupy


@dataclass
class Cand:
    index: int
    defenders: list
    land_id: int = 0


@dataclass
class Pred:
    win: bool
    loss_percent: float


def test_best_occupy_picks_lowest_loss_win_over_all_armies():
    c1, c2 = Cand(1, []), Cand(2, [])
    armies = {
        1: [{"uid": "A", "pawns": [1], "name": "A"}, {"uid": "B", "pawns": [1], "name": "B"}],
        2: [{"uid": "C", "pawns": [1], "name": "C"}],
    }
    # A wins c1 with 40% loss; B wins c1 with 10%; C loses c2.
    def predict(army, c):
        if army["uid"] == "A":
            return Pred(True, 40.0)
        if army["uid"] == "B":
            return Pred(True, 10.0)
        return Pred(False, 100.0)

    rec = best_occupy([c1, c2], lambda i: armies.get(i, []), predict)
    assert rec is not None
    assert rec.army["uid"] == "B" and rec.target == 1 and rec.prediction.loss_percent == 10.0


def test_best_occupy_none_when_no_win():
    c = Cand(1, [])
    rec = best_occupy([c], lambda i: [{"uid": "A", "pawns": [1]}], lambda a, c: Pred(False, 100.0))
    assert rec is None


def test_best_occupy_skips_empty_armies_and_none_predictions():
    c = Cand(1, [])
    armies = [{"uid": "empty", "pawns": []}, {"uid": "A", "pawns": [1], "name": "A"}]
    rec = best_occupy([c], lambda i: armies, lambda a, c: None if a["uid"] == "empty" else Pred(True, 5.0))
    assert rec.army["uid"] == "A"


# --- v2: best_plan over ordered multi-army plans ---
from types import SimpleNamespace

from nta_agent.execution.advisor import Plan, best_plan


def _pred(win, loss):
    return SimpleNamespace(win=win, loss_percent=loss)


def test_best_plan_picks_lowest_loss_winning_plan():
    cell = SimpleNamespace(index=7)
    plans = {7: [
        Plan(armies=[{"uid": "a"}, {"uid": "b"}], target=7, label="archers-first", prediction=None),
        Plan(armies=[{"uid": "b"}, {"uid": "a"}], target=7, label="tanks-first", prediction=None),
        Plan(armies=[{"uid": "a"}], target=7, label="single", prediction=None),
    ]}
    preds = {"archers-first": _pred(True, 10), "tanks-first": _pred(True, 20),
             "single": _pred(False, 100)}
    got = best_plan([cell], lambda i: plans[i], lambda p: preds[p.label])
    assert got.label == "archers-first"
    assert got.armies == [{"uid": "a"}, {"uid": "b"}]


def test_best_plan_tie_prefers_fewer_armies():
    cell = SimpleNamespace(index=7)
    plans = {7: [
        Plan(armies=[{"uid": "a"}, {"uid": "b"}], target=7, label="two", prediction=None),
        Plan(armies=[{"uid": "a"}], target=7, label="one", prediction=None),
    ]}
    preds = {"two": _pred(True, 10), "one": _pred(True, 10)}
    got = best_plan([cell], lambda i: plans[i], lambda p: preds[p.label])
    assert got.label == "one"


def test_best_plan_none_when_no_win():
    cell = SimpleNamespace(index=7)
    plans = {7: [Plan(armies=[{"uid": "a"}], target=7, label="x", prediction=None)]}
    got = best_plan([cell], lambda i: plans[i], lambda p: _pred(False, 100))
    assert got is None


def test_best_plan_tie_prefers_nearer_group_over_fewer_armies():
    # A far single-army group and a near 2-army group both win at 0 loss. The near
    # group is preferred despite having MORE armies — it needs no long march/bridge.
    cell = SimpleNamespace(index=7)
    plans = {7: [
        Plan(armies=[{"uid": "far"}], target=7, label="far-one", prediction=None),
        Plan(armies=[{"uid": "n1"}, {"uid": "n2"}], target=7, label="near-two", prediction=None),
    ]}
    preds = {"far-one": _pred(True, 0), "near-two": _pred(True, 0)}
    dist = {"far-one": 12, "near-two": 3}
    got = best_plan([cell], lambda i: plans[i], lambda p: preds[p.label],
                    distance=lambda p: dist[p.label])
    assert got.label == "near-two"


def test_best_plan_distance_yields_to_lower_loss():
    # Distance only breaks TIES: a far plan with lower loss still wins over a near
    # plan with higher loss.
    cell = SimpleNamespace(index=7)
    plans = {7: [
        Plan(armies=[{"uid": "far"}], target=7, label="far-clean", prediction=None),
        Plan(armies=[{"uid": "near"}], target=7, label="near-lossy", prediction=None),
    ]}
    preds = {"far-clean": _pred(True, 0), "near-lossy": _pred(True, 15)}
    dist = {"far-clean": 20, "near-lossy": 1}
    got = best_plan([cell], lambda i: plans[i], lambda p: preds[p.label],
                    distance=lambda p: dist[p.label])
    assert got.label == "far-clean"
