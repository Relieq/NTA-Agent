"""Deterministic forge decisions (equipment).

User rules (2026-09-18, see memory nta-agent-forge-leveling):
- Only forge COMMON equipment (``equipBase.exclusive_pawn`` empty); never the
  specialized (pawn-locked) ones.
- Baseline: forge each un-forged common equip once.
- For user-designated MAIN equips, recast toward a PER-ITEM threshold within a
  PER-ITEM iron budget. No RestoreForge (too costly) — we simply stop as soon as
  a roll meets the threshold, so we keep it.

Pure over an explicit interface (normalized equip dicts + a base lookup), so no
live-shape guessing leaks into the tested logic; the raw→normalized adapter is
wired/verified separately when equipment exists.
"""
from __future__ import annotations

from dataclasses import dataclass

# CType -> resource name (engine enum, verified: 1 cereal,2 timber,3 stone,9 iron…).
CTYPE = {1: "cereal", 2: "timber", 3: "stone", 5: "gold", 7: "exp_book",
         9: "iron", 13: "up_scroll", 14: "fixator"}


def parse_cost(s) -> dict:
    """``"2,0,357|3,0,357|9,0,3"`` -> ``{"timber":357,"stone":357,"iron":3}``.

    Each ``ctype,_,amount`` segment; the resource name comes from :data:`CTYPE`."""
    out: dict[str, int] = {}
    for seg in str(s or "").split("|"):
        parts = seg.split(",")
        if len(parts) >= 3:
            try:
                name = CTYPE.get(int(parts[0]))
                if name:
                    out[name] = out.get(name, 0) + int(parts[-1])
            except (ValueError, TypeError):
                continue
    return out


def affordable(cost: dict, resources: dict) -> bool:
    return all(int(resources.get(k, 0) or 0) >= v for k, v in cost.items())


def craft_candidates(equip_slots, base_of, crafted_ids, *, novice=False):
    """Unlocked equip slots to CRAFT (materialize) via the first forge.

    ``equip_slots``: ``player.equipSlots`` = ``{slotKey: {"id":?, "lv":n, ...}}``.
    A slot with a chosen ``id`` whose equip is COMMON and not yet in ``crafted_ids``
    yields a craft: uid ``"<id>_<lv>"`` (engine EquipSlotObj.uid = id_lv), with its
    forge cost. Specialized (pawn-locked) equips are left for the human."""
    out = []
    for slot in (equip_slots or {}).values():
        if not isinstance(slot, dict):
            continue
        eid = int(slot.get("id", 0) or 0)
        if not eid or eid in crafted_ids:
            continue
        base = base_of(eid) or {}
        if not is_common(base):
            continue
        cost_key = "forge_cost_novice" if novice else "forge_cost"
        cost = parse_cost(base.get(cost_key) or base.get("forge_cost"))
        out.append({"uid": f"{eid}_{int(slot.get('lv', 0) or 0)}", "id": eid, "cost": cost})
    return out


def parse_range(s) -> tuple[int, int] | None:
    """``"6,15"`` -> ``(6, 15)``; empty/invalid -> None."""
    try:
        lo, hi = (int(x) for x in str(s).split(","))
        return lo, hi
    except (ValueError, TypeError):
        return None


def is_common(base: dict) -> bool:
    """Common equipment (agent may forge) is not locked to a pawn."""
    return not str((base or {}).get("exclusive_pawn", "") or "").strip()


def stat_fraction(equip: dict, base: dict) -> float | None:
    """Where the equip's forgeable stat sits in its range (0..1), or None.

    Uses whichever of attack/hp carries a range in the base row."""
    for key in ("attack", "hp"):
        rng = parse_range((base or {}).get(key, ""))
        if rng is None:
            continue
        lo, hi = rng
        if hi <= lo:
            return 1.0
        cur = int((equip or {}).get(key, 0) or 0)
        return max(0.0, min(1.0, (cur - lo) / (hi - lo)))
    return None


@dataclass
class ForgeDecision:
    uid: str
    kind: str   # "forge" (baseline, once) | "recast" (toward the item's threshold)
    cost: int   # iron spent (0 when a free recast is used)


def _forge_cost(base: dict) -> int:
    return int((base or {}).get("forge_cost", 0) or 0)


def next_forge(equips, base_of, targets=None, *, iron=0, free_count=0, busy=False):
    """The next forge action, or None.

    ``equips``: normalized dicts ``{uid, id, is_forged, attack, hp, recast_count,
    next_forge_free}``. ``base_of(id)`` -> equipBase row (attack/hp ranges,
    forge_cost, reforge_count, exclusive_pawn). ``targets``: ``{uid: {"threshold":
    0..1, "budget": remaining_iron}}`` for main equips. ``busy``: an equip is
    mid-forge (server allows one at a time)."""
    if busy:
        return None
    targets = targets or {}

    def cost_for(base, equip):
        if free_count > 0 or (equip or {}).get("next_forge_free"):
            return 0
        return _forge_cost(base)

    # Baseline: forge each un-forged common equip once.
    for e in equips:
        base = base_of(e.get("id"))
        if not is_common(base) or e.get("is_forged"):
            continue
        c = cost_for(base, e)
        if c == 0 or iron >= c:
            return ForgeDecision(uid=str(e.get("uid")), kind="forge", cost=c)

    # Recast targeted main equips toward their per-item threshold, within budget.
    by_uid = {str(e.get("uid")): e for e in equips}
    for uid, cfg in targets.items():
        e = by_uid.get(str(uid))
        if e is None:
            continue
        base = base_of(e.get("id"))
        if not is_common(base):
            continue
        reforge_max = int((base or {}).get("reforge_count", 0) or 0)
        if reforge_max and int(e.get("recast_count", 0) or 0) >= reforge_max:
            continue  # hit the recast cap
        frac = stat_fraction(e, base)
        if frac is None or frac >= float(cfg.get("threshold", 1.0)):
            continue  # already good enough
        c = cost_for(base, e)
        if c > 0 and (int(cfg.get("budget", 0) or 0) < c or iron < c):
            continue  # out of this item's iron budget or global iron
        return ForgeDecision(uid=str(uid), kind="recast", cost=c)
    return None
