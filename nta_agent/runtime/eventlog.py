"""Append-only JSONL event log for the operational spine."""
from __future__ import annotations

import json
import time
from pathlib import Path


class EventLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, obj: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def append(self, kind: str, detail=None) -> None:
        row = {"ts": time.time(), "kind": kind}
        if detail is not None:
            try:
                json.dumps(detail)
                row["detail"] = detail
            except (TypeError, ValueError):
                row["detail"] = str(detail)
        self._write(row)

    def tick(self, i: int, fired: list[str], state) -> None:
        r = state.resources
        self._write({"ts": time.time(), "kind": "tick", "i": i, "fired": fired,
                     "cereal": r.cereal, "timber": r.timber, "stone": r.stone})
