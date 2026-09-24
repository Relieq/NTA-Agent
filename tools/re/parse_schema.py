"""Parse the decrypted protobuf.js static module (msg.js) into schema.json.

Thin CLI over ``nta_agent.io.api.schema_parse`` (the packaged app's Setup uses
the same parser).

    python tools/re/parse_schema.py tools/re/decrypted/msg.js nta_agent/io/api/schema.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nta_agent.io.api.schema_parse import parse_schema


def main():
    src = Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")
    out, unknown = parse_schema(src)
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("schema.json")
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print("[+] %d messages -> %s  (%d unknown fields)" % (len(out), dst, unknown))


if __name__ == "__main__":
    main()
