"""Exclusive (pawn-locked) equipment rules — pure, no I/O.

Spec: docs/superpowers/specs/2026-09-26-exclusive-equips-design.md. An effect attr
is ``[2, type, value, odds, smeltId]``; a non-zero ``smeltId`` marks an effect
smelted in from a common equip (engine EquipInfo.smeltEffects). The random pool of
an exclusive equip is PER MATCH (``HD_GetWorldRandomInfo.exclusiveMap``).
"""
from __future__ import annotations

SMELT_NEED_LV = (14, 20)  # engine EQUIP_SMELT_NEED_LV: Tiệm Rèn level per smelt slot


def is_exclusive(base: dict | None) -> bool:
    return bool(str((base or {}).get("exclusive_pawn", "") or "").strip())


def _effect_attrs(equip):
    for a in (equip or {}).get("attrs") or []:
        arr = a.get("attr") if isinstance(a, dict) else a
        if isinstance(arr, (list, tuple)) and len(arr) >= 3 and int(arr[0] or 0) == 2:
            yield arr


def natural_effects(equip) -> list[dict]:
    """The equip's own (recastable) effects — not the smelted ones."""
    out = []
    for arr in _effect_attrs(equip):
        if len(arr) > 4 and arr[4]:
            continue
        out.append({"type": int(arr[1]), "value": int(arr[2] or 0),
                    "odds": int(arr[3] or 0) if len(arr) > 3 else 0})
    return out


def smelted_types(equip) -> dict[int, int]:
    """``{effectType: vice equip id}`` for the effects smelted into this equip."""
    return {int(arr[1]): int(arr[4]) for arr in _effect_attrs(equip) if len(arr) > 4 and arr[4]}


def fixator_per_recast(equip, pool) -> int:
    """Fixators one recast costs (client getSmeltNeedFixatorCount + the lock):
    1 if an effect is locked (and still on the equip — else the engine drops the
    lock) + 1 per smelted effect whose type is in this match's pool."""
    pool = {int(t) for t in (pool or ())}
    lock = int((equip or {}).get("lockEffect") or 0)
    locked = 1 if lock and any(e["type"] == lock for e in natural_effects(equip)) else 0
    return locked + sum(1 for t in smelted_types(equip) if t in pool)


def smelt_slots(smithy_lv: int) -> int:
    """How many smelt slots Tiệm Rèn's level opens (0, 1 or 2)."""
    return sum(1 for lv in SMELT_NEED_LV if int(smithy_lv or 0) >= lv)


def _equip_id(equip) -> int:
    uid = str((equip or {}).get("uid", ""))
    if (equip or {}).get("id"):
        return int(equip["id"])
    return int(uid.split("_")[0]) if "_" in uid and uid.split("_")[0].isdigit() else 0


def vice_candidates(equips, base_of, *, main_uid: str) -> list[dict]:
    """Common equips that may be smelted into ``main_uid``: not exclusive, and not
    already smelted into ANOTHER exclusive equip (the game forbids reuse)."""
    used: set[int] = set()
    for e in equips or []:
        if str(e.get("uid")) != str(main_uid) and is_exclusive(base_of(_equip_id(e))):
            used |= set(smelted_types(e).values())
    out = []
    for e in equips or []:
        eid = _equip_id(e)
        if not eid or is_exclusive(base_of(eid)) or eid in used:
            continue
        out.append({"uid": str(e.get("uid")), "id": eid, "effects": natural_effects(e)})
    return sorted(out, key=lambda c: c["id"])


def smelt_preview(main, vices, pool) -> dict:
    """What a smelt would give: ``vices`` = [(vice id, vice EquipInfo)] per slot.
    The main keeps everything; each vice adds its effect. Also the fixators every
    later recast of the main would cost, and whether anything changes at all."""
    added = []
    for vid, v in vices:
        for eff in natural_effects(v):
            added.append({**eff, "from": int(vid)})
    def smelted(a) -> bool:
        arr = a.get("attr") if isinstance(a, dict) else a
        return len(arr) > 4 and int(arr[0] or 0) == 2 and bool(arr[4])

    # the new smelt replaces the old smelted effects; the main's own stats stay
    kept = [a for a in (main or {}).get("attrs") or [] if not smelted(a)]
    after = {**(main or {}), "attrs": kept + [
        {"attr": [2, x["type"], x["value"], x["odds"], x["from"]]} for x in added]}
    before = smelted_types(main)
    unchanged = before == {x["type"]: x["from"] for x in added}
    return {"added": added, "fixator_per_recast": fixator_per_recast(after, pool),
            "unchanged": unchanged}
