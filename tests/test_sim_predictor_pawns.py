from nta_agent.execution.predictors.sim_predictor import SimBattlePredictor
from nta_agent.state.schema import GameState


class FakeBridge:
    def __init__(self, res):
        self._res = res

    def forecast(self, inp):
        return self._res

    def available(self):
        return True


def test_predict_armies_exposes_pawn_survival():
    res = {"isWin": True, "lossPercent": 10.0, "lossLv": 1,
           "survivors": {"self": {"alive": 2, "total": 3},
                         "pawns": [{"uid": "big", "camp": 2, "alive": True, "curHp": 150}]}}
    st = GameState(source="api"); st.raw = {}; st.user.uid = "1"
    p = SimBattlePredictor(bridge=FakeBridge(res))
    armies = [{"uid": "a", "index": 1, "pawns": [{"uid": "big", "id": 3101, "lv": 1}]}]
    pred = p.predict_armies(st, armies, target_index=9, land_id=0, distance=1)
    assert pred.win is True
    assert pred.pawn_survival == [{"uid": "big", "camp": 2, "alive": True, "curHp": 150}]
