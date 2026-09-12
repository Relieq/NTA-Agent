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
