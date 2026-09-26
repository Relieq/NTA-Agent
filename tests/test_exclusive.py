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
    base = {6005: {"exclusive_pawn": ""}, 6006: {"exclusive_pawn": ""},
            6101: {"exclusive_pawn": 3101}, 6102: {"exclusive_pawn": 3202}}.get
    equips = [_eq("6005_1", [(8, 40, 0)]), _eq("6006_3", [(15, 9, 0)]),
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
    same = smelt_preview(_eq("x", [(21, 5, 0), (8, 40, 0, 6005)]), [(6005, vices[0])], POOL)
    assert same["unchanged"] is True
