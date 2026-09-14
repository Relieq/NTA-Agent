from types import SimpleNamespace

from nta_agent.data.config import GameConfig
from nta_agent.execution.treasure_model import CellLoot, cell_loot, chest_budget


def test_cell_loot_reads_count_and_tier_weighted_reward():
    cfg = GameConfig.load()
    loot = cell_loot(1003, cfg)  # landAttr 1003: treasures_count "2,2"
    assert isinstance(loot, CellLoot)
    assert loot.chest_cost >= 1 and loot.reward_value > 0
    # unknown land -> zeros
    assert cell_loot(-1, cfg) == CellLoot(chest_cost=0, reward_value=0.0)


def test_chest_budget_reads_field_else_unlimited():
    with_field = SimpleNamespace(raw={"player": {"treasureOpenCount": 12}})
    assert chest_budget(with_field) == 12
    without = SimpleNamespace(raw={"player": {}})
    assert chest_budget(without) >= 1000  # unlimited sentinel
