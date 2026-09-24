"""Game data pulled from the user's own APK: config tables + decrypted battle engine.

Nothing here ships with the app (it is the game's copyrighted data). The first-run
Setup extracts it from the APK installed in the emulator into ``paths.gamedata_dir()``;
dev tools ``tools/re/extract_config.py`` / ``tools/re/decrypt_jsc.py`` are thin CLIs
over these functions.

Cocos encrypts JS with XXTEA (16-byte key), optionally zlib/gzip-compressing the
plaintext. Config tables live under ``resources/common/json/<name>`` as JsonAssets.
"""
from __future__ import annotations

import json
import shutil
import struct
import zipfile
import zlib
from pathlib import Path

RES_BASE = "assets/assets/resources"
ENGINE_ENTRY = "assets/assets/app/index.jsc"   # verified on v4.4.4 (== tools/re/decrypted/index.js)
MSG_ENTRY = "assets/src/assets/app/proto/msg.jsc"  # protobuf.js static module -> schema.json

# ---------------------------------------------------------------- XXTEA ---- #
DELTA = 0x9E3779B9
MASK = 0xFFFFFFFF


def _to_uint32_list(data: bytes) -> list[int]:
    n = len(data) >> 2
    return list(struct.unpack("<%dI" % n, data[: n * 4])) if n else []


def _to_bytes(v: list[int]) -> bytes:
    return b"".join(struct.pack("<I", x & MASK) for x in v)


def _mx(total, y, z, p, e, k):
    return (((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) ^ ((total ^ y) + (k[(p & 3) ^ e] ^ z))


def xxtea_decrypt(data: bytes, key: bytes) -> bytes:
    if not data:
        return b""
    v = _to_uint32_list(data)
    k = _to_uint32_list(key.ljust(16, b"\0")[:16])
    n = len(v)
    if n < 2:
        return data
    total = ((6 + 52 // n) * DELTA) & MASK
    y = v[0]
    while total != 0:
        e = (total >> 2) & 3
        for p in range(n - 1, 0, -1):
            z = v[p - 1]
            v[p] = (v[p] - _mx(total, y, z, p, e, k)) & MASK
            y = v[p]
        z = v[n - 1]
        v[0] = (v[0] - _mx(total, y, z, 0, e, k)) & MASK
        y = v[0]
        total = (total - DELTA) & MASK
    return _to_bytes(v)


def xxtea_encrypt(data: bytes, key: bytes) -> bytes:
    """Inverse of :func:`xxtea_decrypt` (tests only). Pads to a 4-byte multiple."""
    data = data + b"\0" * (-len(data) % 4)
    v = _to_uint32_list(data)
    k = _to_uint32_list(key.ljust(16, b"\0")[:16])
    n = len(v)
    if n < 2:
        return data
    total, z = 0, v[n - 1]
    for _ in range(6 + 52 // n):
        total = (total + DELTA) & MASK
        e = (total >> 2) & 3
        for p in range(n):
            y = v[(p + 1) % n]
            v[p] = (v[p] + _mx(total, y, z, p, e, k)) & MASK
            z = v[p]
    return _to_bytes(v)


def maybe_decompress(b: bytes) -> bytes:
    if b[:2] == b"\x1f\x8b":
        try:
            return zlib.decompress(b, 16 + zlib.MAX_WBITS)
        except zlib.error:
            pass
    if b[:1] == b"\x78":
        try:
            return zlib.decompress(b)
        except zlib.error:
            pass
    try:
        return zlib.decompress(b, -zlib.MAX_WBITS)
    except zlib.error:
        return b


def decrypt_bytes(raw: bytes, key: bytes) -> bytes:
    return maybe_decompress(xxtea_decrypt(raw, key))


def find_engine_entry(names: list[str]) -> str | None:
    if ENGINE_ENTRY in names:
        return ENGINE_ENTRY
    cands = [n for n in names if n.endswith("/app/index.jsc")]
    return cands[0] if cands else None


def decrypt_engine(apk: Path, out_js: Path, key: bytes) -> int:
    """Decrypt the battle engine bundle from ``apk`` to ``out_js``; returns its size."""
    with zipfile.ZipFile(apk) as z:
        entry = find_engine_entry(z.namelist())
        if entry is None:
            raise FileNotFoundError("engine bundle (app/index.jsc) not found in APK")
        js = decrypt_bytes(z.read(entry), key)
    if not js.lstrip().startswith(b"window.__require"):
        raise ValueError("engine decrypt produced garbage — wrong XXTEA key?")
    out_js.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_js.with_suffix(".tmp")
    tmp.write_bytes(js)
    tmp.replace(out_js)
    return len(js)


def build_schema(apk: Path, out_json: Path, key: bytes) -> int:
    """Decrypt msg.jsc and write the protobuf schema the API client needs; returns
    the message count."""
    from nta_agent.io.api.schema_parse import parse_schema
    with zipfile.ZipFile(apk) as z:
        src = decrypt_bytes(z.read(MSG_ENTRY), key).decode("utf-8", "ignore")
    schema, _unknown = parse_schema(src)
    if len(schema) < 50:
        raise ValueError("msg.jsc decrypt produced no schema — wrong XXTEA key?")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_json.with_suffix(".tmp")
    tmp.write_text(json.dumps(schema, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(out_json)
    return len(schema)


# -------------------------------------------------------- config tables ---- #
_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_VAL = {c: i for i, c in enumerate(_B64)}
_HEX = "0123456789abcdef"


def decode_uuid(base64: str) -> str:
    """Cocos Creator compressed-uuid -> dashed uuid (matches import filenames)."""
    base64 = base64.split("@")[0]
    if len(base64) != 22:
        return base64
    out = [base64[0], base64[1]]
    for i in range(2, 22, 2):
        lhs, rhs = _VAL[base64[i]], _VAL[base64[i + 1]]
        out.append(_HEX[lhs >> 2])
        out.append(_HEX[((lhs & 3) << 2) | (rhs >> 4)])
        out.append(_HEX[rhs & 0xF])
    h = "".join(out)
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def unwrap_jsonasset(imp: list) -> tuple[str, list]:
    """Return (name, rows) from a Cocos JsonAsset import structure."""
    entry = imp[5][0]  # [0, "<name>", [rows...]]
    return entry[1], entry[2]


def extract_config_tables(apk: Path, out_dir: Path, res_base: str = RES_BASE,
                          atomic: bool = True) -> tuple[int, list]:
    """Write every ``common/json/<name>`` table as ``out_dir/<name>.json``.

    Returns (tables written, [(name, error)]). With ``atomic`` the tables are built
    in a sibling dir and swapped in, so a failed run never leaves a half-set.
    """
    out_dir = Path(out_dir)
    work = out_dir.with_name(out_dir.name + ".new") if atomic else out_dir
    if atomic and work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    ok, fail = 0, []
    with zipfile.ZipFile(apk) as z:
        cfg = json.loads(z.read(f"{res_base}/config.json"))
        paths_, uuids = cfg["paths"], cfg["uuids"]
        tables = {
            int(idx): v[0].split("/")[-1]
            for idx, v in paths_.items()
            if isinstance(v, list) and v and str(v[0]).startswith("common/json/")
        }
        for idx, name in sorted(tables.items(), key=lambda kv: kv[1]):
            uuid = decode_uuid(uuids[idx])
            member = f"{res_base}/import/{uuid[:2]}/{uuid}.json"
            try:
                _, rows = unwrap_jsonasset(json.loads(z.read(member)))
            except (KeyError, IndexError, ValueError) as e:
                fail.append((name, str(e)))
                continue
            (work / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False),
                                               encoding="utf-8")
            ok += 1
    if atomic:
        if ok == 0:
            shutil.rmtree(work)
            return 0, fail
        old = out_dir.with_name(out_dir.name + ".old")
        if old.exists():
            shutil.rmtree(old)
        if out_dir.exists():
            out_dir.rename(old)
        work.rename(out_dir)
        if old.exists():
            shutil.rmtree(old)
    return ok, fail
