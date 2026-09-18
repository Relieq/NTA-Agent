"""Tactics profile: the contract the hands obey (army + occupy policy).

Persisted JSON with defaults; loaded each tick. Later authored by brain/chat
(Track B B3/B4); for now hand/dashboard-editable. See the Track B design.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROFILE = {
    "army": {"group": [], "roles": {}, "onetile": True, "composition": {},
             "active": "", "presets": {}},
    "occupy": {"max_loss": 0.0, "max_march_ms": 0, "expansion": "none",
               "loot": {"enabled": True, "min_reward_per_chest": 0.0}},
    "notes": [],
    "build": {"order": [], "skip": []},
}


def _merge(base: dict, over: dict) -> dict:
    # deep-copy so the returned profile never shares mutable state with DEFAULT_PROFILE
    # (rules/brain mutate the profile in place).
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            out[k] = _merge(base[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


@dataclass
class Profile:
    army: dict
    occupy: dict
    notes: list
    build: dict


def load_profile(path) -> Profile:
    """Load the profile, deep-merged over defaults. Missing/invalid → defaults."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        data = {}
    merged = _merge(DEFAULT_PROFILE, data if isinstance(data, dict) else {})
    return Profile(army=merged["army"], occupy=merged["occupy"], notes=merged["notes"],
                   build=merged["build"])


def save_profile(profile: Profile, path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"army": profile.army, "occupy": profile.occupy,
                             "notes": profile.notes, "build": profile.build},
                            ensure_ascii=False, indent=1), encoding="utf-8")


def active_formation(profile: Profile) -> dict:
    """The active preset's formation, or the flat army fields when none is active."""
    name = (profile.army or {}).get("active") or ""
    preset = (profile.army.get("presets") or {}).get(name)
    src = preset if preset else profile.army
    return {"group": src.get("group", []), "roles": src.get("roles", {}),
            "onetile": src.get("onetile", True), "composition": src.get("composition", {})}


def apply_edits(profile: Profile, clean: dict) -> bool:
    """Merge sanitized edits (occupy/army/presets/notes/active) into the profile in
    place. Activating a preset syncs its fields into the flat army.*. Returns
    whether anything changed."""
    changed = False
    if isinstance(clean.get("occupy"), dict):
        for k, v in clean["occupy"].items():
            if profile.occupy.get(k) != v:
                profile.occupy[k] = v
                changed = True
    if isinstance(clean.get("army"), dict):
        for k, v in clean["army"].items():
            if k == "presets" and isinstance(v, dict):
                for name, preset in v.items():
                    if profile.army["presets"].get(name) != preset:
                        profile.army["presets"][name] = preset
                        changed = True
            elif profile.army.get(k) != v:
                profile.army[k] = v
                changed = True
    if "notes" in clean and clean["notes"] != profile.notes:
        profile.notes = list(clean["notes"])
        changed = True
    if isinstance(clean.get("build"), dict):
        for k, v in clean["build"].items():
            if profile.build.get(k) != v:
                profile.build[k] = list(v)
                changed = True
    active = profile.army.get("active") or ""
    preset = (profile.army.get("presets") or {}).get(active)
    if preset:
        for k in ("group", "roles", "onetile", "composition"):
            if k in preset and profile.army.get(k) != preset[k]:
                profile.army[k] = preset[k]
                changed = True
    return changed


def composition_target(profile: Profile, area_armys: list, unlocked_ids,
                       composition: dict | None = None) -> tuple | None:
    """The biggest unmet composition gap as ``(army_uid, pawn_id)``, or None.

    Composition = {armyUid: {pawnId: targetCount}} — from ``composition`` when
    given (e.g. the active preset's), else ``profile.army.composition``. Only
    pawns in ``unlocked_ids`` are eligible; picks the largest positive gap.
    """
    comp = composition if composition is not None else ((profile.army or {}).get("composition") or {})
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
