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
    rel = {"tag_name": "v0.2.0", "body": "notes",
           "assets": [{"name": "manifest.json",
                       "browser_download_url": "https://github.com/x/y/releases/download/v0.2.0/manifest.json"}]}
    r = updater.check(fetch=lambda url: rel, current="0.1.0")
    assert r["version"] == "0.2.0" and r["manifest_url"].endswith("manifest.json")
    assert updater.check(fetch=lambda url: rel, current="0.2.0") is None
    rel["assets"][0]["browser_download_url"] = "https://evil.example/manifest.json"
    assert updater.check(fetch=lambda url: rel, current="0.1.0") is None


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
