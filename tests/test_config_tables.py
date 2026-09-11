"""Config parsing + loader (uses the extracted tables when present)."""

import pytest

from nta_agent.data.config import GameConfig, parse_cost, parse_effects


def test_parse_cost():
    assert parse_cost("2,0,178|3,0,178") == {"timber": 178, "stone": 178}
    assert parse_cost("1,0,113") == {"cereal": 113}
    assert parse_cost("") == {}


def test_parse_effects():
    assert parse_effects("11,2|63,3") == [(11, 2), (63, 3)]
    assert parse_effects("") == []


_HAS_CONFIG = (GameConfig().config_dir / "buildAttr.json").exists()


@pytest.mark.skipif(not _HAS_CONFIG, reason="config tables not extracted")
def test_build_upgrade_main_hall_lv1():
    gc = GameConfig.load()
    up = gc.build_upgrade(2001, 1)  # main hall -> lv1
    assert up is not None
    assert up.cost == {"timber": 178, "stone": 178}
    assert up.time == 60


@pytest.mark.skipif(not _HAS_CONFIG, reason="config tables not extracted")
def test_pawn_recruit_cost():
    gc = GameConfig.load()
    cost = gc.pawn_recruit_cost(3101)
    assert cost == {"cereal": 113}
