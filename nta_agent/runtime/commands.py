"""File-based dashboard->agent command channel (append-only + done-set)."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path


def append_command(path: Path, cmd: dict) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cid = uuid.uuid4().hex
    row = {"id": cid, "ts": time.time(), **cmd}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return cid


def _done_ids(done_path: Path) -> set[str]:
    try:
        text = Path(done_path).read_text(encoding="utf-8")
    except OSError:
        return set()
    return {ln.strip() for ln in text.splitlines() if ln.strip()}


def read_pending(commands_path: Path, done_path: Path) -> list[dict]:
    try:
        lines = Path(commands_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    done = _done_ids(done_path)
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict) and obj.get("id") and obj["id"] not in done:
            out.append(obj)
    return out


def mark_done(done_path: Path, cmd_id: str) -> None:
    done_path = Path(done_path)
    done_path.parent.mkdir(parents=True, exist_ok=True)
    with done_path.open("a", encoding="utf-8") as f:
        f.write(str(cmd_id) + "\n")
