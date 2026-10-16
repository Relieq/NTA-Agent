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


def test_loot_and_stamina_are_found_from_a_real_land_id_and_distance():
    """Cells carry the LAND id (land table: 301..505 / 0..14), but the chest rows live in
    landAttr at 1000*land.lv + clamp(distance, 1, cap) (engine getLandAttrLvByDis); looking the
    land id up directly gave 0 for every real cell, so the loot model never saw a chest."""
    from nta_agent.execution.treasure_model import land_attr_id, need_stamina
    cfg = GameConfig.load()
    lv5, lv3, lv1 = 305, 303, 301          # land ids of level 5 / 3 / 1 (type 3)
    assert land_attr_id(cfg, lv5, 7) == 5007
    assert land_attr_id(cfg, lv5, 99) == 5016          # lv5 caps at 16
    assert land_attr_id(cfg, lv3, 99) == 3012          # lv1-3 cap at 12
    assert land_attr_id(cfg, 304, 99) == 4015          # lv4 caps at 15
    assert land_attr_id(cfg, lv1, None) == 1001
    assert land_attr_id(cfg, 5003, 1) == 5003           # an id that is already a landAttr id stays
    assert need_stamina(cfg, lv5, 4) == 3 and need_stamina(cfg, lv3, 4) == 1
    assert need_stamina(cfg, 4, 4) == 3                  # the 0..14 numbering: id 4 = lv5 too
    assert cell_loot(lv5, cfg, 4).reward_value > cell_loot(lv3, cfg, 4).reward_value > 0
    assert cell_loot(9999, cfg, 4) == CellLoot(0, 0.0)   # unknown land
