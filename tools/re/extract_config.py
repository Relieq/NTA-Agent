"""Extract the game's config tables (common/json/*) from a Cocos Creator APK.

Thin CLI over ``nta_agent.gamedata.extract_config_tables`` (the packaged app's
Setup uses the same function).

    python tools/re/extract_config.py <base.apk> -o nta_agent/data/config

Output is game data — keep it gitignored.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nta_agent.gamedata import RES_BASE, extract_config_tables


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("apk")
    ap.add_argument("-o", "--out", default="tools/re/decrypted/config")
    ap.add_argument("--res-base", default=RES_BASE)
    a = ap.parse_args()
    # Not atomic: the dev config dir also holds the committed manifest.json.
    ok, fail = extract_config_tables(Path(a.apk), Path(a.out), a.res_base, atomic=False)
    print(f"[+] extracted {ok} tables -> {a.out}")
    if fail:
        print("    failed:", fail[:10])


if __name__ == "__main__":
    main()
