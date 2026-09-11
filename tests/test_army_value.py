"""Config-driven army value (calculateArmysValue port), using real tables."""

import pytest

from nta_agent.data.config import GameConfig
from nta_agent.execution.predictors.army_value import PawnValuer

_HAS_CONFIG = (GameConfig().config_dir / "pawnBase.json").exists()
pytestmark = pytest.mark.skipif(not _HAS_CONFIG, reason="config tables not extracted")


def test_pawn_cost_cumulative():
    v = PawnValuer(GameConfig.load())
    # pawn 3101: drill_cost lv0 = 113 cereal; lv1 lv_cost = 181 cereal + 1 of type7 (res7)
    assert v.pawn_cost(3101, 0) == {"cereal": 113}
    assert v.pawn_cost(3101, 1) == {"cereal": 113 + 181, "res7": 1}
    # res7 has no weight, so it doesn't affect the value
    assert v.pawn_value({"id": 3101, "lv": 1}) == 294.0


def test_pawn_value_weighted():
    v = PawnValuer(GameConfig.load())
    assert v.pawn_value({"id": 3101, "lv": 1}) == 294.0  # 113 + 181, weight 1


def test_army_value_sums_and_ranks():
    v = PawnValuer(GameConfig.load())
    strong = [{"id": 3101, "lv": 1}, {"id": 3101, "lv": 1}]
    weak = [{"id": 3101, "lv": 0}]
    assert v.army_value(strong) > v.army_value(weak)


def test_battle_predictor_from_config():
    from nta_agent.execution.predictors.battle import BattlePredictor
    p = BattlePredictor.from_config()
    r = p.predict([{"id": 3101, "lv": 1}, {"id": 3101, "lv": 1}], [{"id": 3101, "lv": 0}])
    assert r.win is True and r.my_power > r.enemy_power
