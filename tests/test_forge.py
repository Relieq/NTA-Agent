"""Forge core: crafting + RECAST toward a per-item EFFECT-quality threshold.

User rules (2026-09-18 + 2026-09-23): only COMMON equips (exclusive_pawn empty);
recast a user-designated equip until its EFFECT rolls (value + odds, each within
equipEffect ranges) reach the item's threshold, or its IRON budget runs out.
Main stats (attack/hp) don't count. No RestoreForge.
"""
from nta_agent.execution.forge import (
    effect_quality,
    is_common,
    next_recast,
    parse_attrs,
    parse_range,
)

# equipBase-like rows (forge_cost is the multi-resource config string)
BASE = {
    6001: {"id": 6001, "attack": "1,5", "hp": "20,40", "effect": "3",
           "forge_cost": "2,0,100|3,0,100|9,0,3", "exclusive_pawn": ""},
    9001: {"id": 9001, "attack": "1,5", "effect": "3", "forge_cost": "9,0,3",
           "exclusive_pawn": "3101"},                       # specialized -> never
}
EFFECT = {3: {"id": 3, "value": "150,180", "odds": "20,40", "suffix": "%"},   # crit: dmg% + chance%
          7: {"id": 7, "value": "30,50", "odds": ""}}           # no odds range


def base_of(i):
    return BASE.get(i)


def eff_row(t):
    return EFFECT.get(t)


def _eq(uid="6001_1", id_=6001, effects=((3, 165, 30),), attack=3, hp=30, free=False, recast=0):
    """Engine EquipInfo: attrs = [[0, 2(atk)|1(hp), v], [2, effectType, value, odds], ...]."""
    attrs = [{"attr": [0, 2, attack]}, {"attr": [0, 1, hp]}]
    attrs += [{"attr": [2, t, v, o]} for t, v, o in effects]
    return {"uid": uid, "id": id_, "attrs": attrs, "recastCount": recast, "nextForgeFree": free}


RICH = {"timber": 999, "stone": 999, "iron": 99}


def test_parse_range():
    assert parse_range("150,180") == (150, 180)
    assert parse_range("") is None


def test_is_common():
    assert is_common(BASE[6001]) and not is_common(BASE[9001])


def test_parse_attrs_engine_shape():
    a = parse_attrs(_eq(effects=((3, 165, 30), (7, 40, 0))))
    assert a["attack"] == 3 and a["hp"] == 30
    assert a["effects"] == [{"type": 3, "value": 165, "odds": 30},
                            {"type": 7, "value": 40, "odds": 0}]


def test_effect_quality_ignores_main_stats():
    # value 165 in 150..180 = 0.5 ; odds 30 in 20..40 = 0.5 -> 0.5
    assert effect_quality(_eq(), eff_row) == 0.5
    # maxed effects -> 1.0 regardless of terrible attack/hp
    assert effect_quality(_eq(effects=((3, 180, 40),), attack=1, hp=20), eff_row) == 1.0
    # effect without an odds range only scores its value: (40-30)/20 = 0.5
    assert effect_quality(_eq(effects=((7, 40, 0),)), eff_row) == 0.5
    assert effect_quality(_eq(effects=()), eff_row) is None       # nothing to judge


def test_recast_below_threshold_within_iron_budget():
    t = {"6001_1": {"threshold": 0.8, "budget": 10}}
    d = next_recast([_eq()], base_of, eff_row, t, RICH)
    assert d.uid == "6001_1" and d.iron == 3 and d.free is False
    assert d.cost == {"timber": 100, "stone": 100, "iron": 3}
    assert d.quality == 0.5


def test_stop_when_threshold_reached():
    t = {"6001_1": {"threshold": 0.5, "budget": 10}}
    assert next_recast([_eq()], base_of, eff_row, t, RICH) is None


def test_iron_budget_exhausted_or_unaffordable():
    assert next_recast([_eq()], base_of, eff_row, {"6001_1": {"threshold": 1, "budget": 2}},
                       RICH) is None                           # budget 2 < 3 iron
    poor = {"timber": 999, "stone": 50, "iron": 99}           # stone short
    assert next_recast([_eq()], base_of, eff_row, {"6001_1": {"threshold": 1, "budget": 9}},
                       poor) is None


def test_free_recast_ignores_budget_and_cost():
    t = {"6001_1": {"threshold": 1, "budget": 0}}
    d = next_recast([_eq(free=True)], base_of, eff_row, t, {"iron": 0})
    assert d.free is True and d.iron == 0 and d.cost == {}


def test_specialized_busy_and_untargeted_skipped():
    t = {"9001_1": {"threshold": 1, "budget": 99}}
    assert next_recast([_eq("9001_1", 9001)], base_of, eff_row, t, RICH) is None
    t = {"6001_1": {"threshold": 1, "budget": 99}}
    assert next_recast([_eq()], base_of, eff_row, t, RICH, busy=True) is None
    assert next_recast([_eq()], base_of, eff_row, {}, RICH) is None     # no target


def test_parse_cost_multi_resource():
    from nta_agent.execution.forge import parse_cost
    assert parse_cost("2,0,357|3,0,357|9,0,3") == {"timber": 357, "stone": 357, "iron": 3}
    assert parse_cost("") == {}


def test_affordable():
    from nta_agent.execution.forge import affordable
    cost = {"timber": 357, "stone": 357, "iron": 3}
    assert affordable(cost, {"timber": 400, "stone": 400, "iron": 3}) is True
    assert affordable(cost, {"timber": 400, "stone": 400, "iron": 1}) is False  # iron short


def test_craft_candidates_from_slots():
    slots = {"1": {"id": 6001, "lv": 1},          # chosen common -> craft "6001_1"
             "3": {"selectIds": [6001, 6002], "lv": 3},  # not chosen (no id) -> skip
             "5": {"id": 9001, "lv": 5}}          # specialized -> skip
    base = {6001: {"exclusive_pawn": "", "forge_cost": "9,0,3"},
            9001: {"exclusive_pawn": "3101", "forge_cost": "9,0,3"}}
    from nta_agent.execution.forge import craft_candidates
    cands = craft_candidates(slots, lambda i: base.get(i), crafted_ids=set())
    assert [c["uid"] for c in cands] == ["6001_1"]
    assert cands[0]["cost"] == {"iron": 3}
    # already crafted -> skipped
    assert craft_candidates(slots, lambda i: base.get(i), crafted_ids={6001}) == []


def test_forge_view_lists_common_equips_with_quality_and_target():
    from nta_agent.execution.forge import forge_view
    names = {6001: "Rìu Chiến", 9001: "Khiên Riêng"}
    texts = {3: "Có {1} gây {0} ST Bạo"}
    rows = forge_view([_eq(effects=((3, 165, 30),), recast=2), _eq("9001_1", 9001)],
                      base_of, eff_row, {"6001_1": {"threshold": 0.8, "budget": 12}},
                      name_of=names.get, effect_text=texts.get)
    # exclusive (pawn-locked) equips are listed too since 2026-09-26, flagged as such
    assert [r["uid"] for r in rows] == ["6001_1", "9001_1"]
    assert [r["exclusive"] for r in rows] == [False, True]
    rows = [r for r in rows if not r["exclusive"]]
    r = rows[0]
    assert r["name"] == "Rìu Chiến" and r["quality"] == 0.5 and r["recast_count"] == 2
    assert r["target"] == {"threshold": 0.8, "budget": 12} and r["iron_cost"] == 3
    assert r["effects"][0]["text"] == "Có 30% gây 165% ST Bạo"
    assert r["effects"][0]["value_range"] == [150, 180] and r["effects"][0]["odds_range"] == [20, 40]


def test_equip_id_derived_from_uid_when_missing():
    """Live EquipInfo can omit `id` (engine derives it from uid "<id>_<lv>");
    without it the equipBase lookup failed (name #0, cost 0, recast skipped)."""
    e = _eq()
    del e["id"]
    t = {"6001_1": {"threshold": 0.8, "budget": 10}}
    d = next_recast([e], base_of, eff_row, t, RICH)
    assert d is not None and d.iron == 3
    from nta_agent.execution.forge import forge_view
    rows = forge_view([e], base_of, eff_row, {}, name_of={6001: "Rìu"}.get,
                      effect_text={3: "Có <color=#000001>{1}</c> gây <color=#000001>{0}</c> ST Bạo"}.get)
    assert rows[0]["id"] == 6001 and rows[0]["name"] == "Rìu" and rows[0]["iron_cost"] == 3
    assert rows[0]["effects"][0]["text"] == "Có 30% gây 165% ST Bạo"     # markup stripped


# ---- per-equip, per-stat minimums (user 2026-09-24) ---------------------------
def test_target_met_per_stat_minimums():
    from nta_agent.execution.forge import target_met
    e = _eq(effects=((3, 165, 30),))
    assert target_met(e, {"mins": {"3.value": 160, "3.odds": 30}}, eff_row) is True
    assert target_met(e, {"mins": {"3.value": 170}}, eff_row) is False     # value short
    assert target_met(e, {"mins": {"3.odds": 35}}, eff_row) is False       # odds short
    # a required effect that wasn't rolled -> not met
    assert target_met(e, {"mins": {"7.value": 31}}, eff_row) is False
    # legacy composite threshold still works when no mins
    assert target_met(e, {"threshold": 0.5}, eff_row) is True
    assert target_met(e, {"threshold": 0.6}, eff_row) is False


def test_next_recast_uses_per_stat_minimums():
    t = {"6001_1": {"budget": 10, "mins": {"3.odds": 35}}}
    d = next_recast([_eq(effects=((3, 180, 30),))], base_of, eff_row, t, RICH)
    assert d is not None and d.unmet == ["3.odds"]            # value maxed, odds short
    t = {"6001_1": {"budget": 10, "mins": {"3.odds": 30}}}
    assert next_recast([_eq(effects=((3, 150, 30),))], base_of, eff_row, t, RICH) is None


def test_forge_view_lists_possible_effects_for_per_stat_ui():
    from nta_agent.execution.forge import forge_view
    base = {6101: {"id": 6101, "exclusive_pawn": "", "effect": "3|7",
                   "forge_cost": "9,0,2"}}
    eq = {"uid": "6101_1", "attrs": [{"attr": [2, 3, 170, 25]}]}
    rows = forge_view([eq], base.get, eff_row, {"6101_1": {"budget": 5, "mins": {"3.odds": 35}}},
                      effect_text={3: "Có {1} gây {0} ST Bạo", 7: "Hồi {0} máu"}.get)
    r = rows[0]
    pos = {p["type"]: p for p in r["possible"]}
    assert set(pos) == {3, 7}
    assert pos[3]["current"] == {"value": 170, "odds": 25}
    assert pos[7]["current"] is None                          # not rolled now
    assert pos[3]["label"] == "Có [tỉ lệ] gây [giá trị] ST Bạo"
    assert pos[3]["value_range"] == [150, 180] and pos[3]["odds_range"] == [20, 40]
    assert pos[7]["odds_range"] == []                         # no odds -> single number
    assert r["met"] is False and r["unmet"] == ["3.odds"]
