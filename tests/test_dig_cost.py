"""CellCost: per-cell dig time = one-cell march + the sim's battle length."""
from __future__ import annotations

from nta_agent.execution.dig_cost import ROUGH_BATTLE_S, CellCost, attr_lv, march_ms
from nta_agent.execution.predictors.battle import BattlePrediction
from nta_agent.execution.worldmap import WorldMap


def _pred(win=True, loss=0.0, dur=30.0):
    return BattlePrediction(win=win, my_power=1, enemy_power=1, ratio=1,
                            loss_percent=loss, loss_lv=0, duration_s=dur)


def _world():
    land = [{"id": 1, "type": 3, "lv": 1, "occupy": 1},
            {"id": 5, "type": 3, "lv": 5, "occupy": 1}]
    w = WorldMap({"maps_15": [1] * 10 + [5] * 10}, land)
    w.detect([0])
    return w


def test_march_ms_matches_engine_formula():
    # floor(dis * 3_600_000 / marchSpeed) * (1 - cd%)
    assert march_ms(1, 62) == 58064
    assert march_ms(2, 62) == 116129
    assert march_ms(1, 60, cd_pct=50) == 30000


def test_attr_lv_clamps_by_land_level():
    assert attr_lv(0, 1) == 1
    assert attr_lv(30, 1) == 12
    assert attr_lv(30, 4) == 15
    assert attr_lv(30, 5) == 16
    assert attr_lv(7, 5) == 7


def test_cost_is_march_plus_battle_and_memoised_by_land_and_attr_level():
    calls = []

    def predict(idx, land_id, dist):
        calls.append((idx, land_id, dist))
        return _pred(dur=30.0)

    cc = CellCost(predict, _world(), dist_fn=lambda i: 20, max_loss=0, speed=60)
    assert cc.cost(1) == 60.0 + 30.0
    assert cc.cost(2) == 90.0          # same landId, same clamped level -> memo
    assert len(calls) == 1
    cc.cost(15)                         # other landId -> a new sim
    assert len(calls) == 2


def test_lost_or_too_costly_battles_are_hard():
    w = _world()
    lose = CellCost(lambda *a: _pred(win=False), w, dist_fn=lambda i: 3, max_loss=0, speed=60)
    assert lose.cost(1) is None
    lossy = CellCost(lambda *a: _pred(loss=10.0), w, dist_fn=lambda i: 3, max_loss=5, speed=60)
    assert lossy.cost(1) is None
    ok = CellCost(lambda *a: _pred(loss=4.0), w, dist_fn=lambda i: 3, max_loss=5, speed=60)
    assert ok.cost(1) == 90.0


def test_sim_failure_falls_back_to_a_rough_estimate():
    def boom(*a):
        raise RuntimeError("sidecar down")

    cc = CellCost(boom, _world(), dist_fn=lambda i: 3, max_loss=0, speed=60)
    assert cc.cost(15) == 60.0 + ROUGH_BATTLE_S[5]
    assert cc.rough is True
    # a prediction without a duration (old sidecar) is rough too, but keeps win/loss
    cc2 = CellCost(lambda *a: _pred(dur=None), _world(), dist_fn=lambda i: 3, max_loss=0, speed=60)
    assert cc2.cost(1) == 60.0 + ROUGH_BATTLE_S[1]
