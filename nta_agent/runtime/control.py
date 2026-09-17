"""File-based control channel between the dashboard and the agent loop."""
from __future__ import annotations

import json
from pathlib import Path


def read_mode(path) -> str:
    """Return 'stop', 'pause', or 'run' from control.json (missing/bad -> 'run')."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "run"
    if not isinstance(d, dict):
        return "run"
    if d.get("stop"):
        return "stop"
    return "pause" if d.get("paused") else "run"


def write_control(path, *, paused=None, stop=None) -> None:
    """Merge the given flags into control.json (create parent dir)."""
    path = Path(path)
    try:
        cur = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(cur, dict):
            cur = {}
    except (OSError, ValueError):
        cur = {}
    if paused is not None:
        cur["paused"] = bool(paused)
    if stop is not None:
        cur["stop"] = bool(stop)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cur), encoding="utf-8")


def reset(path) -> None:
    """Clear both flags (fresh start)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"paused": False, "stop": False}), encoding="utf-8")
