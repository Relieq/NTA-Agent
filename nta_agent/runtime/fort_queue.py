"""Persistent queue of Cứ Điểm (fort) cells waiting to be built.

A user 'build fort' click appends a cell here (dashboard process); the FortBuild
rule (agent process) retries create_city for each until resources allow, removing
it on success. Shared JSON file, atomic writes — same pattern as commands/control.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def load(path) -> list[int]:
    try:
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [int(x) for x in rows if isinstance(x, (int, str)) and str(x).lstrip("-").isdigit()]


def _save(path, items: list[int]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(items), encoding="utf-8")
    os.replace(tmp, p)


def add(path, index: int) -> None:
    items = load(path)
    if int(index) not in items:
        items.append(int(index))
        _save(path, items)


def remove(path, index: int) -> None:
    items = load(path)
    if int(index) in items:
        _save(path, [x for x in items if x != int(index)])
