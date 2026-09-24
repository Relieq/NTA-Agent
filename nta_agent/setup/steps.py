"""Self-checking first-run steps: each one verifies (and where it can, performs)
one prerequisite and reports ``{ok, detail, hint, doc}`` for the Setup page.

Results persist in ``run_dir()/setup_status.json``; Start is gated on all steps
passing (packaged app only — a dev checkout is never gated).
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from nta_agent import gamedata, paths, settings
from nta_agent.version import GAME_VERSION

PACKAGE = "twgame.global.acers"
_PREFS = f"/data/data/{PACKAGE}/shared_prefs/com.thinkingdata.analyse.xml"


def read_account_token(dm) -> str:  # indirection so tests can stub it
    from nta_agent.io.bootstrap import read_account_token as _read
    return _read(dm)


def _connect():
    from nta_agent.io.adb import DeviceManager
    return DeviceManager.connect()


def _status_path() -> Path:
    return paths.run_dir() / "setup_status.json"


# ------------------------------------------------------------------ steps -- #
def _adb(get_dm) -> dict:
    from nta_agent import config
    exe = config._find_adb()
    if not (Path(exe).is_file() or shutil.which(exe)):
        return {"ok": False, "detail": f"không thấy adb ({exe})"}
    if not settings.get("adb_path"):
        settings.set_values({"adb_path": exe})
    return {"ok": True, "detail": exe}


def _device(get_dm) -> dict:
    serial = get_dm().serial
    settings.set_values({"adb_serial": serial})
    return {"ok": True, "detail": serial}


def _root(get_dm) -> dict:
    out = get_dm().su("id")
    return {"ok": "uid=0" in out, "detail": out.strip()[:80] or "không có quyền root"}


def _installed_version(dm) -> str | None:
    m = re.search(r"versionName=(\S+)", dm.shell(f"dumpsys package {PACKAGE}"))
    return m.group(1) if m else None


def _game(get_dm) -> dict:
    ver = _installed_version(get_dm())
    if ver is None:
        return {"ok": False, "detail": "chưa cài game trong giả lập"}
    ok = ver == GAME_VERSION
    return {"ok": ok, "detail": f"game {ver} (app hỗ trợ {GAME_VERSION})"}


def _meta_path() -> Path:
    return paths.gamedata_dir() / "meta.json"


def _gamedata(get_dm) -> dict:
    cfg_ok = (paths.config_dir() / "buildBase.json").is_file()
    if not paths.is_packaged():  # dev: managed by tools/re, never overwritten here
        return {"ok": cfg_ok, "detail": f"dev: {paths.config_dir()}"}
    dm = get_dm()
    ver = _installed_version(dm)
    key = settings.get("xxtea_key")
    try:
        meta = json.loads(_meta_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    engine_ok = paths.engine_js().is_file()
    if cfg_ok and meta.get("game_version") == ver and (engine_ok or not key):
        return {"ok": True, "detail": _gamedata_detail(ver, engine_ok)}
    remote = dm.shell(f"pm path {PACKAGE}").strip().splitlines()[0].replace("package:", "")
    apk = paths.data_dir() / "tmp_base.apk"
    apk.parent.mkdir(parents=True, exist_ok=True)
    try:
        dm.pull(remote.strip(), str(apk), timeout=300)
        n, _fail = gamedata.extract_config_tables(apk, paths.config_dir())
        if n == 0:
            return {"ok": False, "detail": "không trích được bảng config nào từ APK"}
        engine_ok, engine_err = False, ""
        if key:
            try:
                gamedata.decrypt_engine(apk, paths.engine_js(), key.encode())
                engine_ok = True
            except (ValueError, FileNotFoundError) as e:
                engine_err = f" — engine lỗi: {e}"
    finally:
        apk.unlink(missing_ok=True)
    _meta_path().write_text(json.dumps({"game_version": ver, "tables": n, "engine": engine_ok,
                                        "extracted_at": int(time.time())}), encoding="utf-8")
    return {"ok": True, "detail": _gamedata_detail(ver, engine_ok) + f", {n} bảng" + engine_err}


def _gamedata_detail(ver, engine_ok: bool) -> str:
    sim = "mô phỏng trận BẬT" if engine_ok else "mô phỏng trận TẮT (chưa có XXTEA key)"
    return f"dữ liệu game {ver}; {sim}"


def _distinct(get_dm) -> dict:
    xml = get_dm().su(f"cat {_PREFS}")
    m = re.search(r'name="randomID">([^<]+)<', xml)
    if not m:
        return {"ok": False, "detail": "không đọc được randomID"}
    settings.set_values({"distinct_id": m.group(1).strip()})
    return {"ok": True, "detail": "đã lưu distinct id"}


def _token(get_dm) -> dict:
    tok = read_account_token(get_dm())
    if not tok:
        return {"ok": False, "detail": "chưa có token đăng nhập"}
    p = paths.token_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(tok, encoding="utf-8")
    return {"ok": True, "detail": "đã lưu token"}


_RUNNERS = {"adb": _adb, "device": _device, "root": _root, "game": _game,
            "gamedata": _gamedata, "distinct_id": _distinct, "token": _token}
STEPS = list(_RUNNERS)

TITLES = {
    "adb": "Tìm ADB", "device": "Kết nối giả lập", "root": "Quyền root",
    "game": "Phiên bản game", "gamedata": "Dữ liệu game", "distinct_id": "Mã thiết bị",
    "token": "Token đăng nhập",
}
_HINTS = {
    "adb": ("Cài LDPlayer 9 (có sẵn adb.exe) hoặc nhập đường dẫn adb trong Cài đặt.",
            "buoc-1-adb"),
    "device": ("Mở LDPlayer và bật ADB: Cài đặt LDPlayer → Khác → Gỡ lỗi ADB = Mở kết nối cục bộ.",
               "buoc-2-gia-lap"),
    "root": ("Bật Root: Cài đặt LDPlayer → Khác → Quyền ROOT = Bật, rồi khởi động lại giả lập.",
             "buoc-3-root"),
    "game": (("Cài đúng bản game mà app hỗ trợ; bản khác có thể lệch giao thức. "
              "Có thể bỏ qua nếu chấp nhận rủi ro."), "buoc-4-game"),
    "gamedata": ("Cần bước 2–4 đạt trước. Mô phỏng trận cần XXTEA key (Cài đặt).",
                 "buoc-5-du-lieu-game"),
    "distinct_id": ("Mở game ít nhất một lần cho tới màn hình chính.", "buoc-6-distinct-id"),
    "token": ("Đăng nhập game (Google/Facebook) trong giả lập rồi THOÁT game, chạy lại bước này.",
              "buoc-7-token"),
}
OVERRIDABLE = {"game"}


# ------------------------------------------------------------------- API -- #
def _load() -> dict:
    try:
        d = json.loads(_status_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _save(d: dict) -> None:
    p = _status_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _decorate(name: str, r: dict) -> dict:
    hint, anchor = _HINTS[name]
    return {"name": name, "title": TITLES[name], "ok": bool(r.get("ok")),
            "detail": r.get("detail", ""), "hint": "" if r.get("ok") else hint,
            "doc": f"README.md#{anchor}", "ran": bool(r.get("ran", True)),
            "overridable": name in OVERRIDABLE and not r.get("ok"),
            "overridden": bool(r.get("overridden"))}


def run_step(name: str, dm_factory=None) -> dict:
    if name not in _RUNNERS:
        raise KeyError(name)
    factory = dm_factory or _connect
    cache: list = []

    def get_dm():
        if not cache:
            cache.append(factory())
        return cache[0]

    try:
        r = dict(_RUNNERS[name](get_dm))
    except Exception as e:  # any failure is a step result, not a crash
        r = {"ok": False, "detail": f"{type(e).__name__}: {e}"[:200]}
    d = _load()
    d[name] = {"ok": bool(r.get("ok")), "detail": r.get("detail", ""), "at": int(time.time())}
    _save(d)
    return _decorate(name, d[name])


def override(name: str) -> dict:
    """User accepted the risk (e.g. a newer game version): mark the step passed."""
    if name not in OVERRIDABLE:
        raise KeyError(name)
    d = _load()
    prev = d.get(name, {})
    d[name] = {"ok": True, "overridden": True, "at": int(time.time()),
               "detail": (prev.get("detail", "") + " — người dùng chấp nhận rủi ro").strip(" —")}
    _save(d)
    return _decorate(name, d[name])


def status() -> dict:
    d = _load()
    steps = [_decorate(n, d[n]) if n in d else
             _decorate(n, {"ok": False, "detail": "chưa chạy", "ran": False}) for n in STEPS]
    return {"steps": steps, "ready": all(s["ok"] for s in steps),
            "packaged": paths.is_packaged(), "game_version": GAME_VERSION}


def ready() -> bool:
    return True if not paths.is_packaged() else status()["ready"]
