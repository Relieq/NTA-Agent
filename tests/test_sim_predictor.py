"""SimBattlePredictor: map the sidecar forecast onto BattlePrediction."""
from __future__ import annotations

import pytest

from nta_agent.execution.predictors.battle import BattlePrediction
from nta_agent.execution.predictors.sim_bridge import SimUnavailable
from nta_agent.execution.predictors.sim_predictor import SimBattlePredictor
from nta_agent.state.schema import GameState, User


class FakeBridge:
    def __init__(self, result, *, available=True):
        self._result = result
        self._available = available
        self.calls = []

    def available(self):
        return self._available

    def forecast(self, inp):
        if not self._available:
            raise SimUnavailable("down")
        self.calls.append(inp)
        return self._result


def _state():
    return GameState(user=User(uid="100"))


def _army():
    return {"uid": "a1", "name": "D1", "index": 109726,
            "pawns": [{"id": 3101, "lv": 1, "uid": "p1", "hp": [135, 135]}]}


def test_predict_target_maps_engine_result():
    bridge = FakeBridge({"isWin": True, "lossLv": 2, "lossPercent": 18.0,
                         "survivors": {"self": {"alive": 1, "total": 2}}})
    pred = SimBattlePredictor(bridge=bridge)
    out = pred.predict_target(_state(), _army(), target_index=109725, land_id=0, distance=1)

    assert isinstance(out, BattlePrediction)
    assert out.win is True
    assert out.loss_lv == 2
    assert out.loss_percent == 18.0
    # the request carried the right target context
    assert bridge.calls[0]["targetCellIndex"] == 109725
    assert bridge.calls[0]["playerUid"] == "100"


def test_predict_target_loss_maps_when_defeated():
    bridge = FakeBridge({"isWin": False, "lossLv": 4, "lossPercent": 100.0})
    pred = SimBattlePredictor(bridge=bridge)
    out = pred.predict_target(_state(), _army(), target_index=1, land_id=0, distance=1)
    assert out.win is False
    assert out.loss_lv == 4


def test_predict_target_carries_battle_duration():
    bridge = FakeBridge({"isWin": True, "lossLv": 0, "lossPercent": 0.0, "durationS": 42.5})
    out = SimBattlePredictor(bridge=bridge).predict_target(
        _state(), _army(), target_index=1, land_id=0, distance=1)
    assert out.duration_s == 42.5
    # an older sidecar without durationS -> unknown, not 0
    bridge2 = FakeBridge({"isWin": True, "lossLv": 0, "lossPercent": 0.0})
    out2 = SimBattlePredictor(bridge=bridge2).predict_target(
        _state(), _army(), target_index=1, land_id=0, distance=1)
    assert out2.duration_s is None


def test_legacy_predict_requires_target_context():
    pred = SimBattlePredictor(bridge=FakeBridge({"isWin": True, "lossLv": 0, "lossPercent": 0}))
    with pytest.raises(SimUnavailable):
        pred.predict([{"id": 3101, "lv": 1}], [{"id": 4101, "lv": 1}])
