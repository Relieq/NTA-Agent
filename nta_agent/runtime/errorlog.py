"""Structured error log for unattended (overnight) runs.

Writes one JSON object per error to ``errors.jsonl`` with enough context to
debug after the fact: timestamp, source (rule/service/session), kind, the parsed
game ecode + its Vietnamese reason, the message, a traceback (for exceptions),
and free-form context. ``summary()`` aggregates the file for a morning review.
"""
from __future__ import annotations

import json
import re
import time
import traceback
from collections import Counter
from pathlib import Path

_ECODE_RE = re.compile(r"ecode\.(\d+)")


def _ecode(text: str) -> str:
    m = _ECODE_RE.search(text or "")
    return m.group(1) if m else ""


class ErrorLog:
    def __init__(self, path, config=None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.config = config  # optional GameConfig for ecode -> reason

    def _reason(self, ecode: str) -> str:
        if not ecode or self.config is None:
            return ""
        try:
            row = self.config.table("ecode").get(ecode) or self.config.table("ecode").get(int(ecode)) or {}
            return row.get("vi") or row.get("en") or ""
        except Exception:
            return ""

    def _write(self, row: dict) -> None:
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            pass  # logging must never break the loop

    def log(self, source: str, kind: str, err, context=None) -> None:
        """Record one error. ``err`` may be an exception or a string."""
        if isinstance(err, BaseException):
            msg = str(err)
            tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))[-4000:]
        else:
            msg, tb = str(err), ""
        code = _ecode(msg)
        row = {"ts": time.time(), "source": source, "kind": kind, "msg": msg[:1000]}
        if code:
            row["ecode"] = code
            reason = self._reason(code)
            if reason:
                row["reason"] = reason
        if tb:
            row["traceback"] = tb
        if context is not None:
            try:
                json.dumps(context)
                row["context"] = context
            except (TypeError, ValueError):
                row["context"] = str(context)
        self._write(row)

    def rule_error(self, rule: str, exc, context=None) -> None:
        self.log(rule, "rule_error", exc, context)

    def summary(self, limit: int = 2000) -> dict:
        """Aggregate errors.jsonl for a quick morning review."""
        rows = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines()[-limit:]:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
        except OSError:
            return {"total": 0, "by_kind": {}, "by_source": {}, "by_ecode": {}, "recent": []}
        by_kind = Counter(r.get("kind", "?") for r in rows)
        by_source = Counter(r.get("source", "?") for r in rows)
        by_ecode = Counter(f'{r["ecode"]}:{r.get("reason", "")}' for r in rows if r.get("ecode"))
        return {"total": len(rows), "by_kind": dict(by_kind), "by_source": dict(by_source),
                "by_ecode": dict(by_ecode.most_common()),
                "recent": rows[-10:]}
