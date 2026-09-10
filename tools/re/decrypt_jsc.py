"""Decrypt Cocos Creator XXTEA-encrypted assets (.jsc, proto/msg.d, ...) for NTA.

Cocos encrypts JS/asset payloads with XXTEA using a 16-byte key, optionally
zlib/gzip-compressing the plaintext. This standalone decryptor needs no engine.

    python tools/re/decrypt_jsc.py <encrypted_file> [-o out] [-k KEY]

Key defaults to the one recovered via tools/re/hook_xxtea.js (see tools/re/KEY.txt).
"""
from __future__ import annotations
import argparse, struct, zlib
from pathlib import Path

def _load_key() -> bytes:
    """Key comes from env NTA_XXTEA_KEY or the gitignored tools/re/KEY.txt — never hardcoded."""
    import os
    env = os.environ.get("NTA_XXTEA_KEY")
    if env:
        return env.encode()
    kf = Path(__file__).with_name("KEY.txt")
    if kf.exists():
        for line in kf.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("key"):
                return line.split("=", 1)[1].strip().encode()
    raise SystemExit("XXTEA key not found: set NTA_XXTEA_KEY or create tools/re/KEY.txt")
DELTA = 0x9E3779B9
MASK = 0xFFFFFFFF


def _to_uint32_list(data: bytes, include_len: bool):
    n = len(data) >> 2
    out = list(struct.unpack("<%dI" % n, data[: n * 4])) if n else []
    if include_len:
        out.append(len(data))
    return out


def _to_bytes(v, include_len: bool) -> bytes:
    length = len(v)
    raw = b"".join(struct.pack("<I", x & MASK) for x in v)
    if include_len:
        n = v[-1]
        raw = b"".join(struct.pack("<I", v[i] & MASK) for i in range(length - 1))
        return raw[:n]
    return raw


def xxtea_decrypt(data: bytes, key: bytes) -> bytes:
    if not data:
        return b""
    v = _to_uint32_list(data, False)
    k = _to_uint32_list(key.ljust(16, b"\0"), False)
    n = len(v)
    if n < 2:
        return data
    rounds = 6 + 52 // n
    total = (rounds * DELTA) & MASK
    y = v[0]
    while total != 0:
        e = (total >> 2) & 3
        p = n - 1
        while p > 0:
            z = v[p - 1]
            mx = (((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) ^ ((total ^ y) + (k[(p & 3) ^ e] ^ z))
            v[p] = (v[p] - mx) & MASK
            y = v[p]
            p -= 1
        z = v[n - 1]
        mx = (((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) ^ ((total ^ y) + (k[(0 & 3) ^ e] ^ z))
        v[0] = (v[0] - mx) & MASK
        y = v[0]
        total = (total - DELTA) & MASK
    return _to_bytes(v, False)


def maybe_decompress(b: bytes) -> bytes:
    if b[:2] == b"\x1f\x8b":
        try: return zlib.decompress(b, 16 + zlib.MAX_WBITS)
        except Exception: pass
    if b[:1] == b"\x78":
        try: return zlib.decompress(b)
        except Exception: pass
    try: return zlib.decompress(b, -zlib.MAX_WBITS)
    except Exception: return b


def decrypt_file(path: Path, key: bytes) -> bytes:
    raw = path.read_bytes()
    # Cocos may prepend a sign header; try raw first, then skip common sign lengths.
    for skip in (0,):
        dec = xxtea_decrypt(raw[skip:], key)
        out = maybe_decompress(dec)
        return out
    return b""


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
