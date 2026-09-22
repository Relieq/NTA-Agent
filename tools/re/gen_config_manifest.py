"""Generate / verify the config manifest — F2 regression guard.

The manifest pins the game version and a sha256 fingerprint + row count of every
``nta_agent/data/config/*.json`` table. It is the anchor for detecting drift when
the game updates and config tables are re-extracted.

Workflow on a game update:
  1. Bump ``GAME_VERSION`` in ``nta_agent/version.py`` and re-extract config
     (``tools/re/extract_config.py``).
  2. Run ``python tools/re/gen_config_manifest.py --check`` to see exactly which
     tables changed / were added / removed — review the diff.
  3. Run ``python tools/re/gen_config_manifest.py`` to rewrite the manifest.
  4. Run pytest: ``tests/test_config_regression.py`` re-asserts the structural
     invariants (load-bearing tables, recruit pawn ids, ecodes) against the new data.

``--check`` exits non-zero when the on-disk config no longer matches the manifest,
so it can gate CI if desired. Generating (no flag) always rewrites the manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from nta_agent.version import GAME_VERSION

CONFIG_DIR = Path(__file__).resolve().parents[2] / "nta_agent" / "data" / "config"
MANIFEST = CONFIG_DIR / "manifest.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row_count(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return -1
    return len(data) if isinstance(data, (list, dict)) else -1


def scan() -> dict:
    """Fingerprint every config table (excluding the manifest itself)."""
    files = {}
    for p in sorted(CONFIG_DIR.glob("*.json")):
        if p.name == MANIFEST.name:
            continue
        files[p.name] = {"sha256": _sha256(p), "rows": _row_count(p)}
    return {"game_version": GAME_VERSION, "files": files}


def check(current: dict, saved: dict) -> list[str]:
    """Return human-readable drift lines; empty when in sync."""
    drift: list[str] = []
    if current["game_version"] != saved.get("game_version"):
        drift.append(
            f"game_version: manifest={saved.get('game_version')} disk={current['game_version']}"
        )
    cur_f, old_f = current["files"], saved.get("files", {})
    for name in sorted(set(cur_f) - set(old_f)):
        drift.append(f"added:   {name}")
    for name in sorted(set(old_f) - set(cur_f)):
        drift.append(f"removed: {name}")
    for name in sorted(set(cur_f) & set(old_f)):
        if cur_f[name]["sha256"] != old_f[name]["sha256"]:
            drift.append(
                f"changed: {name} (rows {old_f[name]['rows']} -> {cur_f[name]['rows']})"
            )
    return drift


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report drift vs the saved manifest, don't rewrite (exit 1 on drift)")
    a = ap.parse_args()

    current = scan()
    if a.check:
        if not MANIFEST.exists():
            print("no manifest yet — run without --check to create it")
            return 1
        saved = json.loads(MANIFEST.read_text(encoding="utf-8"))
        drift = check(current, saved)
        if not drift:
            print(f"config in sync with manifest (version {current['game_version']}, "
                  f"{len(current['files'])} tables)")
            return 0
        print("CONFIG DRIFT vs manifest:")
        for line in drift:
            print(f"  {line}")
        return 1

    MANIFEST.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"wrote {MANIFEST} — version {current['game_version']}, "
          f"{len(current['files'])} tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
