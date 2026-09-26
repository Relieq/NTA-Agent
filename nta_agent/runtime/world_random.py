"""world_random.json — this match's random config (HD_GetWorldRandomInfo).

The effect pool of each EXCLUSIVE equip is per match (not equipBase.effect), so the
agent fetches it at start and refreshes it now and then; the Forge rule and the
dashboard read the file. A failed fetch keeps the last good file.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def load(path) -> dict[int, list[int]]:
    """``{exclusive equipId: [effectType]}`` (empty when not fetched yet)."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {int(k): [int(t) for t in v] for k, v in (d.get("exclusive") or {}).items()}


def refresh(actions, path, *, now: float | None = None, every_s: float = 0.0) -> bool:
    """Fetch and write the file unless it is younger than ``every_s``. True if written."""
    now = time.time() if now is None else now
    p = Path(path)
    try:
        at = float(json.loads(p.read_text(encoding="utf-8")).get("at", 0))
    except (OSError, ValueError):
        at = None
    if at is not None and every_s and now - at < every_s:
        return False
    try:
        info = actions.get_world_random_info() or {}
    except Exception:
        return False  # keep the last good file
    data = {"exclusive": {str(k): v for k, v in (info.get("exclusive") or {}).items()},
            "pawn_cost": {str(k): v for k, v in (info.get("pawn_cost") or {}).items()},
            "at": now}
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, p)
    return True
