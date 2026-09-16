"""Validate + clamp LLM-proposed profile edits before applying."""
from __future__ import annotations

_ROLES = {"archer", "tank"}


def _num(v, lo, hi, default):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def sanitize_edits(edits: dict, profile, valid_army_uids) -> dict:
    valid = {str(u) for u in (valid_army_uids or ())}
    out: dict = {}

    occ_in = edits.get("occupy") if isinstance(edits, dict) else None
    if isinstance(occ_in, dict):
        occ: dict = {}
        if "max_loss" in occ_in:
            occ["max_loss"] = _num(occ_in["max_loss"], 0, 100, profile.occupy["max_loss"])
        if "max_march_ms" in occ_in:
            occ["max_march_ms"] = int(_num(occ_in["max_march_ms"], 0, 10 ** 9, 0))
        loot_in = occ_in.get("loot")
        if isinstance(loot_in, dict):
            loot: dict = {}
            if "enabled" in loot_in:
                v = loot_in["enabled"]
                loot["enabled"] = (v.lower() in ("1", "true", "yes")
                                   if isinstance(v, str) else bool(v))
            if "min_reward_per_chest" in loot_in:
                loot["min_reward_per_chest"] = _num(loot_in["min_reward_per_chest"], 0, 10 ** 9, 0)
            if loot:
                occ["loot"] = loot
        if occ:
            out["occupy"] = occ

    army_in = edits.get("army") if isinstance(edits, dict) else None
    if isinstance(army_in, dict):
        army: dict = {}
        if isinstance(army_in.get("group"), list):
            army["group"] = [str(u) for u in army_in["group"] if str(u) in valid]
        if isinstance(army_in.get("roles"), dict):
            army["roles"] = {str(u): r for u, r in army_in["roles"].items()
                             if str(u) in valid and r in _ROLES}
        if "onetile" in army_in:
            army["onetile"] = bool(army_in["onetile"])
        if isinstance(army_in.get("composition"), dict):
            comp: dict = {}
            for u, targets in army_in["composition"].items():
                if str(u) in valid and isinstance(targets, dict):
                    comp[str(u)] = {str(pid): int(_num(c, 0, 10 ** 6, 0))
                                    for pid, c in targets.items()}
            if comp:
                army["composition"] = comp
        if army:
            out["army"] = army
    return out
