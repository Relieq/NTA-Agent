"""Deterministic, bounded ledger of real failures for the brain to learn from.

Hands (the deterministic loop) append facts here — troop losses, repeated
resource blocks, stuck goals — so the brain can read grounded outcomes in its
digest instead of guessing. The ledger never interprets; interpretation (and any
"lesson" drawn from it) is the brain's job, and every lesson must cite an event
id that ``has()`` confirms is real (see ``brain/lessons.py``, ``brain/guard.py``).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class FailureEvent:
    id: str
    ts: float
    kind: str            # "battle_loss" | "res_depletion" | "stuck_goal"
    context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> FailureEvent:
        return cls(id=str(d.get("id", "")), ts=float(d.get("ts", 0) or 0),
                   kind=str(d.get("kind", "")), context=dict(d.get("context") or {}))


class FailureLedger:
    def __init__(self, path, cap: int = 100) -> None:
        self.path = Path(path)
        self.cap = int(cap)
        self._seq = 0
        self._events: list[FailureEvent] = self._load()

    def _load(self) -> list[FailureEvent]:
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [FailureEvent.from_dict(r) for r in rows if isinstance(r, dict)]

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps([e.to_dict() for e in self._events],
                                      ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass  # never break the loop over ledger I/O

    def record(self, kind: str, context: dict) -> str:
        self._seq += 1
        eid = f"{int(time.time() * 1000)}-{self._seq}"
        self._events.append(FailureEvent(id=eid, ts=time.time(), kind=str(kind),
                                         context=dict(context or {})))
        if len(self._events) > self.cap:
            self._events = self._events[-self.cap:]
        self._save()
        return eid

    def all(self) -> list[FailureEvent]:
        return list(self._events)

    def recent(self, n: int = 10, kind: str | None = None) -> list[FailureEvent]:
        evs = [e for e in self._events if kind is None or e.kind == kind]
        return list(reversed(evs[-n:]))

    def has(self, event_id: str) -> bool:
        return any(e.id == event_id for e in self._events)

    def aggregate_res(self, window_s: float) -> dict[str, int]:
        if window_s <= 0:
            return {}  # a zero-length window contains nothing
        cutoff = time.time() - float(window_s)
        out: dict[str, int] = {}
        for e in self._events:
            if e.kind == "res_depletion" and e.ts >= cutoff:
                r = e.context.get("resource")
                if r:
                    out[str(r)] = out.get(str(r), 0) + 1
        return out
