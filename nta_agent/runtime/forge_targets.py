"""Per-equip recast targets set by the user: {equip_uid: {mins, threshold, budget}}.

``mins`` = per-stat minimums ``{"<effectType>.value"|"<effectType>.odds": min}``
(user 2026-09-24: each equip gets its own criteria — an effect line can carry two
numbers); every set minimum must hold to stop. ``threshold`` = legacy composite
effect quality (0..1), used only when no mins. ``budget`` = remaining iron the
agent may spend recasting THAT equip; decremented as it spends.
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
            t = {"threshold": float(cfg.get("threshold", 1.0) or 0.0),
                 "budget": int(cfg.get("budget", 0) or 0)}
            mins = cfg.get("mins")
            if isinstance(mins, dict):
                t["mins"] = {str(k): float(v) for k, v in mins.items()
                             if isinstance(v, (int, float))}
            out[str(uid)] = t
    return out


def _save(path, d) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def set_target(path, uid, threshold, budget, mins: dict | None = None) -> dict:
    """Add/replace a main equip's target (user action)."""
    d = load(path)
    d[str(uid)] = {"threshold": max(0.0, min(1.0, float(threshold))), "budget": int(budget)}
    if mins:
        d[str(uid)]["mins"] = {str(k): float(v) for k, v in mins.items()}
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
