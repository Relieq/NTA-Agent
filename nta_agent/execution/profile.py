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
