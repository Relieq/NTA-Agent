"""Single authority for every filesystem location (dev repo vs packaged app).

Packaged layout (spec 2026-09-24-packaging-design.md):
    <root>/VERSION, <root>/runtime/{python,node}, <root>/app/nta_agent   (replaced by updates)
    %LOCALAPPDATA%/NTA-Agent/...                                         (user data, kept)
Dev (running from the repo): today's paths under the repo (build/, nta_agent/data/config, ...).
"""
from __future__ import annotations

import os
from pathlib import Path

_APP = Path(__file__).resolve().parents[1]  # repo root (dev) or <root>/app (packaged)


def app_dir() -> Path:
    return _APP


def root_dir() -> Path:
    return _APP.parent


def is_packaged(root: Path | None = None) -> bool:
    r = root if root is not None else root_dir()
    return (r / "runtime").is_dir() and (r / "VERSION").is_file()


def data_dir() -> Path:
    env = os.environ.get("NTA_DATA_DIR")
    if env:
        return Path(env)
    if is_packaged():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "NTA-Agent"
    return _APP / "build"


def run_dir() -> Path:
    return data_dir() / "run"


def token_path() -> Path:
    return data_dir() / ("token.txt" if is_packaged() else "nta_token.txt")


def gamedata_dir() -> Path:
    return data_dir() / "gamedata"


def config_dir() -> Path:
    if is_packaged():
        return gamedata_dir() / "config"
    return _APP / "nta_agent" / "data" / "config"


def engine_js() -> Path:
    if is_packaged():
        return gamedata_dir() / "engine" / "index.js"
    return _APP / "tools" / "re" / "decrypted" / "index.js"


def settings_path() -> Path:
    return data_dir() / "settings.json"


def backups_dir() -> Path:
    return data_dir() / "backups"


def node_exe() -> str:
    if is_packaged():
        return str(root_dir() / "runtime" / "node" / "node.exe")
    return "node"


def app_version() -> str:
    if not is_packaged():
        return "dev"
    try:
        return (root_dir() / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "dev"
