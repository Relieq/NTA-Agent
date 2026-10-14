"""Bring the game app INSIDE the emulator up to date (before a token OAuth).

Downloading the APK to the PC (``nta_agent.gameupdate``) only refreshes the TOOL's data; the
app in the emulator is a separate copy. When its version is one we do not support (too old),
install the official APK over it with ``adb install -r``: same package, so data and the
Google sign-in are kept, and Android itself refuses a different signing key or a downgrade.
Never uninstalls anything — a refusal is just reported and the app updates itself (hot-update)
when it starts.
"""
from __future__ import annotations

import re
from pathlib import Path

from nta_agent import gameupdate

PACKAGE = "twgame.global.acers"


def supported_versions() -> set[str]:
    """App/script versions the tool works with: the code's, plus the last data update's."""
    from nta_agent import paths
    from nta_agent.version import GAME_APK_VERSIONS, GAME_VERSION
    sup = {GAME_VERSION, *GAME_APK_VERSIONS}
    meta = gameupdate.read_meta(paths.gamedata_dir() / "meta.json")
    for k in ("game_version", "scripts_version"):
        if meta.get(k):
            sup.add(str(meta[k]))
    return sup


def installed_version(dm) -> str | None:
    m = re.search(r"versionName=(\S+)", dm.shell(f"dumpsys package {PACKAGE}"))
    return m.group(1) if m else None


def ensure_app_current(dm, work_dir: Path, *, supported: set[str] | None = None,
                       discover_fn=None, head_fn=None, download_fn=None) -> dict:
    """``{action: none|installed|refused|skipped, detail}``."""
    ver = installed_version(dm)
    sup = supported if supported is not None else supported_versions()
    if ver is None:
        return {"action": "skipped", "detail": "chưa cài game trong giả lập"}
    if ver in sup or not any(gameupdate.newer(s, ver) for s in sup):
        return {"action": "none", "detail": f"app {ver} dùng được"}   # supported, or newer than all
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    apk = work / "app_update.apk"
    try:
        pub = (discover_fn or gameupdate.discover)()
        h = (head_fn or gameupdate.head)(pub["apk_url"])
        if not h.get("md5"):
            return {"action": "skipped", "detail": "không kiểm chứng được md5 của APK"}
        (download_fn or gameupdate.download)(pub["apk_url"], apk, h["md5"])
        out = dm.install(str(apk))
    except gameupdate.UpdateError as e:
        return {"action": "skipped", "detail": str(e)}
    except Exception as e:
        return {"action": "refused", "detail": str(e)[:200]}
    finally:
        apk.unlink(missing_ok=True)
    if "success" in str(out).lower():
        return {"action": "installed", "detail": f"đã cài đè APK {pub['apk_version']} (app {ver} → mới)"}
    return {"action": "refused", "detail": str(out).strip()[:200]}
