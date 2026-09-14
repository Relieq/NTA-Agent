"""Tactics profile: the contract the hands obey (army + occupy policy).

Persisted JSON with defaults; loaded each tick. Later authored by brain/chat
(Track B B3/B4); for now hand/dashboard-editable. See the Track B design.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROFILE = {
    "army": {"group": [], "roles": {}, "onetile": True, "composition": {}},
    "occupy": {"max_loss": 0.0, "max_march_ms": 0,
               "loot": {"enabled": True, "min_reward_per_chest": 0.0}},
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            out[k] = _merge(base[k], v)
        else:
            out[k] = v
    return out


@dataclass
class Profile:
    army: dict
    occupy: dict


def load_profile(path) -> Profile:
    """Load the profile, deep-merged over defaults. Missing/invalid → defaults."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        data = {}
    merged = _merge(DEFAULT_PROFILE, data if isinstance(data, dict) else {})
    return Profile(army=merged["army"], occupy=merged["occupy"])


def save_profile(profile: Profile, path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"army": profile.army, "occupy": profile.occupy},
                            ensure_ascii=False, indent=1), encoding="utf-8")


def composition_target(profile: Profile, area_armys: list, unlocked_ids) -> tuple | None:
    """The biggest unmet composition gap as ``(army_uid, pawn_id)``, or None.

    ``profile.army.composition`` = {armyUid: {pawnId: targetCount}}. Only pawns in
    ``unlocked_ids`` are eligible. Picks the largest positive (target - current) gap.
    """
    comp = (profile.army or {}).get("composition") or {}
    unlocked = {int(x) for x in (unlocked_ids or [])}
    by_uid = {str(a.get("uid")): a for a in area_armys}
    best = None  # (gap, army_uid, pawn_id)
    for army_uid, targets in comp.items():
        army = by_uid.get(str(army_uid))
        have: dict[int, int] = {}
        for p in (army.get("pawns") if army else []) or []:
            have[int(p.get("id", 0))] = have.get(int(p.get("id", 0)), 0) + 1
        for pid_str, want in (targets or {}).items():
            pid = int(pid_str)
            if pid not in unlocked:
                continue
            gap = int(want) - have.get(pid, 0)
            if gap > 0 and (best is None or gap > best[0]):
                best = (gap, str(army_uid), pid)
    return (best[1], best[2]) if best else None
