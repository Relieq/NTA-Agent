"""Self-update from GitHub Releases (packaged app only).

Flow (spec §5): the dashboard checks ``releases/latest``; on "Cập nhật" it stops the
agent, copies the bundled Python + this file to %TEMP% (so nothing it runs from is
being replaced), spawns ``updater --apply`` detached and exits. The updater waits for
the dashboard to die, downloads the zip named in ``manifest.json``, verifies sha256,
moves the current ``app\\`` (+ ``runtime\\`` for a full update) into
``backups\\<old version>``, unpacks the new one, relaunches and health-checks it —
rolling back automatically if the new version doesn't come up. Two backups are kept.

``main()`` and the helpers it uses are STDLIB-ONLY: this file runs from a temp copy,
outside the app folder. Dashboard-side helpers import ``nta_agent`` lazily.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

REPO = os.environ.get("NTA_UPDATE_REPO", "Relieq/NTA-Agent")
_API = "https://api.github.com/repos/{repo}/releases/latest"
_HOSTS = ("github.com", "githubusercontent.com")
# Top-level entries each update kind replaces (everything else — e.g. user files — stays).
_ITEMS = {"app": ["app", "VERSION"],
          "full": ["app", "runtime", "VERSION", "NTA-Agent.exe", "NTA-Agent.bat"]}
_DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


# ------------------------------------------------------------ versions ---- #
def parse_version(s: str) -> tuple:
    s = (s or "").strip().lstrip("vV")
    try:
        return tuple(int(x) for x in s.split("."))
    except ValueError:
        return ()


def newer(a: str, b: str) -> bool:
    """True when version ``a`` is strictly newer than ``b`` ("dev" is oldest)."""
    return parse_version(a) > parse_version(b)


def _safe_url(url: str) -> bool:
    u = urllib.parse.urlparse(url)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or host.endswith("." + h) for h in _HOSTS)


def _request(url: str, accept: str, token: str | None) -> urllib.request.Request:
    req = urllib.request.Request(url, headers={"User-Agent": "NTA-Agent-updater",
                                               "Accept": accept})
    if token:
        # Unredirected: a private asset download 302s to a signed storage URL that
        # rejects (and must never receive) the GitHub token.
        req.add_unredirected_header("Authorization", "Bearer " + token)
    return req


def _token() -> str | None:
    return os.environ.get("NTA_UPDATE_TOKEN") or None


def _fetch_json(url: str, token: str | None = None) -> dict:
    with urllib.request.urlopen(_request(url, "application/vnd.github+json",
                                         token or _token()),
                                timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def check(fetch=None, current: str = "dev", repo: str = REPO) -> dict | None:
    """Latest release if newer than ``current``:
    {version, notes, page, assets: {name: api asset url}} (works for private repos)."""
    rel = (fetch or _fetch_json)(_API.format(repo=repo))
    ver = str(rel.get("tag_name", "")).lstrip("vV")
    if not ver or not newer(ver, current):
        return None
    assets = {a.get("name"): a.get("url") for a in rel.get("assets", [])
              if a.get("name") and _safe_url(str(a.get("url") or ""))}
    if "manifest.json" not in assets:
        return None
    return {"version": ver, "notes": str(rel.get("body") or "")[:4000],
            "page": rel.get("html_url", ""), "assets": assets}


def plan(manifest: dict, current_runtime: dict) -> str:
    """"app" when the bundled runtimes are unchanged, else "full"."""
    want = manifest.get("runtime") or {}
    return "app" if want and want == current_runtime else "full"


def verify(path: Path, sha256: str) -> bool:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest() == (sha256 or "").lower()


# ---------------------------------------------------------- swap/rollback -- #
def _read_version(root: Path) -> str:
    try:
        return (root / "VERSION").read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        return "unknown"


def _move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def apply(zip_path: Path, root: Path, backups: Path, kind: str) -> Path:
    """Replace ``_ITEMS[kind]`` under ``root`` with the zip's; returns the backup dir.

    The zip is fully extracted first; if the swap fails midway everything moved so
    far is put back before re-raising, so the install is never left half-updated.
    """
    root, backups = Path(root), Path(backups)
    stage = root / ".update_stage"
    if stage.exists():
        shutil.rmtree(stage)
    with zipfile.ZipFile(zip_path) as z:
        for m in z.namelist():  # zip-slip guard
            if Path(m).is_absolute() or ".." in Path(m).parts:
                raise ValueError(f"unsafe path in update zip: {m}")
        z.extractall(stage)
    if not (stage / "VERSION").is_file() and (stage / "NTA-Agent" / "VERSION").is_file():
        inner = stage / "NTA-Agent"            # the "full" zip wraps a top folder
        for item in list(inner.iterdir()):
            shutil.move(str(item), str(stage / item.name))
        inner.rmdir()
    if not (stage / "app").is_dir() or not (stage / "VERSION").is_file():
        shutil.rmtree(stage)
        raise ValueError("update zip lacks app/ or VERSION")
    backup = backups / f"{_read_version(root)}-{int(time.time())}"
    backup.mkdir(parents=True)
    moved_out, moved_in = [], []
    try:
        for name in _ITEMS[kind]:
            if (stage / name).exists():
                if (root / name).exists():
                    _move(root / name, backup / name)
                    moved_out.append(name)
                _move(stage / name, root / name)
                moved_in.append(name)
    except OSError:
        for name in moved_in:
            if (root / name).is_dir():
                shutil.rmtree(root / name, ignore_errors=True)
            else:
                (root / name).unlink(missing_ok=True)
        for name in moved_out:
            _move(backup / name, root / name)
        shutil.rmtree(backup, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return backup


def rollback(root: Path, backup: Path) -> None:
    """Put every item saved in ``backup`` back under ``root`` (current copy discarded)."""
    root, backup = Path(root), Path(backup)
    for item in list(backup.iterdir()):
        cur = root / item.name
        if cur.is_dir():
            shutil.rmtree(cur)
        elif cur.exists():
            cur.unlink()
        _move(item, cur)
    shutil.rmtree(backup, ignore_errors=True)


def prune(backups: Path, keep: int = 2) -> None:
    dirs = sorted((d for d in Path(backups).glob("*") if d.is_dir()),
                  key=lambda d: d.stat().st_mtime, reverse=True)
    for d in dirs[keep:]:
        shutil.rmtree(d, ignore_errors=True)


def latest_backup(backups: Path) -> Path | None:
    dirs = sorted((d for d in Path(backups).glob("*") if d.is_dir()),
                  key=lambda d: d.stat().st_mtime, reverse=True)
    return dirs[0] if dirs else None


# ------------------------------------------------------ updater process ---- #
def _log(data: Path, msg: str) -> None:
    p = data / "run" / "updater.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def _wait_pid_exit(pid: int, timeout: float = 30.0) -> None:
    if not pid:
        return
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if h:
        k.WaitForSingleObject(h, int(timeout * 1000))
        k.CloseHandle(h)


def _download(url: str, dst: Path) -> None:
    """Download a release asset via its API url (``Accept: octet-stream``)."""
    if not _safe_url(url):
        raise ValueError(f"refusing non-GitHub URL: {url}")
    req = _request(url, "application/octet-stream", _token())
    with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)


def _launch(root: Path) -> None:
    py = root / "runtime" / "python" / "pythonw.exe"
    subprocess.Popen([str(py), "-m", "nta_agent.app"], cwd=str(root / "app"),
                     creationflags=_DETACHED, close_fds=True)


def _healthy(port: int, version: str, timeout: float = 45.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/app", timeout=3) as r:
                if json.loads(r.read().decode("utf-8")).get("version") == version:
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(1.5)
    return False


def _runtime_versions(root: Path) -> dict:
    try:
        return json.loads((root / "runtime" / "versions.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run_update(root: Path, data: Path, assets: dict, port: int) -> int:
    """``assets`` = {asset name: API url} of the release (from :func:`check`)."""
    root, data = Path(root).resolve(), Path(data).resolve()
    backups = data / "backups"
    try:
        tmp = Path(tempfile.mkdtemp(prefix="nta-upd-"))
        man_p = tmp / "manifest.json"
        _download(assets["manifest.json"], man_p)
        manifest = json.loads(man_p.read_text(encoding="utf-8"))
        kind = plan(manifest, _runtime_versions(root))
        asset = manifest["assets"][kind]
        url = assets[asset["name"]]
        zp = tmp / asset["name"]
        _log(data, f"downloading {kind} {manifest.get('version')} from {url}")
        _download(url, zp)
        if not verify(zp, asset["sha256"]):
            raise ValueError("sha256 mismatch — download corrupted or tampered")
        backup = apply(zp, root, backups, kind)
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception as e:  # nothing replaced: just bring the old version back up
        _log(data, f"update aborted: {e!r}")
        _launch(root)
        return 1
    _launch(root)
    if _healthy(port, str(manifest.get("version"))):
        prune(backups, keep=2)
        _log(data, f"updated to {manifest.get('version')} ({kind})")
        return 0
    _log(data, "new version failed health check — rolling back")
    _kill_dashboard(data)
    rollback(root, backup)
    _launch(root)
    return 2


def run_rollback(root: Path, data: Path) -> int:
    root, data = Path(root).resolve(), Path(data).resolve()
    b = latest_backup(data / "backups")
    if b is None:
        _log(data, "rollback: no backup")
        _launch(root)
        return 1
    rollback(root, b)
    _log(data, f"rolled back to {b.name}")
    _launch(root)
    return 0


def _kill_dashboard(data: Path) -> None:
    try:
        pid = int((data / "run" / "dashboard.pid").read_text(encoding="utf-8").split()[0])
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
    except (OSError, ValueError, IndexError):
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="nta-updater")
    ap.add_argument("--root", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--wait-pid", type=int, default=0)
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--assets", help="JSON file {asset name: API url}")
    ap.add_argument("--rollback", action="store_true")
    a = ap.parse_args(argv)
    _wait_pid_exit(a.wait_pid)
    time.sleep(1.0)  # let Windows release file handles of the exited dashboard
    root, data = Path(a.root), Path(a.data)
    if a.rollback:
        return run_rollback(root, data)
    assets = json.loads(Path(a.assets).read_text(encoding="utf-8"))
    return run_update(root, data, assets, a.port)


# ------------------------------------------------ dashboard-side helpers ---- #
def spawn(port: int, assets: dict | None = None, rollback_: bool = False) -> None:
    """Copy the bundled Python + this file to %TEMP% and run the updater from there.
    The GitHub token (private repo) travels in the child's environment only."""
    from nta_agent import paths, settings
    root = paths.root_dir()
    tmp = Path(tempfile.gettempdir()) / "nta-updater"
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(root / "runtime" / "python", tmp / "python")
    shutil.copy2(__file__, tmp / "nta_updater.py")
    args = [str(tmp / "python" / "pythonw.exe"), str(tmp / "nta_updater.py"),
            "--root", str(root), "--data", str(paths.data_dir()),
            "--wait-pid", str(os.getpid()), "--port", str(port)]
    if rollback_:
        args += ["--rollback"]
    else:
        (tmp / "assets.json").write_text(json.dumps(assets or {}), encoding="utf-8")
        args += ["--assets", str(tmp / "assets.json")]
    env = dict(os.environ)
    tok = settings.get("update_token")
    if tok:
        env["NTA_UPDATE_TOKEN"] = tok
    subprocess.Popen(args, cwd=str(tmp), env=env, creationflags=_DETACHED, close_fds=True)


def cached_check(max_age_s: float = 6 * 3600, force: bool = False, fetch=None) -> dict:
    """Dashboard view: {current, packaged, update|None, checked_at, error?} (cached)."""
    from nta_agent import paths
    cur = paths.app_version()
    if not paths.is_packaged():
        return {"current": cur, "packaged": False, "update": None}
    cache = paths.run_dir() / "update_check.json"
    try:
        c = json.loads(cache.read_text(encoding="utf-8"))
        if not force and time.time() - c.get("checked_at", 0) < max_age_s \
                and c.get("current") == cur:
            return c
    except (OSError, ValueError):
        pass
    from nta_agent import settings
    out = {"current": cur, "packaged": True, "update": None, "checked_at": time.time(),
           "has_backup": latest_backup(paths.backups_dir()) is not None}
    tok = settings.get("update_token")
    try:
        out["update"] = check(fetch=fetch or (lambda url: _fetch_json(url, tok)), current=cur)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403) or (e.code == 404 and not tok):
            # the repo is private: 404 without a token, 401/403 with a bad one
            out["error"] = "cần GitHub token hợp lệ (Cài đặt) để kiểm tra cập nhật"
        elif e.code != 404:  # 404 with a token = no release yet: nothing to update to
            out["error"] = f"không kiểm tra được: HTTP {e.code}"
    except (OSError, ValueError) as e:
        out["error"] = f"không kiểm tra được: {e}"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    sys.exit(main())
