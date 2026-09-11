"""Extract the game's config tables (common/json/*) from a Cocos Creator APK.

The data tables the client reads via ``assetsMgr.getJsonData(name, id)`` live under
``resources/common/json/<name>`` as Cocos JsonAssets. This resolves each name to
its import file via the resources ``config.json`` (path index -> compressed uuid),
unwraps the JsonAsset, and writes a clean ``<name>.json`` (a list of rows).

    python tools/re/extract_config.py <base.apk> -o tools/re/decrypted/config

Output is game data — keep it gitignored.
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("apk")
    ap.add_argument("-o", "--out", default="tools/re/decrypted/config")
    ap.add_argument("--res-base", default="assets/assets/resources")
    a = ap.parse_args()

    z = zipfile.ZipFile(a.apk)
    cfg = json.loads(z.read(f"{a.res_base}/config.json"))
    paths, uuids = cfg["paths"], cfg["uuids"]

    # index -> name for everything under common/json/
    tables = {
        int(idx): v[0].split("/")[-1]
        for idx, v in paths.items()
        if isinstance(v, list) and v and str(v[0]).startswith("common/json/")
    }
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    ok, fail = 0, []
    for idx, name in sorted(tables.items(), key=lambda kv: kv[1]):
        uuid = decode_uuid(uuids[idx])
        member = f"{a.res_base}/import/{uuid[:2]}/{uuid}.json"
        try:
            imp = json.loads(z.read(member))
            asset_name, rows = unwrap_jsonasset(imp)
            (out_dir / f"{name}.json").write_text(
                json.dumps(rows, ensure_ascii=False), encoding="utf-8"
            )
            ok += 1
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            fail.append((name, str(e)))
    print(f"[+] extracted {ok}/{len(tables)} tables -> {out_dir}")
    if fail:
        print("    failed:", fail[:10])


if __name__ == "__main__":
    main()
