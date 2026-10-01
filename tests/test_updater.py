import hashlib
import zipfile

import pytest

from nta_agent import updater


def test_semver():
    assert updater.newer("0.2.0", "0.1.9")
    assert not updater.newer("0.1.0", "0.1.0")
    assert updater.newer("1.0.0", "dev")
    assert updater.newer("v0.10.0", "0.9.9")


def test_verify_sha(tmp_path):
    f = tmp_path / "a.zip"
    f.write_bytes(b"abc")
    assert updater.verify(f, hashlib.sha256(b"abc").hexdigest())
    assert not updater.verify(f, "0" * 64)


def _mk(root, ver):
    (root / "app" / "nta_agent").mkdir(parents=True)
    (root / "app" / "nta_agent" / "__init__.py").write_text(ver, encoding="utf-8")
    (root / "VERSION").write_text(ver, encoding="utf-8")
    (root / "keep.txt").write_text("user", encoding="utf-8")


def _zip(path, files):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)


def _read(p):
    return p.read_text(encoding="utf-8")


def test_apply_swaps_app_and_rollback_restores(tmp_path):
    root, backups = tmp_path / "NTA-Agent", tmp_path / "backups"
    _mk(root, "0.1.0")
    z = tmp_path / "new.zip"
    _zip(z, {"app/nta_agent/__init__.py": "0.2.0", "VERSION": "0.2.0"})
    bk = updater.apply(z, root, backups, "app")
    assert _read(root / "app" / "nta_agent" / "__init__.py") == "0.2.0"
    assert _read(root / "VERSION") == "0.2.0"
    assert _read(root / "keep.txt") == "user"
    assert bk.name.startswith("0.1.0-")
    updater.rollback(root, bk)
    assert _read(root / "app" / "nta_agent" / "__init__.py") == "0.1.0"
    assert _read(root / "VERSION") == "0.1.0"
    assert not bk.exists()


def test_apply_rejects_bad_zip_and_changes_nothing(tmp_path):
    root, backups = tmp_path / "r", tmp_path / "b"
    _mk(root, "0.1.0")
    z = tmp_path / "bad.zip"
    _zip(z, {"README.md": "x"})
    with pytest.raises(ValueError):
        updater.apply(z, root, backups, "app")
    _zip(z, {"../evil.txt": "x", "app/a": "", "VERSION": "1"})
    with pytest.raises(ValueError):
        updater.apply(z, root, backups, "app")
    assert _read(root / "VERSION") == "0.1.0"
    assert not (tmp_path / "evil.txt").exists()


def test_plan_full_when_runtime_changes():
    m = {"runtime": {"python": "3.12.10", "node": "20.18.0"}}
    assert updater.plan(m, {"python": "3.12.10", "node": "20.18.0"}) == "app"
    assert updater.plan(m, {"python": "3.12.9", "node": "20.18.0"}) == "full"
    assert updater.plan(m, {}) == "full"


def test_check_reads_latest_release():
    api = "https://api.github.com/repos/x/y/releases/assets/"
    rel = {"tag_name": "v0.2.0", "body": "notes",
           "assets": [{"name": "manifest.json", "url": api + "1"},
                      {"name": "NTA-Agent-0.2.0-app.zip", "url": api + "2"}]}
    r = updater.check(fetch=lambda url: rel, current="0.1.0")
    assert r["version"] == "0.2.0"
    assert r["assets"] == {"manifest.json": api + "1", "NTA-Agent-0.2.0-app.zip": api + "2"}
    assert updater.check(fetch=lambda url: rel, current="0.2.0") is None
    rel["assets"][0]["url"] = "https://evil.example/manifest.json"
    assert updater.check(fetch=lambda url: rel, current="0.1.0") is None


def test_token_is_never_forwarded_on_redirect():
    req = updater._request("https://api.github.com/x", "application/octet-stream", "tok123")
    assert req.unredirected_hdrs.get("Authorization") == "Bearer tok123"
    assert "Authorization" not in req.headers
    assert not updater._request("https://api.github.com/x", "a", None).has_header("Authorization")


def test_prune_keeps_newest(tmp_path):
    import os
    import time
    for i in range(4):
        d = tmp_path / f"v{i}"
        d.mkdir()
        os.utime(d, (time.time() + i, time.time() + i))
    updater.prune(tmp_path, keep=2)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["v2", "v3"]


def test_cached_check_is_off_in_dev():
    assert updater.cached_check()["packaged"] is False


def test_locked_app_folder_aborts_without_losing_files(tmp_path, monkeypatch):
    # live 2026-09-27: the adb daemon had app\ as its working dir -> renaming app\
    # failed; shutil.move then fell back to copy + delete, deleted every file in app\,
    # and the cleanup removed the copy too -> an EMPTY app\. Now nothing is deleted.
    import os
    root, backups = tmp_path / "NTA-Agent", tmp_path / "backups"
    _mk(root, "0.1.0")
    z = tmp_path / "new.zip"
    _zip(z, {"app/nta_agent/__init__.py": "0.2.0", "VERSION": "0.2.0"})
    real = os.replace

    def locked(src, dst):
        if os.path.normcase(os.path.abspath(src)) == os.path.normcase(str(root / "app")):
            raise PermissionError(13, "being used by another process")
        return real(src, dst)
    monkeypatch.setattr(updater.os, "replace", locked)
    monkeypatch.setattr(updater.time, "sleep", lambda s: None)
    with pytest.raises(OSError):
        updater.apply(z, root, backups, "app")
    assert _read(root / "app" / "nta_agent" / "__init__.py") == "0.1.0"   # intact
    assert _read(root / "VERSION") == "0.1.0"


def test_apply_retries_a_briefly_locked_folder(tmp_path, monkeypatch):
    import os
    root, backups = tmp_path / "NTA-Agent", tmp_path / "backups"
    _mk(root, "0.1.0")
    z = tmp_path / "new.zip"
    _zip(z, {"app/nta_agent/__init__.py": "0.2.0", "VERSION": "0.2.0"})
    real, fails = os.replace, {"n": 2}

    def flaky(src, dst):
        if os.path.normcase(os.path.abspath(src)) == os.path.normcase(str(root / "app")) and fails["n"]:
            fails["n"] -= 1
            raise PermissionError(13, "being used by another process")
        return real(src, dst)
    monkeypatch.setattr(updater.os, "replace", flaky)
    monkeypatch.setattr(updater.time, "sleep", lambda s: None)
    updater.apply(z, root, backups, "app")
    assert _read(root / "app" / "nta_agent" / "__init__.py") == "0.2.0"


def test_release_handles_stops_the_adb_daemon(tmp_path, monkeypatch):
    import json
    (tmp_path / "settings.json").write_text(json.dumps({"adb_path": r"C:\LD\adb.exe"}), encoding="utf-8")
    calls = []
    monkeypatch.setattr(updater.subprocess, "run", lambda args, **kw: calls.append((args, kw)))
    updater._release_handles(tmp_path)
    assert calls and calls[0][0][1:] == ["kill-server"]


def test_rate_limit_is_not_reported_as_a_token_problem(monkeypatch, tmp_path):
    import urllib.error

    from nta_agent import paths
    monkeypatch.setenv("NTA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(paths, "is_packaged", lambda: True)

    def limited(url):
        raise urllib.error.HTTPError(url, 403, "rate limit exceeded",
                                     {"X-RateLimit-Remaining": "0"}, None)
    r = updater.cached_check(force=True, fetch=limited)
    assert "giới hạn" in r["error"] and "token" not in r["error"]


def test_release_handles_stops_leftover_programs_of_ours(tmp_path, monkeypatch):
    # a node sidecar / agent that outlived the dashboard keeps files open -> rename fails
    calls = []
    monkeypatch.setattr(updater, "_root_processes", lambda root: [(111, "node.exe"), (222, "python.exe")])
    monkeypatch.setattr(updater.subprocess, "run", lambda args, **kw: calls.append(args))
    monkeypatch.setattr(updater.time, "sleep", lambda s: None)
    updater._release_handles(tmp_path, tmp_path / "NTA-Agent")
    kills = [c for c in calls if c[0] == "taskkill"]
    assert [c[-1] for c in kills] == ["111", "222"]
    assert "node.exe(111)" in (tmp_path / "run" / "updater.log").read_text(encoding="utf-8")


def test_nothing_is_killed_without_an_install_root(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(updater, "_root_processes", lambda root: [(1, "x.exe")])
    monkeypatch.setattr(updater.subprocess, "run", lambda args, **kw: calls.append(args))
    updater._release_handles(tmp_path)                       # old call shape: adb only
    assert calls == []


def test_a_refused_rename_is_reported_with_the_file_the_culprits_and_a_hint(tmp_path, monkeypatch):
    err = PermissionError(13, "The process cannot access the file because it is being used by another process")
    err.filename = r"D:\NTA-Agent\app"
    monkeypatch.setattr(updater, "_root_processes", lambda root: [(333, "node.exe")])
    text = updater._lock_hint(err, tmp_path)
    assert r"D:\NTA-Agent\app" in text and "node.exe(333)" in text and "Explorer" in text
    assert updater._lock_hint(ValueError("x"), tmp_path) == ""      # only for lock errors


def test_root_processes_never_raises(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError("no powershell")
    monkeypatch.setattr(updater.subprocess, "run", boom)
    assert updater._root_processes(tmp_path) == []


def test_run_update_failure_log_carries_the_hint(tmp_path, monkeypatch):
    err = PermissionError(13, "being used by another process")
    monkeypatch.setattr(updater, "_root_processes", lambda root: [(5, "node.exe")])
    monkeypatch.setattr(updater, "_download", lambda url, dst: (_ for _ in ()).throw(err))
    monkeypatch.setattr(updater, "_launch", lambda root: None)
    assert updater.run_update(tmp_path / "root", tmp_path / "data", {"manifest.json": "u"}, 1) == 1
    log = (tmp_path / "data" / "run" / "updater.log").read_text(encoding="utf-8")
    assert "update aborted" in log and "node.exe(5)" in log and "HINT" in log
