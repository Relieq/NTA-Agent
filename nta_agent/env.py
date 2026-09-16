"""Tiny .env loader (stdlib, no dependency).

Loads KEY=VALUE lines from a .env file into os.environ *without overriding*
values already set in the real environment. Called once at CLI entry so
`OPENAI_API_KEY`, `NTA_*`, etc. can live in a gitignored .env.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | os.PathLike = ".env") -> None:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:  # real env wins
            os.environ[key] = val
