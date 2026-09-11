"""Occupy evaluator + occupy_cell action (fakes; no network)."""

from dataclasses import dataclass, field

from nta_agent.execution.actions import Actions
from nta_agent.execution.occupy_planner import evaluate_target
from nta_agent.execution.predictors.battle import BattlePrediction
from nta_agent.state.schema import GameState


def _pred(win, loss=10.0):
    return BattlePrediction(win=win, my_power=100, enemy_power=50, ratio=2.0,
                            loss_percent=loss, loss_lv=1)


def test_evaluate_ok_when_win_and_stamina():
    e = evaluate_target(500, _pred(True, 20.0), {"timber": 300}, need_stamina=1, available_stamina=5)
    assert e.ok and e.score > 0 and e.yield_total == 300


def test_evaluate_rejects_loss():
    e = evaluate_target(500, _pred(False), {"timber": 300}, 1, 5)
    assert not e.ok and e.score == 0 and e.reason == "would lose"


def test_evaluate_rejects_no_stamina():
    e = evaluate_target(500, _pred(True), {"timber": 300}, need_stamina=9, available_stamina=2)
    assert not e.ok and e.reason == "not enough stamina"


def test_lower_loss_scores_higher():
    a = evaluate_target(1, _pred(True, 5.0), {"timber": 100}, 1, 5)
    b = evaluate_target(2, _pred(True, 80.0), {"timber": 100}, 1, 5)
    assert a.score > b.score


@dataclass
class FakeSession:
    state: GameState
    calls: list = field(default_factory=list)
    def request(self, route, params=None, timeout=15):
        self.calls.append((route, params or {}))
        return {}


def test_occupy_cell_builds_index_uid_arrays():
    s = FakeSession(state=GameState(source="api"))
    armies = [{"index": 109726, "uid": "a1"}, {"index": 109726, "uid": "a2"}]
    Actions(s).occupy_cell(870, armies, auto_back_type=1, same_speed=True)
    route, params = s.calls[0]
    assert route == "game/HD_OccupyCell"
    assert params["indexs"] == [109726, 109726]
    assert params["uids"] == ["a1", "a2"]
    assert params["target"] == 870 and params["autoBackType"] == 1 and params["isSameSpeed"] is True


def test_drill_pawn_and_building_uid():
    from nta_agent.state.schema import Building
    st = GameState(source="api")
    st.main_city_index = 109726
    st.builds = [Building(index=109726, id=2004, lv=1, uid="barracks1")]
    s = FakeSession(state=st)
    a = Actions(s)
    assert a.building_uid(2004) == "barracks1"
    assert a.building_uid(9999) == ""
    a.drill_pawn("barracks1", 3101, army_name="A")
    route, params = s.calls[0]
    assert route == "game/HD_DrillPawn"
    assert params == {"index": 109726, "buildUid": "barracks1", "id": 3101,
                      "armyUid": "", "armyName": "A"}
