"""Game data updates WITHOUT the emulator.

The official download page (what the player opens to get the game) links the current APK;
the CDN holds the hot-update manifests (``hotUpdate/version/<v>/project.manifest``). The
tool reads both, downloads the APK (md5-checked against the CDN's header) and extracts the
XXTEA key, the protobuf schema, the config tables and the battle engine itself — the same
pipeline the emulator-based Setup step uses, fed with a downloaded APK instead of a pulled
one. Nothing here touches the emulator or its copy of the app.

Network access goes through small injectable callables so everything is testable offline.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

DOWNLOAD_PAGE = "https://nine-hk.twomiles.cn/download.html"
CDN_MANIFEST = "https://jwm-global-file.twomiles.cn/hotUpdate/version/{v}/project.manifest"
_UA = "Mozilla/5.0 (NTA-Agent game-update check)"
_APK_RE = re.compile(r"https?://[^'\"\s<>]+/apk/jwm\.v(\d+(?:\.\d+)+)\.apk")


class UpdateError(RuntimeError):
    """The update could not be checked / downloaded / verified / applied."""


def _vkey(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(v or "")))


def newer(a: str, b: str) -> bool:
    """True when version ``a`` is newer than ``b``."""
    return _vkey(a) > _vkey(b)


# ---------------------------------------------------------------- network -- #
def _get_text(url: str, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _get_headers(url: str, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return dict(r.headers.items())


def _open_stream(url: str, timeout: float = 60.0):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    return urllib.request.urlopen(req, timeout=timeout)


def _url_exists(url: str) -> bool:
    try:
        _get_headers(url, timeout=15.0)
        return True
    except Exception:
        return False


# ------------------------------------------------------------- discovery ---- #
def discover(fetch_text: Callable[[str], str] | None = None) -> dict:
    """``{apk_url, apk_version}`` from the download page (the version is in the file name)."""
    try:
        html = (fetch_text or _get_text)(DOWNLOAD_PAGE)
    except Exception as e:
        raise UpdateError(f"không mở được trang tải game: {e}") from e
    m = _APK_RE.search(html or "")
    if not m:
        raise UpdateError("trang tải game không có liên kết APK (đang bảo trì, hoặc trang đổi)")
    return {"apk_url": m.group(0), "apk_version": m.group(1)}


def head(url: str, fetch_headers: Callable[[str], dict] | None = None) -> dict:
    """``{size, md5}`` of the published APK (the CDN's ``x-cos-meta-md5`` header)."""
    try:
        hdr = {k.lower(): v for k, v in (fetch_headers or _get_headers)(url).items()}
    except Exception as e:
        raise UpdateError(f"không đọc được thông tin APK: {e}") from e
    return {"size": int(hdr.get("content-length", 0) or 0),
            "md5": str(hdr.get("x-cos-meta-md5", "")).strip().lower()}


def probe_newer_scripts(current: str, url_exists: Callable[[str], bool] | None = None) -> str | None:
    """A hot-update manifest newer than ``current`` already on the CDN (next patch / next
    minor), i.e. the server may soon want a newer client than the published APK carries."""
    exists = url_exists or _url_exists
    v = list(_vkey(current)) or [0]
    cands = []
    nxt = v[:]
    nxt[-1] += 1
    cands.append(nxt)
    if len(v) >= 2:
        minor = v[:]
        minor[-2] += 1
        minor[-1] = 0
        cands.append(minor)
    for c in cands:
        ver = ".".join(str(x) for x in c)
        if exists(CDN_MANIFEST.format(v=ver)):
            return ver
    return None


# --------------------------------------------------------------- download --- #
def download(url: str, dest: Path, md5: str, open_stream=None,
             progress: Callable[[int], None] | None = None) -> Path:
    """Stream ``url`` to ``dest`` and keep it only if its md5 matches ``md5``."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.md5()
    done = 0
    try:
        with (open_stream or _open_stream)(url) as src, part.open("wb") as out:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done)
        if md5 and h.hexdigest().lower() != md5.lower():
            raise UpdateError(f"md5 không khớp (nhận {h.hexdigest()}, cần {md5}) — bỏ file tải")
        part.replace(dest)
    except UpdateError:
        part.unlink(missing_ok=True)
        raise
    except Exception as e:
        part.unlink(missing_ok=True)
        raise UpdateError(f"tải APK thất bại: {e}") from e
    return dest


def apk_info(apk: Path) -> dict:
    """``{app_version, scripts_version}`` of an APK: the app's versionName and the version of
    the game scripts it bundles (the number the login handshake must declare)."""
    app, scripts = "", ""
    with zipfile.ZipFile(apk) as z:
        try:
            am = z.read("AndroidManifest.xml")
            for m in re.finditer(rb"(?:\d\x00)+(?:\.\x00(?:\d\x00)+)+", am):
                s = m.group(0).decode("utf-16le", "ignore")
                if s.count(".") >= 2:
                    app = s
                    break
        except KeyError:
            pass
        for n in z.namelist():
            if n.startswith("assets/assets/manifest/native/") and n.endswith(".manifest"):
                try:
                    scripts = str(json.loads(z.read(n)).get("version", ""))
                except ValueError:
                    continue
                break
    return {"app_version": app, "scripts_version": scripts}


# ------------------------------------------------------------------ status -- #
def read_meta(meta_path: Path) -> dict:
    try:
        d = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def status(meta_path: Path, published: dict, newer_scripts: str | None, baseline: str) -> dict:
    """What an update would change. ``baseline`` = the scripts version the tool targets now."""
    meta = read_meta(meta_path)
    have_md5 = str(meta.get("apk_md5", "")).lower()
    have_ver = str(meta.get("scripts_version") or baseline)
    if newer(baseline, have_ver):
        have_ver = baseline
    reasons = []
    if have_md5 and published.get("md5") and have_md5 != published["md5"]:
        reasons.append("apk đã đổi trên trang tải (md5 khác bản đang dùng)")
    elif newer(published.get("apk_version", ""), have_ver):
        reasons.append(f"apk {published['apk_version']} mới hơn dữ liệu đang dùng ({have_ver})")
    if newer_scripts and newer(newer_scripts, have_ver):
        reasons.append(f"máy chủ đã có bản script {newer_scripts} (hot-update)")
    return {"update_available": bool(reasons), "reason": "; ".join(reasons),
            "installed_scripts": have_ver, "installed_md5": have_md5,
            "published": published, "newer_scripts": newer_scripts}


# ------------------------------------------------------------------- apply -- #
@dataclass
class Targets:
    """Where the extracted game data lives (``paths`` in the app; injectable in tests)."""
    config_dir: Path
    schema: Path
    engine: Path
    meta: Path
    backups: Path


def default_targets() -> Targets:
    from nta_agent import paths
    return Targets(config_dir=paths.config_dir(), schema=paths.schema_path(),
                   engine=paths.engine_js(), meta=paths.gamedata_dir() / "meta.json",
                   backups=paths.backups_dir())


def _backup(t: Targets, old_version: str) -> Path | None:
    """Copy what is about to be replaced; None when there is nothing to keep."""
    if not (t.config_dir.is_dir() or t.schema.is_file() or t.engine.is_file()):
        return None
    dest = t.backups / f"gamedata-{old_version or 'old'}-{int(time.time())}"
    dest.mkdir(parents=True, exist_ok=True)
    if t.config_dir.is_dir():
        shutil.copytree(t.config_dir, dest / "config", dirs_exist_ok=True)
    for src, name in ((t.schema, "schema.json"), (t.engine, "engine-index.js"),
                      (t.meta, "meta.json")):
        if src.is_file():
            shutil.copy2(src, dest / name)
    return dest


KEY_MISSING = ("không tìm được khoá giải mã: APK không chứa sẵn khoá (game 4.5+) và không đọc "
               "được từ LDPlayer — mở LDPlayer (bật root) có cài game cùng phiên bản rồi thử lại")


def resolve_and_save_key(apk: Path, device=None) -> tuple[str | None, str]:
    """The APK's key (saved -> APK -> the running game over root ADB); a key read from the
    game is remembered so the next update needs no emulator (an APK key is found again)."""
    from nta_agent import gamedata, settings
    if device is None:
        from nta_agent.io.keydump import device_reader
        device = device_reader()
    saved = settings.get("xxtea_key")
    key, src = gamedata.resolve_key(apk, saved=saved, device=device)
    if not key:
        return None, KEY_MISSING
    if src == "device" and key != saved:
        settings.set_values({"xxtea_key": key})
    return key, src or ""


def extract_gamedata(apk: Path, t: Targets, apk_md5: str = "") -> dict:
    """Run the extraction pipeline on ``apk`` into a staging dir; only a COMPLETE result
    replaces the current data (after a backup), and other files in the config dir (e.g. the
    committed ``manifest.json``) are left alone. Records ``meta.json``."""
    from nta_agent import gamedata
    info = apk_info(apk)
    key, err = resolve_and_save_key(apk)
    if not key:
        return {"ok": False, "detail": err}
    stage = t.meta.parent / "staging"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)
    try:
        try:
            msgs = gamedata.build_schema(apk, stage / "schema.json", key.encode())
        except (ValueError, KeyError) as e:
            return {"ok": False, "detail": f"giải mã giao thức thất bại ({e})"}
        n, _fail = gamedata.extract_config_tables(apk, stage / "config")
        if n == 0:
            return {"ok": False, "detail": "không trích được bảng config nào từ APK"}
        engine_ok = False
        try:
            gamedata.decrypt_engine(apk, stage / "engine.js", key.encode())
            engine_ok = True
        except (ValueError, FileNotFoundError):
            pass
        old = read_meta(t.meta)
        backup = _backup(t, str(old.get("game_version") or ""))
        t.config_dir.mkdir(parents=True, exist_ok=True)
        for f in (stage / "config").iterdir():
            shutil.copy2(f, t.config_dir / f.name)
        t.schema.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stage / "schema.json", t.schema)
        if engine_ok:
            t.engine.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(stage / "engine.js", t.engine)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    meta = {"game_version": info["app_version"], "scripts_version": info["scripts_version"],
            "apk_md5": apk_md5, "tables": n, "messages": msgs, "engine": engine_ok,
            "extracted_at": int(time.time())}
    t.meta.parent.mkdir(parents=True, exist_ok=True)
    t.meta.write_text(json.dumps(meta), encoding="utf-8")
    return {"ok": True, "tables": n, "messages": msgs, "engine": engine_ok,
            "app_version": info["app_version"], "scripts_version": info["scripts_version"],
            "backup": str(backup) if backup else "",
            "detail": f"{n} bảng, {msgs} message, mô phỏng trận {'BẬT' if engine_ok else 'TẮT'}"}


def apply_update(t: Targets | None = None, *, work_dir: Path | None = None,
                 discover_fn=None, head_fn=None, download_fn=None, extract_fn=None,
                 progress=None) -> dict:
    """Discover -> download (md5-checked) -> extract -> record. The APK is deleted after use."""
    from nta_agent import paths
    t = t or default_targets()
    work = Path(work_dir or (paths.data_dir() / "gameupdate"))
    work.mkdir(parents=True, exist_ok=True)
    apk = work / "game.apk"
    try:
        pub = (discover_fn or discover)()
        h = (head_fn or head)(pub["apk_url"])
        if not h.get("md5"):
            raise UpdateError("máy chủ không cho biết md5 của APK — không kiểm chứng được file tải")
        (download_fn or download)(pub["apk_url"], apk, h["md5"], progress=progress)
        res = (extract_fn or extract_gamedata)(apk, t, apk_md5=h["md5"])
    except UpdateError as e:
        return {"ok": False, "detail": str(e)}
    finally:
        apk.unlink(missing_ok=True)
        apk.with_suffix(".apk.part").unlink(missing_ok=True)
    return res


# ----------------------------------------------------------------- service -- #
def check_now(t: Targets | None = None, *, discover_fn=None, head_fn=None, probe_fn=None) -> dict:
    """One network check -> :func:`status`. Raises :class:`UpdateError` when the page is
    unreachable or has no APK link."""
    from nta_agent.version import GAME_VERSION
    t = t or default_targets()
    pub = (discover_fn or discover)()
    pub = {**pub, **(head_fn or head)(pub["apk_url"])}
    meta = read_meta(t.meta)
    have = str(meta.get("scripts_version") or GAME_VERSION)
    if newer(GAME_VERSION, have):
        have = GAME_VERSION
    return status(t.meta, pub, (probe_fn or probe_newer_scripts)(have), GAME_VERSION)


class GameUpdateService:
    """What the dashboard talks to: a cached check result (``store`` JSON file) and a
    background apply job. A periodic check keeps the cache fresh without anyone asking."""

    def __init__(self, store: Path, check_fn=None, apply_fn=None):
        import threading
        self.store = Path(store)
        self._check = check_fn or check_now
        self._apply = apply_fn or apply_update
        self._lock = threading.Lock()
        self._thread = None

    def state(self) -> dict:
        try:
            d = json.loads(self.store.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        return d if isinstance(d, dict) else {}

    def _write(self, **fields) -> dict:
        with self._lock:
            d = self.state()
            d.update(fields)
            self.store.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.store.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.store)
            return d

    def check(self) -> dict:
        try:
            st = self._check()
            return self._write(status=st, error="", checked_at=time.time())
        except UpdateError as e:
            return self._write(error=str(e), checked_at=time.time())
        except Exception as e:
            return self._write(error=f"lỗi kiểm tra: {e}", checked_at=time.time())

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def apply(self) -> bool:
        """Start the update in the background; False when one is already running."""
        import threading
        if self.running():
            return False
        self._write(apply={"state": "running", "detail": "đang tải APK…", "ts": time.time()})

        def work():
            try:
                r = self._apply()
            except Exception as e:
                r = {"ok": False, "detail": f"lỗi: {e}"}
            self._write(apply={"state": "done" if r.get("ok") else "error",
                               "detail": str(r.get("detail", "")), "ts": time.time()})
            if r.get("ok"):
                self.check()

        self._thread = threading.Thread(target=work, name="game-update", daemon=True)
        self._thread.start()
        return True

    def join(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def start_periodic(self, every_s: float = 6 * 3600, first_delay_s: float = 20.0) -> None:
        import threading

        def loop():
            time.sleep(first_delay_s)
            while True:
                self.check()
                time.sleep(every_s)
        threading.Thread(target=loop, name="game-update-check", daemon=True).start()
