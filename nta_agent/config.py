"""Environment configuration and auto-detection for the BlueStacks/ADB target.

Everything the agent needs to reach the emulator is resolved here so the rest of the
codebase never hard-codes a path or a port. Values can be overridden via environment
variables (prefix ``NTA_``) for machines where BlueStacks is installed elsewhere.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

# Default install locations on this machine (verified 2026-09-01).
_DEFAULT_ADB = Path(r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe")
_BLUESTACKS_CONF = Path(r"C:\ProgramData\BlueStacks_nxt\bluestacks.conf")

# The emulator renders the game at this resolution; combat/coordinate math assumes it.
DEFAULT_SCREEN_W = 1600
DEFAULT_SCREEN_H = 900


def _find_adb() -> str:
    """Locate an adb binary: NTA_ADB_PATH → bundled HD-Adb.exe → adb on PATH."""
    override = os.environ.get("NTA_ADB_PATH")
    if override:
        return override
    if _DEFAULT_ADB.exists():
        return str(_DEFAULT_ADB)
    on_path = shutil.which("adb")
    if on_path:
        return on_path
    # Fall back to the bundled path even if missing, so errors point somewhere concrete.
    return str(_DEFAULT_ADB)


def _detect_adb_port(conf: Path = _BLUESTACKS_CONF) -> int | None:
    """Read the emulator's adb port from bluestacks.conf, if present."""
    try:
        text = conf.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    # Prefer the live status port, fall back to the configured one.
    for key in ("status.adb_port", "adb_port"):
        m = re.search(rf'bst\.instance\.\w+\.{key}="(\d+)"', text)
        if m:
            return int(m.group(1))
    return None


@dataclass(frozen=True)
class Settings:
    adb_path: str
    serial: str | None
    screen_w: int = DEFAULT_SCREEN_W
    screen_h: int = DEFAULT_SCREEN_H
    game_package: str = "twgame.global.acers"

    @classmethod
    def detect(cls) -> "Settings":
        serial = os.environ.get("NTA_ADB_SERIAL")
        if not serial:
            port = _detect_adb_port()
            serial = f"127.0.0.1:{port}" if port else None
        return cls(adb_path=_find_adb(), serial=serial)


def load_settings() -> Settings:
    return Settings.detect()
