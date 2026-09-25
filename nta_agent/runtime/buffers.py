"""buffers.json — the buffer-leveling proposal, its approval and each buffer's phase.

The agent (BufferLeveling) writes the proposal and phases; the dashboard sets
``approved`` when the player confirms. Atomic writes (tmp + replace), like the
other shared files. Spec: docs/superpowers/specs/2026-09-25-buffer-leveling-design.md.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def _default() -> dict:
    return {"proposal": None, "approved": False, "setup_done": False, "buffers": {}}


def load(path) -> dict:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _default()
    return {**_default(), **d} if isinstance(d, dict) else _default()


def save(path, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def approve(path) -> dict:
    d = load(path)
    d["approved"] = True
    save(path, d)
    return d


def set_proposal(path, proposal: dict) -> dict:
    """A changed proposal needs a fresh approval (and a fresh setup)."""
    d = load(path)
    d.update(proposal=proposal, approved=False, setup_done=False)
    save(path, d)
    return d
