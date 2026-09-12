"""Pure readers for the operational-spine seam files (state.json, events.jsonl)."""
from __future__ import annotations

import json
from pathlib import Path


def read_state(path: Path) -> dict:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return {"ok": False}
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return {"ok": False}
    if not isinstance(data, dict):
        return {"ok": False}
    return {"ok": True, **data}


def read_json_array(path: Path) -> list:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    return data if isinstance(data, list) else []


def tail_events(path: Path, n: int = 50) -> list[dict]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines[-n:] if n > 0 else []:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out
