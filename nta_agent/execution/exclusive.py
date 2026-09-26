"""Exclusive (pawn-locked) equipment rules — pure, no I/O.

Spec: docs/superpowers/specs/2026-09-26-exclusive-equips-design.md. An effect attr
is ``[2, type, value, odds, smeltId]``; a non-zero ``smeltId`` marks an effect
smelted in from a common equip (engine EquipInfo.smeltEffects). The random pool of
an exclusive equip is PER MATCH (``HD_GetWorldRandomInfo.exclusiveMap``).
"""
from __future__ import annotations

SMELT_NEED_LV = (14, 20)  # engine EQUIP_SMELT_NEED_LV: Tiệm Rèn level per smelt slot
SMITHY_ID = 2008          # Tiệm Rèn (engine BUILD_SMITHY_NID gates smelting)


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
    """Equips that may be smelted into ``main_uid`` (engine getCanSmeltEquips: a
    ``smelt_type`` equip with at least one effect), not already smelted into ANOTHER
    exclusive equip (the game forbids reuse)."""
    used: set[int] = set()
    for e in equips or []:
        if str(e.get("uid")) != str(main_uid) and is_exclusive(base_of(_equip_id(e))):
            used |= set(smelted_types(e).values())
    out = []
    for e in equips or []:
        eid = _equip_id(e)
        base = base_of(eid) or {}
        if not eid or is_exclusive(base) or not base.get("smelt_type") or eid in used:
            continue
        effects = natural_effects(e)
        if not effects:
            continue
        out.append({"uid": str(e.get("uid")), "id": eid, "effects": effects})
    return sorted(out, key=lambda c: c["id"])


def smelt_preview(main, vices, pool) -> dict:
    """What a smelt would give: ``vices`` = [(vice id, vice EquipInfo)] per slot.
    The main keeps its own stats; each vice adds its effects + half its main stats
    (engine updateEquipAttr). Also the fixators the smelt itself costs (1 per vice,
    onClickSmelting), those every later recast would cost, and whether anything
    changes at all."""
    added = []
    stats = {"hp": 0, "attack": 0}
    for vid, v in vices:
        for eff in natural_effects(v):
            added.append({**eff, "from": int(vid)})
        for a in (v or {}).get("attrs") or []:
            arr = a.get("attr") if isinstance(a, dict) else a
            if isinstance(arr, (list, tuple)) and len(arr) >= 3 and int(arr[0] or 0) == 0:
                key = {1: "hp", 2: "attack"}.get(int(arr[1] or 0))
                if key:
                    stats[key] += int(arr[2] or 0) // 2 + int(arr[2] or 0) % 2  # JS Math.round(v/2)
    def smelted(a) -> bool:
        arr = a.get("attr") if isinstance(a, dict) else a
        return len(arr) > 4 and int(arr[0] or 0) == 2 and bool(arr[4])

    # the new smelt replaces the old smelted effects; the main's own stats stay
    kept = [a for a in (main or {}).get("attrs") or [] if not smelted(a)]
    after = {**(main or {}), "attrs": kept + [
        {"attr": [2, x["type"], x["value"], x["odds"], x["from"]]} for x in added]}
    before = smelted_types(main)
    unchanged = before == {x["type"]: x["from"] for x in added}
    return {"added": added, "stats": stats, "fixator_cost": len(vices),
            "fixator_per_recast": fixator_per_recast(after, pool), "unchanged": unchanged}


def smelt_view(player, smithy_lv, base_of, *, name_of=None, effect_text=None, pools=None,
               pawn_name=None) -> dict:
    """Dashboard smelting tab: each exclusive equip (main) with its effects, what is
    smelted in, this match's pool and the equips it may take; the open slots (Tiệm
    Rèn level) and whether a smelt/forge is running. ``raw`` keeps the EquipInfo of
    every listed equip so the server can preview a choice without the game."""
    from nta_agent.execution.forge import _MARKUP

    def text(eff):
        tmpl = _MARKUP.sub("", (effect_text(eff["type"]) if effect_text else None) or "")
        return (tmpl.replace("{0}", str(eff["value"])).replace("{1}", f"{eff['odds']}%")
                if tmpl else f"hiệu ứng #{eff['type']}")

    equips = [e for e in (player or {}).get("equips") or [] if isinstance(e, dict)]
    raw, mains = {}, []
    for e in equips:
        eid = _equip_id(e)
        base = base_of(eid) or {}
        if not is_exclusive(base):
            continue
        pool = [int(t) for t in (pools or {}).get(eid) or []]
        smelted = smelted_types(e)
        effects = []
        for arr in _effect_attrs(e):
            eff = {"type": int(arr[1]), "value": int(arr[2] or 0),
                   "odds": int(arr[3] or 0) if len(arr) > 3 else 0}
            sid = int(arr[4]) if len(arr) > 4 and arr[4] else 0
            effects.append({**eff, "text": text(eff), "smelted": bool(sid), "from": sid})
        cands = []
        for c in vice_candidates(equips, base_of, main_uid=str(e.get("uid"))):
            cands.append({**c, "name": (name_of(c["id"]) if name_of else None) or f"#{c['id']}",
                          "in_pool": any(x["type"] in pool for x in c["effects"]),
                          "effects": [{**x, "text": text(x)} for x in c["effects"]]})
            raw[c["uid"]] = next(q for q in equips if str(q.get("uid")) == c["uid"])
        raw[str(e.get("uid"))] = e
        pawn = str(base.get("exclusive_pawn") or "")
        mains.append({"uid": str(e.get("uid")), "id": eid,
                      "name": (name_of(eid) if name_of else None) or f"#{eid}",
                      "pawn_id": int(pawn) if pawn.isdigit() else 0,
                      "pawn_name": (pawn_name(pawn) if pawn_name else None) or pawn,
                      "effects": effects, "smelted_from": sorted(set(smelted.values())),
                      "pool": pool, "candidates": cands})
    return {"smithy_lv": int(smithy_lv or 0), "need_lv": list(SMELT_NEED_LV),
            "slots": smelt_slots(smithy_lv), "fixator": int((player or {}).get("fixator") or 0),
            "smelting": (player or {}).get("currSmeltEquip") or None,
            "forging": (player or {}).get("currForgeEquip") or None,
            "mains": mains, "raw": raw}
