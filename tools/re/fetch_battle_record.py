"""Fetch a battle record from the live game (Chiến Báo) for turn-by-turn replay.

Lists the player's stored battles, or fetches one full record (frames + randSeed) and
saves it as JSON for tools/battlesim/replay-log.js to replay blow-by-blow.

Needs its OWN game session, so the agent must be STOPPED first (single session — this
kicks the emulator client too). Then:

    # list recent battles (uid + location + time + deaths)
    .venv/Scripts/python.exe tools/re/fetch_battle_record.py --list

    # fetch the most recent battle (or a specific --uid) -> build/run/battle_record.json
    .venv/Scripts/python.exe tools/re/fetch_battle_record.py --latest
    .venv/Scripts/python.exe tools/re/fetch_battle_record.py --uid <uid>

    # then replay it turn-by-turn:
    node tools/battlesim/replay-log.js build/run/battle_record.json <playerUid>
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys

from nta_agent.execution.actions import Actions
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.runner import build_session

W = 600


def _fmt(rec: dict) -> str:
    idx = int(rec.get("index", 0) or 0)
    end = rec.get("endTime", 0) or 0
    when = (datetime.datetime.fromtimestamp(end / 1000).strftime("%m-%d %H:%M:%S")  # noqa: DTZ006
            if end else "?")
    # a records-list item may carry a summary (deadInfo / kill counts); show if present
    dead = rec.get("deadInfo")
    dead_n = len(dead) if isinstance(dead, list) else rec.get("deadCount", "?")
    return f"{rec.get('uid')}  cell=({idx % W},{idx // W})  end={when}  tu_tran={dead_n}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="list recent battle records")
    ap.add_argument("--uid", help="fetch this battle record uid")
    ap.add_argument("--latest", action="store_true", help="fetch the most recent battle")
    ap.add_argument("--out", default="build/run/battle_record.json", help="output json path")
    a = ap.parse_args()

    from nta_agent.env import load_dotenv
    load_dotenv()   # NTA_DISTINCT_ID etc. live in the gitignored .env (as the agent does)
    cfg = RuntimeConfig.from_env()
    session = build_session(cfg)
    actions = Actions(session)

    records = actions.get_battle_records_list()
    records = sorted(records, key=lambda r: r.get("endTime", 0) or 0, reverse=True)
    if not records:
        print("(no battle records)")
        return 1

    if a.list or not (a.uid or a.latest):
        for r in records[:15]:
            print(_fmt(r))
        if not (a.uid or a.latest):
            print("\nRe-run with --latest or --uid <uid> to fetch one for replay.")
        return 0

    uid = a.uid or str(records[0].get("uid"))
    record = actions.get_battle_record(uid)
    if not record or not record.get("frames"):
        print(f"record {uid} has no frames (server returned nothing usable)")
        return 1
    from pathlib import Path
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"record": record}, ensure_ascii=False), encoding="utf-8")
    print(f"saved record {uid} ({len(record.get('frames', []))} frames) -> {out}")
    print(f"replay: node tools/battlesim/replay-log.js {out} {session.state.user.uid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
