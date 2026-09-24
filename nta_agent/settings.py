"""User settings (``settings.json`` in the data dir, see ``nta_agent.paths``).

Precedence: real env / .env  >  settings.json  >  default. Secrets are stored with
Windows DPAPI (current-user scope) so a copied file is useless on another machine or
account; they are never logged or returned unmasked (packaging spec §4).
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

from nta_agent import paths

KEYS = {  # setting -> env var that overrides it
    "openai_api_key": "OPENAI_API_KEY",
    "openai_model": "OPENAI_MODEL",
    "brain_max_calls": "NTA_BRAIN_MAX_CALLS",
    "distinct_id": "NTA_DISTINCT_ID",
    "adb_path": "NTA_ADB_PATH",
    "adb_serial": "NTA_ADB_SERIAL",
    "xxtea_key": "NTA_XXTEA_KEY",
    "dashboard_port": "NTA_DASHBOARD_PORT",
}
SECRETS = {"openai_api_key", "xxtea_key"}


def _path() -> Path:
    return paths.settings_path()


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    inp = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    crypt32 = ctypes.windll.crypt32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("DPAPI call failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _enc(v: str) -> dict:
    if sys.platform == "win32":
        return {"dpapi": base64.b64encode(_dpapi(v.encode("utf-8"), True)).decode("ascii")}
    return {"plain": v}  # non-Windows = tests/CI only


def _dec(v):
    if isinstance(v, dict):
        if "dpapi" in v:
            try:
                return _dpapi(base64.b64decode(v["dpapi"]), False).decode("utf-8")
            except (OSError, ValueError):
                return None  # copied from another machine / account
        return v.get("plain")
    return v


def _load() -> dict:
    try:
        d = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def get(key: str, default=None):
    env = os.environ.get(KEYS.get(key, ""), "")
    if env:
        return env
    v = _dec(_load().get(key))
    return v if v not in (None, "") else default


def set_values(values: dict) -> None:
    """Merge ``values`` into the file; a blank value removes the key."""
    unknown = [k for k in values if k not in KEYS]
    if unknown:
        raise KeyError(unknown[0])
    d = _load()
    for k, v in values.items():
        v = "" if v is None else str(v).strip()
        if not v:
            d.pop(k, None)
        else:
            d[k] = _enc(v) if k in SECRETS else v
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def mask(v: str) -> str:
    if len(v) >= 24:          # long API keys: prefix + last 4 identify which key it is
        return f"{v[:3]}…{v[-4:]}"
    return "…" + v[-2:] if len(v) > 8 else "…"


def view() -> dict:
    """Every setting as ``{set, value}`` — secrets masked (safe for the dashboard)."""
    out = {}
    for k in KEYS:
        v = get(k)
        shown = (mask(v) if k in SECRETS else v) if v else ""
        out[k] = {"set": bool(v), "value": shown}
    return out
