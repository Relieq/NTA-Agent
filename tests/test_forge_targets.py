from nta_agent.runtime import forge_targets as ft


def test_set_load_spend_remove(tmp_path):
    p = tmp_path / "forge_targets.json"
    ft.set_target(p, "u1", 0.9, 100)
    ft.set_target(p, "u2", 1.5, 50)  # threshold clamped to 1.0
    d = ft.load(p)
    assert d["u1"] == {"threshold": 0.9, "budget": 100, "fixator_budget": 0}
    assert d["u2"]["threshold"] == 1.0
    # spend decrements the item's remaining budget, floored at 0
    ft.spend(p, "u1", 30)
    assert ft.load(p)["u1"]["budget"] == 70
    ft.spend(p, "u1", 999)
    assert ft.load(p)["u1"]["budget"] == 0
    # remove drops the item
    ft.remove(p, "u1")
    assert "u1" not in ft.load(p)


def test_load_missing_is_empty(tmp_path):
    assert ft.load(tmp_path / "nope.json") == {}


def test_set_target_with_per_stat_mins(tmp_path):
    from nta_agent.runtime import forge_targets
    p = tmp_path / "t.json"
    forge_targets.set_target(p, "6101_1", 1.0, 20, mins={"3.value": 170, "3.odds": 35})
    t = forge_targets.load(p)["6101_1"]
    assert t["mins"] == {"3.value": 170.0, "3.odds": 35.0} and t["budget"] == 20
    forge_targets.spend(p, "6101_1", 2)                     # budget debit keeps the mins
    t = forge_targets.load(p)["6101_1"]
    assert t["budget"] == 18 and t["mins"] == {"3.value": 170.0, "3.odds": 35.0}


def test_fixator_budget_is_kept_and_debited(tmp_path):
    from nta_agent.runtime import forge_targets as ft
    p = tmp_path / "t.json"
    ft.set_target(p, "6101_10", 1.0, 100, mins={"3.value": 150}, fixator_budget=5)
    assert ft.load(p)["6101_10"]["fixator_budget"] == 5
    ft.spend(p, "6101_10", 12, fixator=1)
    t = ft.load(p)["6101_10"]
    assert t["budget"] == 88 and t["fixator_budget"] == 4
    ft.spend(p, "6101_10", 12)                                 # old callers: iron only
    assert ft.load(p)["6101_10"]["fixator_budget"] == 4
