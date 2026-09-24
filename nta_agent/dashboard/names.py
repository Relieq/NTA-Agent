"""Map building ids to Vietnamese display names from config (buildText.json)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from nta_agent import paths

_NAME_KEY = re.compile(r"^name_(\d+)$")


def load_build_names(config_dir: Path | None = None) -> dict[int, str]:
    path = Path(config_dir or paths.config_dir()) / "buildText.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    names: dict[int, str] = {}
    for r in rows if isinstance(rows, list) else []:
        m = _NAME_KEY.match(str(r.get("id", "")))
        if not m:
            continue
        label = (r.get("vi") or r.get("en") or "").strip()
        if label:
            names[int(m.group(1))] = label
    return names


def build_label(names: dict[int, str], build_id: int) -> str:
    return names.get(build_id, f"#{build_id}")
