"""exclusive.py — exclusive equipment rules (pure)."""
from __future__ import annotations

from nta_agent.execution.exclusive import (
    fixator_per_recast,
    natural_effects,
    smelt_preview,
    smelt_slots,
    smelted_types,
    vice_candidates,
)

POOL = [21, 3, 8, 15]          # this match's random pool for exclusive 6101


def _eq(uid, effects, lock=0):
    """effects: (type, value, odds[, smeltId])"""
    return {"uid": uid, "lockEffect": lock,
            "attrs": [{"attr": [0, 2, 10]}] + [{"attr": [2, *e]} for e in effects]}


def test_natural_vs_smelted_effects():
    e = _eq("6101_10", [(21, 5, 0), (3, 150, 20), (8, 40, 0, 6005)])
    assert [x["type"] for x in natural_effects(e)] == [21, 3]
    assert smelted_types(e) == {8: 6005}


def test_fixators_per_recast_lock_plus_smelted_in_pool():
    plain = _eq("a", [(21, 5, 0), (3, 150, 20)])
    assert fixator_per_recast(plain, POOL) == 0
    assert fixator_per_recast({**plain, "lockEffect": 21}, POOL) == 1
    assert fixator_per_recast({**plain, "lockEffect": 99}, POOL) == 0   # lock not on the equip -> dropped
    smelt_in = _eq("b", [(21, 5, 0), (3, 150, 20), (8, 40, 0, 6005)], lock=21)
    assert fixator_per_recast(smelt_in, POOL) == 2                    # lock + smelted 8 in pool
    smelt_out = _eq("c", [(21, 5, 0), (3, 150, 20), (77, 1, 0, 6009)])
    assert fixator_per_recast(smelt_out, POOL) == 0                   # 77 not in the pool


def test_smelt_slots_by_smithy_level():
    assert smelt_slots(13) == 0 and smelt_slots(14) == 1 and smelt_slots(20) == 2


def test_vice_candidates_are_common_equips_not_smelted_elsewhere():
    base = {6005: {"exclusive_pawn": "", "smelt_type": 1}, 6006: {"exclusive_pawn": "", "smelt_type": 1},
            6001: {"exclusive_pawn": "", "smelt_type": 0},                 # not smeltable
            6101: {"exclusive_pawn": 3101}, 6102: {"exclusive_pawn": 3202}}.get
    equips = [_eq("6005_1", [(8, 40, 0)]), _eq("6006_3", [(15, 9, 0)]),
              _eq("6001_2", [(8, 40, 0)]),
              _eq("6101_10", [(21, 5, 0)]),
              _eq("6102_18", [(3, 1, 1), (8, 40, 0, 6006)])]            # 6006 already in 6102
    ids = [c["id"] for c in vice_candidates(equips, base, main_uid="6101_10")]
    assert ids == [6005]
    # re-smelting the same main may keep its own vices
    ids2 = [c["id"] for c in vice_candidates(equips, base, main_uid="6102_18")]
    assert ids2 == [6005, 6006]


def test_smelt_preview_lists_added_effects_and_future_fixators():
    main = _eq("6101_10", [(21, 5, 0), (3, 150, 20)])
    vices = [_eq("6005_1", [(8, 40, 0)]), _eq("6006_3", [(77, 9, 0)])]
    p = smelt_preview(main, [(6005, vices[0]), (6006, vices[1])], POOL)
    assert [a["type"] for a in p["added"]] == [8, 77]
    assert p["fixator_per_recast"] == 1          # 8 is in this match's pool, 77 is not
    assert p["unchanged"] is False
    assert p["fixator_cost"] == 2                # the smelt itself: 1 fixator per vice
    withstat = {"uid": "6005_1", "attrs": [{"attr": [0, 1, 41]}, {"attr": [2, 8, 40, 0]}]}
    assert smelt_preview(main, [(6005, withstat)], POOL)["stats"] == {"hp": 21, "attack": 0}
    same = smelt_preview(_eq("x", [(21, 5, 0), (8, 40, 0, 6005)]), [(6005, vices[0])], POOL)
    assert same["unchanged"] is True


def test_smelt_view_lists_mains_candidates_slots_and_busy():
    from nta_agent.execution.exclusive import smelt_view
    base = {6005: {"exclusive_pawn": "", "smelt_type": 1},
            6101: {"exclusive_pawn": "3101"}}.get
    player = {"equips": [_eq("6101_10", [(21, 5, 0), (8, 30, 0, 6005)]),
                         _eq("6005_1", [(8, 40, 0)])],
              "currSmeltEquip": None, "fixator": 4}
    v = smelt_view(player, 14, base, name_of=lambda i: f"N{i}",
                   effect_text=lambda t: "E{0}", pools={6101: [21, 8]},
                   pawn_name=lambda p: "Lính " + str(p))
    assert v["slots"] == 1 and v["smithy_lv"] == 14 and v["need_lv"] == [14, 20]
    assert v["smelting"] is None
    (m,) = v["mains"]
    assert m["uid"] == "6101_10" and m["name"] == "N6101" and m["pawn_name"] == "Lính 3101"
    assert m["smelted_from"] == [6005] and m["pool"] == [21, 8]
    assert [(e["type"], e["smelted"]) for e in m["effects"]] == [(21, False), (8, True)]
    assert m["effects"][0]["text"] == "E5"
    assert [c["id"] for c in m["candidates"]] == [6005]
    assert m["candidates"][0]["name"] == "N6005" and m["candidates"][0]["in_pool"] is True
    assert v["raw"]["6005_1"]["uid"] == "6005_1"    # for the server-side preview
