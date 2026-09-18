"""Per-equip forge targets set by the user: {equip_uid: {threshold, budget}}.

``threshold`` = target stat fraction (0..1) to stop recasting at; ``budget`` =
remaining iron the agent may spend recasting THAT equip (user can top up or
reduce). The agent decrements ``budget`` as it spends iron.
"""
from __future__ import annotations

import json
from pathlib import Path


def load(path) -> dict:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(d, dict):
        return {}
    out = {}
    for uid, cfg in d.items():
        if isinstance(cfg, dict):
            out[str(uid)] = {"threshold": float(cfg.get("threshold", 1.0) or 0.0),
                             "budget": int(cfg.get("budget", 0) or 0)}
    return out


def _save(path, d) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def set_target(path, uid, threshold, budget) -> dict:
    """Add/replace a main equip's target (user action)."""
    d = load(path)
    d[str(uid)] = {"threshold": max(0.0, min(1.0, float(threshold))), "budget": int(budget)}
    _save(path, d)
    return d


def remove(path, uid) -> dict:
    d = load(path)
    d.pop(str(uid), None)
    _save(path, d)
    return d


def spend(path, uid, amount) -> dict:
    """Decrement an item's remaining budget after the agent spends iron on it."""
    d = load(path)
    if str(uid) in d:
        d[str(uid)]["budget"] = max(0, d[str(uid)]["budget"] - int(amount))
        _save(path, d)
    return d
