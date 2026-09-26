"""Grounded, bounded store of tactical lessons the brain distills from failures.

A lesson maps a recurring situation (trigger) to a resolution (a safe lever edit
the hands apply, or advice for the human). Each lesson MUST cite evidence — event
ids from the failure ledger — which the guard verifies before a lesson is stored,
so lessons are grounded in real outcomes, never the LLM's invention. Lessons are
fed back into the digest so the brain remembers what it learned.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Lesson:
    id: str
    trigger: dict
    diagnosis: str
    resolution: dict
    evidence: list = field(default_factory=list)
    created: float = 0.0
    last_seen: float = 0.0
    times_seen: int = 1
    validated_by: str | None = None
    status: str = "active"          # "active" | "retired"
    pinned: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Lesson:
        return cls(
            id=str(d.get("id", "")), trigger=dict(d.get("trigger") or {}),
            diagnosis=str(d.get("diagnosis", "")), resolution=dict(d.get("resolution") or {}),
            evidence=list(d.get("evidence") or []),
            created=float(d.get("created", 0) or 0), last_seen=float(d.get("last_seen", 0) or 0),
            times_seen=int(d.get("times_seen", 1) or 1),
            validated_by=d.get("validated_by"),
            status=str(d.get("status", "active")), pinned=bool(d.get("pinned", False)))


def _canon(trigger: dict) -> str:
    return json.dumps(trigger or {}, sort_keys=True, ensure_ascii=False)


def match_lessons(lessons, situation: dict) -> list[Lesson]:
    """Active lessons whose trigger applies to the current situation (Inc 3 recall).

    situation = {"kind": str, "monster_ids": [int]?, "resource": str?, "goal": str?}.
    A lesson matches when trigger.kind == situation.kind AND every trigger.match
    constraint is satisfied (monster_id in situation.monster_ids; resource/goal equal).
    A lesson with no match constraints matches its kind broadly. Accepts Lesson
    objects or dicts; returns Lesson objects."""
    kind = situation.get("kind")
    monster_ids = {int(m) for m in (situation.get("monster_ids") or [])}
    out: list[Lesson] = []
    for le in lessons or []:
        lz = le if isinstance(le, Lesson) else Lesson.from_dict(le)
        if lz.status == "retired" or (lz.trigger or {}).get("kind") != kind:
            continue
        match = (lz.trigger or {}).get("match") or {}
        if match.get("monster_id") is not None and int(match["monster_id"]) not in monster_ids:
            continue
        if match.get("resource") is not None and match["resource"] != situation.get("resource"):
            continue
        if match.get("goal") is not None and match["goal"] != situation.get("goal"):
            continue
        out.append(lz)
    return out


class LessonStore:
    def __init__(self, path, cap: int = 50) -> None:
        self.path = Path(path)
        self.cap = int(cap)
        self._seq = 0
        self._lessons: list[Lesson] = self._load()

    def _load(self) -> list[Lesson]:
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [Lesson.from_dict(r) for r in rows if isinstance(r, dict)]

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps([le.to_dict() for le in self._lessons],
                                      ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def _find(self, trigger: dict) -> Lesson | None:
        key = _canon(trigger)
        return next((le for le in self._lessons if _canon(le.trigger) == key), None)

    def upsert(self, data: dict) -> str:
        """Add a new lesson or, if one with the same trigger exists, refresh it.

        ``data`` is a plain dict (as produced by guard.sanitize_lessons). Returns the
        lesson id (existing one on a dedup hit), or "" when every cited failure was
        already dismissed by the player (a retired lesson cites it): re-proposing a
        retired lesson from the same evidence must not bring it back."""
        now = time.time()
        dismissed = {ev for le in self._lessons if le.status == "retired" for ev in le.evidence}
        ev_in = list(data.get("evidence") or [])
        if ev_in and all(ev in dismissed for ev in ev_in):
            return ""
        existing = self._find(data.get("trigger") or {})
        if existing is not None:
            existing.last_seen = now
            existing.times_seen += 1
            existing.diagnosis = data.get("diagnosis", existing.diagnosis)
            existing.resolution = data.get("resolution", existing.resolution)
            for ev in (data.get("evidence") or []):
                if ev not in existing.evidence:
                    existing.evidence.append(ev)
            if data.get("validated_by"):
                existing.validated_by = data["validated_by"]
            if existing.status == "retired":
                existing.status = "active"  # it recurred — revive it
            self._save()
            return existing.id
        self._seq += 1
        le = Lesson(
            id=f"{int(now * 1000)}-{self._seq}",
            trigger=dict(data.get("trigger") or {}),
            diagnosis=str(data.get("diagnosis", "")),
            resolution=dict(data.get("resolution") or {}),
            evidence=list(data.get("evidence") or []),
            created=now, last_seen=now, validated_by=data.get("validated_by"))
        self._lessons.append(le)
        self._enforce_cap()
        self._save()
        return le.id

    def _enforce_cap(self) -> None:
        if len(self._lessons) <= self.cap:
            return
        # keep pinned lessons; evict the oldest-seen of the rest first
        pinned = [le for le in self._lessons if le.pinned]
        rest = sorted((le for le in self._lessons if not le.pinned),
                      key=lambda le: le.last_seen, reverse=True)
        self._lessons = (pinned + rest)[: self.cap]

    def all(self) -> list[Lesson]:
        return list(self._lessons)

    def active(self) -> list[Lesson]:
        return [le for le in self._lessons if le.status != "retired"]

    def retire(self, lesson_id: str) -> None:
        for le in self._lessons:
            if le.id == lesson_id:
                le.status = "retired"
        self._save()

    def pin(self, lesson_id: str) -> None:
        for le in self._lessons:
            if le.id == lesson_id:
                le.pinned = True
        self._save()
