from nta_agent.execution.forge import (
    is_common,
    next_forge,
    parse_range,
    stat_fraction,
)

BASE = {
    6001: {"id": 6001, "attack": "6,15", "hp": "", "forge_cost": 10, "reforge_count": 5, "exclusive_pawn": ""},
    6002: {"id": 6002, "attack": "", "hp": "60,130", "forge_cost": 10, "reforge_count": 5, "exclusive_pawn": ""},
    9001: {"id": 9001, "attack": "6,15", "forge_cost": 10, "reforge_count": 5, "exclusive_pawn": "3101"},  # specialized
}


def base_of(i):
    return BASE.get(i)


def _e(uid, id_, is_forged=True, attack=0, hp=0, recast=0, free=False):
    return {"uid": uid, "id": id_, "is_forged": is_forged, "attack": attack,
            "hp": hp, "recast_count": recast, "next_forge_free": free}


def test_parse_range_and_fraction():
    assert parse_range("6,15") == (6, 15)
    assert parse_range("") is None
    assert stat_fraction({"attack": 6}, BASE[6001]) == 0.0
    assert stat_fraction({"attack": 15}, BASE[6001]) == 1.0
    assert abs(stat_fraction({"hp": 95}, BASE[6002]) - (35 / 70)) < 1e-9


def test_is_common():
    assert is_common(BASE[6001]) is True
    assert is_common(BASE[9001]) is False  # exclusive_pawn set


def test_baseline_forges_unforged_common():
    equips = [_e("u1", 6001, is_forged=False)]
    d = next_forge(equips, base_of, iron=100)
    assert d.uid == "u1" and d.kind == "forge" and d.cost == 10


def test_skips_specialized_equipment():
    equips = [_e("s1", 9001, is_forged=False)]           # specialized -> never
    assert next_forge(equips, base_of, iron=100) is None


def test_recast_when_below_threshold_and_budget_ok():
    equips = [_e("u1", 6001, attack=8)]                  # frac = 2/9 ≈ 0.22
    targets = {"u1": {"threshold": 0.9, "budget": 100}}
    d = next_forge(equips, base_of, targets, iron=100)
    assert d.uid == "u1" and d.kind == "recast" and d.cost == 10


def test_no_recast_when_threshold_met():
    equips = [_e("u1", 6001, attack=15)]                 # frac 1.0 >= 0.9
    targets = {"u1": {"threshold": 0.9, "budget": 100}}
    assert next_forge(equips, base_of, targets, iron=100) is None


def test_no_recast_when_item_budget_exhausted():
    equips = [_e("u1", 6001, attack=8)]
    targets = {"u1": {"threshold": 0.9, "budget": 5}}    # < forge_cost 10
    assert next_forge(equips, base_of, targets, iron=100) is None


def test_no_recast_past_reforge_cap():
    equips = [_e("u1", 6001, attack=8, recast=5)]        # reforge_count 5 reached
    targets = {"u1": {"threshold": 0.9, "budget": 100}}
    assert next_forge(equips, base_of, targets, iron=100) is None


def test_free_recast_costs_zero_and_ignores_budget():
    equips = [_e("u1", 6001, attack=8, free=True)]
    targets = {"u1": {"threshold": 0.9, "budget": 0}}    # no budget, but free
    d = next_forge(equips, base_of, targets, iron=0)
    assert d.kind == "recast" and d.cost == 0


def test_busy_blocks_all():
    equips = [_e("u1", 6001, is_forged=False)]
    assert next_forge(equips, base_of, iron=100, busy=True) is None
