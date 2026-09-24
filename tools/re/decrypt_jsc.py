"""Decrypt Cocos Creator XXTEA-encrypted assets (.jsc, proto/msg.d, ...) for NTA.

Thin CLI over ``nta_agent.gamedata`` (XXTEA + optional zlib/gzip).

    python tools/re/decrypt_jsc.py <encrypted_file> [-o out] [-k KEY]

Key comes from -k, env NTA_XXTEA_KEY or the gitignored tools/re/KEY.txt.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nta_agent.gamedata import decrypt_bytes, maybe_decompress, xxtea_decrypt  # noqa: F401


def _load_key() -> bytes:
    """Key comes from env NTA_XXTEA_KEY or the gitignored tools/re/KEY.txt — never hardcoded."""
    env = os.environ.get("NTA_XXTEA_KEY")
    if env:
        return env.encode()
    kf = Path(__file__).with_name("KEY.txt")
    if kf.exists():
        for line in kf.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("key"):
                return line.split("=", 1)[1].strip().encode()
    raise SystemExit("XXTEA key not found: set NTA_XXTEA_KEY or create tools/re/KEY.txt")


def decrypt_file(path: Path, key: bytes) -> bytes:
    return decrypt_bytes(path.read_bytes(), key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("-o", "--out")
    ap.add_argument("-k", "--key", default=None)
    a = ap.parse_args()
    key = a.key.encode() if a.key else _load_key()
    out = decrypt_file(Path(a.infile), key)
    dst = Path(a.out) if a.out else Path(a.infile).with_suffix(".dec")
    dst.write_bytes(out)
    head = out[:64]
    print(f"[+] {a.infile} -> {dst} ({len(out)} bytes)")
    print("    head hex:", head.hex(" "))
    print("    head asc:", "".join(chr(b) if 32 <= b < 127 else "." for b in head))


if __name__ == "__main__":
    main()
