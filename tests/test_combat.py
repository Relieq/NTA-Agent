"""Combat-stat power model (hp*attack) using real config."""
import pytest

from nta_agent.data.config import GameConfig
from nta_agent.execution.predictors.combat import StatValuer

_HAS = (GameConfig().config_dir / "pawnAttr.json").exists()
pytestmark = pytest.mark.skipif(not _HAS, reason="config not extracted")


def test_pawn_power_hp_times_attack():
    v = StatValuer(GameConfig.load())
    # 3101 lv1: hp 135 * atk 10 = 1350
    assert v.pawn_power({"id": 3101, "lv": 1}) == 1350.0
    # 4101 lv1 (npc): hp 25 * atk 13 = 325
    assert v.pawn_power({"id": 4101, "lv": 1}) == 325.0


def test_army_power_and_ranking():
    v = StatValuer(GameConfig.load())
    mine = [{"id": 3101, "lv": 1}, {"id": 3101, "lv": 1}]   # 2700
    enemy = [{"id": 4101, "lv": 1}] * 3                      # 975
    assert v.army_power(mine) > v.army_power(enemy)


def test_from_stats_predictor_margin():
    from nta_agent.execution.predictors.battle import BattlePredictor
    p = BattlePredictor.from_stats(win_margin=1.5)
    # 2700 vs 975 -> ratio ~2.77 >= 1.5 -> win
    r = p.predict([{"id": 3101, "lv": 1}, {"id": 3101, "lv": 1}], [{"id": 4101, "lv": 1}] * 3)
    assert r.win is True
    # 1 pawn (1350) vs 3 npc (975): ratio 1.38 < 1.5 -> not a confident win
    r2 = p.predict([{"id": 3101, "lv": 1}], [{"id": 4101, "lv": 1}] * 3)
    assert r2.win is False
