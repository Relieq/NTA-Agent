"""Game data updates WITHOUT the emulator (player 2026-10-14): the official download page links
the current APK, the CDN holds the hot-update manifests; the tool reads them, downloads the APK
(md5-checked) and extracts the key / schema / config / engine itself."""
import hashlib
import io
import json
import zipfile

import pytest

from nta_agent import gameupdate as gu

PAGE = """<html><script>
 if (isIOS) { window.location.href = 'https://apps.apple.com/ph/app/x/id1' }
 else { window.location.href = 'https://jwm-global-file.twomiles.cn/apk/jwm.v4.4.8.apk' }
</script></html>"""


def test_discover_reads_the_apk_url_and_version_from_the_download_page():
    d = gu.discover(fetch_text=lambda url: PAGE)
    assert d == {"apk_url": "https://jwm-global-file.twomiles.cn/apk/jwm.v4.4.8.apk",
                 "apk_version": "4.4.8"}


def test_discover_refuses_a_page_without_an_apk_link():
    with pytest.raises(gu.UpdateError):
        gu.discover(fetch_text=lambda url: "<html>maintenance</html>")


def test_head_returns_size_and_md5_from_the_cos_headers():
    hdr = {"Content-Length": "121698463", "x-cos-meta-md5": "1E9CA7BADBDA7395AE63B1819810A788"}
    h = gu.head("https://x/y.apk", fetch_headers=lambda url: hdr)
    assert h == {"size": 121698463, "md5": "1e9ca7badbda7395ae63b1819810a788"}


def _apk_bytes(app_version="4.4.7", scripts="4.4.8"):
    buf = io.BytesIO()
    am = b"\x00" * 8 + app_version.encode("utf-16le") + b"\x00" * 8
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("AndroidManifest.xml", am)
        z.writestr("assets/assets/manifest/native/e6/e64b.manifest",
                   json.dumps({"version": scripts, "assets": {}}))
    return buf.getvalue()


def test_download_checks_the_md5_and_keeps_nothing_on_a_mismatch(tmp_path):
    data = _apk_bytes()
    good = hashlib.md5(data).hexdigest()
    dest = tmp_path / "game.apk"
    gu.download("https://x/y.apk", dest, good, open_stream=lambda url: io.BytesIO(data))
    assert dest.read_bytes() == data
    dest2 = tmp_path / "bad.apk"
    with pytest.raises(gu.UpdateError):
        gu.download("https://x/y.apk", dest2, "0" * 32, open_stream=lambda url: io.BytesIO(data))
    assert not dest2.exists() and not list(tmp_path.glob("*.part"))


def test_apk_info_reads_the_app_version_and_the_bundled_scripts_version(tmp_path):
    p = tmp_path / "a.apk"
    p.write_bytes(_apk_bytes("4.4.7", "4.4.8"))
    assert gu.apk_info(p) == {"app_version": "4.4.7", "scripts_version": "4.4.8"}


def test_probe_manifests_finds_a_newer_hot_update_version():
    seen = []

    def exists(url):
        seen.append(url)
        return "/4.4.9/" in url
    assert gu.probe_newer_scripts("4.4.8", url_exists=exists) == "4.4.9"
    assert any("/4.4.9/project.manifest" in u for u in seen)
    assert gu.probe_newer_scripts("4.4.8", url_exists=lambda u: False) is None


def test_status_says_when_the_published_apk_is_not_what_is_installed(tmp_path):
    meta = tmp_path / "meta.json"
    meta.write_text(json.dumps({"apk_md5": "aaa", "scripts_version": "4.4.8"}), encoding="utf-8")
    pub = {"apk_url": "u", "apk_version": "4.4.8", "size": 1, "md5": "bbb"}
    s = gu.status(meta, pub, newer_scripts=None, baseline="4.4.8")
    assert s["update_available"] is True and "apk" in s["reason"]
    pub["md5"] = "aaa"
    assert gu.status(meta, pub, None, "4.4.8")["update_available"] is False
    # no recorded md5 (a dev tree): only a different version counts
    meta.unlink()
    assert gu.status(meta, pub, None, "4.4.8")["update_available"] is False
    assert gu.status(meta, {**pub, "apk_version": "4.4.9"}, None, "4.4.8")["update_available"] is True
    s = gu.status(meta, pub, newer_scripts="4.4.9", baseline="4.4.8")
    assert s["update_available"] is True and "4.4.9" in s["reason"]


# ---- applying: extract with the existing pipeline, back up, swap, record meta --------------
def _targets(tmp_path):
    root = tmp_path / "data"
    return gu.Targets(config_dir=root / "config", schema=root / "schema.json",
                      engine=root / "engine" / "index.js", meta=root / "meta.json",
                      backups=root / "backups")


@pytest.fixture
def fake_pipeline(monkeypatch):
    from nta_agent import gamedata
    calls = []
    monkeypatch.setattr(gamedata, "find_xxtea_key", lambda apk: "k" * 16)

    def build_schema(apk, out, key):
        calls.append("schema")
        out.write_text('{"msgs": 1}', encoding="utf-8")
        return 321

    def extract_tables(apk, out_dir, *a, **k):
        calls.append("tables")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "buildBase.json").write_text('{"v": "new"}', encoding="utf-8")
        return 150, []

    def decrypt_engine(apk, out_js, key):
        calls.append("engine")
        out_js.parent.mkdir(parents=True, exist_ok=True)
        out_js.write_text("window.__require=1", encoding="utf-8")
        return 18
    monkeypatch.setattr(gamedata, "build_schema", build_schema)
    monkeypatch.setattr(gamedata, "extract_config_tables", extract_tables)
    monkeypatch.setattr(gamedata, "decrypt_engine", decrypt_engine)
    return calls


def test_extract_swaps_in_the_new_data_keeps_other_files_and_backs_up_the_old(tmp_path, fake_pipeline):
    t = _targets(tmp_path)
    t.config_dir.mkdir(parents=True)
    (t.config_dir / "buildBase.json").write_text('{"v": "old"}', encoding="utf-8")
    (t.config_dir / "manifest.json").write_text('{"keep": true}', encoding="utf-8")   # committed file
    t.schema.write_text('{"msgs": 0}', encoding="utf-8")
    apk = tmp_path / "a.apk"
    apk.write_bytes(_apk_bytes("4.4.7", "4.4.8"))
    r = gu.extract_gamedata(apk, t, apk_md5="abc")
    assert r["ok"] and r["tables"] == 150 and r["messages"] == 321 and r["engine"] is True
    assert (t.config_dir / "buildBase.json").read_text(encoding="utf-8") == '{"v": "new"}'
    assert (t.config_dir / "manifest.json").read_text(encoding="utf-8") == '{"keep": true}'
    assert t.engine.read_text(encoding="utf-8").startswith("window.__require")
    meta = json.loads(t.meta.read_text(encoding="utf-8"))
    assert meta["game_version"] == "4.4.7" and meta["scripts_version"] == "4.4.8"
    assert meta["apk_md5"] == "abc" and meta["tables"] == 150
    old = list(t.backups.glob("gamedata-*"))
    assert old and (old[0] / "config" / "buildBase.json").read_text(encoding="utf-8") == '{"v": "old"}'


def test_a_failed_extraction_leaves_the_current_data_untouched(tmp_path, monkeypatch, fake_pipeline):
    from nta_agent import gamedata
    t = _targets(tmp_path)
    t.config_dir.mkdir(parents=True)
    (t.config_dir / "buildBase.json").write_text('{"v": "old"}', encoding="utf-8")
    monkeypatch.setattr(gamedata, "extract_config_tables", lambda apk, out, *a, **k: (0, []))
    apk = tmp_path / "a.apk"
    apk.write_bytes(_apk_bytes())
    r = gu.extract_gamedata(apk, t, apk_md5="abc")
    assert r["ok"] is False and "bảng" in r["detail"]
    assert (t.config_dir / "buildBase.json").read_text(encoding="utf-8") == '{"v": "old"}'
    assert not t.meta.exists()


def test_apply_update_runs_discover_download_and_extract_in_order(tmp_path, fake_pipeline):
    t = _targets(tmp_path)
    data = _apk_bytes("4.4.7", "4.4.8")
    md5 = hashlib.md5(data).hexdigest()
    steps = []
    r = gu.apply_update(
        t, work_dir=tmp_path / "work",
        discover_fn=lambda: steps.append("discover") or {"apk_url": "u", "apk_version": "4.4.8"},
        head_fn=lambda url: steps.append("head") or {"size": len(data), "md5": md5},
        download_fn=lambda url, dest, m, progress=None: steps.append("download") or
        dest.write_bytes(data) or dest)
    assert steps == ["discover", "head", "download"] and r["ok"] and r["scripts_version"] == "4.4.8"
    assert not list((tmp_path / "work").glob("*.apk"))          # the 117 MB file is not kept


# ---- the service the dashboard talks to ---------------------------------------------------
def _service(tmp_path, check=None, apply=None):
    return gu.GameUpdateService(tmp_path / "gameupdate.json",
                                check_fn=check or (lambda: {"update_available": False, "reason": ""}),
                                apply_fn=apply or (lambda: {"ok": True, "detail": "ok"}))


def test_check_stores_the_status_and_the_time(tmp_path):
    svc = _service(tmp_path, check=lambda: {"update_available": True, "reason": "apk mới"})
    st = svc.check()
    assert st["status"]["update_available"] is True and st["checked_at"] > 0 and not st["error"]
    assert svc.state()["status"]["reason"] == "apk mới"            # persisted for the dashboard


def test_a_network_error_is_stored_not_raised(tmp_path):
    def boom():
        raise gu.UpdateError("không mở được trang tải game: timeout")
    st = _service(tmp_path, check=boom).check()
    assert "timeout" in st["error"]


def test_apply_runs_in_the_background_and_reports_the_result(tmp_path):
    import threading
    gate = threading.Event()

    def slow_apply():
        gate.wait(2)
        return {"ok": True, "detail": "150 bảng"}
    svc = _service(tmp_path, apply=slow_apply)
    assert svc.apply() is True
    assert svc.state()["apply"]["state"] == "running"
    assert svc.apply() is False                                   # one at a time
    gate.set()
    svc.join(2)
    ap = svc.state()["apply"]
    assert ap["state"] == "done" and "150 bảng" in ap["detail"]


def test_a_failed_apply_is_reported_as_an_error(tmp_path):
    svc = _service(tmp_path, apply=lambda: {"ok": False, "detail": "md5 không khớp"})
    svc.apply()
    svc.join(2)
    ap = svc.state()["apply"]
    assert ap["state"] == "error" and "md5" in ap["detail"]
