"""Persisted user decisions on fort recommendations (accept/reject)."""
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
    return {int(k): v for k, v in d.items() if v in ("accepted", "rejected")}


def update(path, index, decision) -> dict:
    d = load(path)
    idx = int(index)
    if decision in ("clear", "none"):
        d.pop(idx, None)
    elif decision in ("accept", "accepted"):
        d[idx] = "accepted"
    elif decision in ("reject", "rejected"):
        d[idx] = "rejected"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({str(k): v for k, v in d.items()}), encoding="utf-8")
    return d
