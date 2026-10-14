"""Bring the game app INSIDE the emulator up to date before a token OAuth, by installing the
official APK over it with ``adb install -r`` (same package: data and login are kept). Never
uninstalls: a refusal (different signing key, downgrade) is simply left as it is."""
from nta_agent.io import appupdate


class DM:
    def __init__(self, version, install_out="Success"):
        self.version, self.install_out, self.installed = version, install_out, []

    def shell(self, cmd, timeout=30):
        return f"    versionName={self.version}\n" if "dumpsys package" in cmd else ""

    def install(self, apk, timeout=300):
        self.installed.append(apk)
        return self.install_out


def _steps(calls):
    def discover():
        calls.append("discover")
        return {"apk_url": "https://x/apk/jwm.v4.4.9.apk", "apk_version": "4.4.9"}

    def head(url):
        calls.append("head")
        return {"size": 3, "md5": "m"}

    def download(url, dest, md5, progress=None):
        calls.append("download")
        dest.write_bytes(b"apk")
        return dest
    return discover, head, download


def test_a_supported_installed_version_is_left_alone(tmp_path):
    calls = []
    d, h, dl = _steps(calls)
    r = appupdate.ensure_app_current(DM("4.4.7"), tmp_path, supported={"4.4.7", "4.4.8"},
                                     discover_fn=d, head_fn=h, download_fn=dl)
    assert r["action"] == "none" and calls == []


def test_an_older_app_gets_the_published_apk_installed_over_it(tmp_path):
    calls = []
    d, h, dl = _steps(calls)
    dm = DM("4.4.2")
    r = appupdate.ensure_app_current(dm, tmp_path, supported={"4.4.7", "4.4.8"},
                                     discover_fn=d, head_fn=h, download_fn=dl)
    assert r["action"] == "installed" and calls == ["discover", "head", "download"]
    assert len(dm.installed) == 1 and not list(tmp_path.glob("*.apk"))   # the file is removed


def test_a_refused_install_is_reported_and_nothing_is_uninstalled(tmp_path):
    calls = []
    d, h, dl = _steps(calls)
    dm = DM("4.4.2", install_out="Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]")
    r = appupdate.ensure_app_current(dm, tmp_path, supported={"4.4.7"},
                                     discover_fn=d, head_fn=h, download_fn=dl)
    assert r["action"] == "refused" and "INCOMPATIBLE" in r["detail"]


def test_a_newer_app_than_anything_we_know_is_not_downgraded(tmp_path):
    calls = []
    d, h, dl = _steps(calls)
    r = appupdate.ensure_app_current(DM("9.0.0"), tmp_path, supported={"4.4.7"},
                                     discover_fn=d, head_fn=h, download_fn=dl)
    assert r["action"] == "none" and calls == []


def test_supported_versions_include_what_the_last_data_update_recorded(tmp_path, monkeypatch):
    import json

    from nta_agent import paths
    monkeypatch.setattr(paths, "gamedata_dir", lambda: tmp_path)
    (tmp_path / "meta.json").write_text(json.dumps({"game_version": "4.4.9", "scripts_version": "4.5.0"}),
                                        encoding="utf-8")
    sup = appupdate.supported_versions()
    assert {"4.4.9", "4.5.0"} <= sup
    from nta_agent.version import GAME_APK_VERSIONS, GAME_VERSION
    assert GAME_VERSION in sup and set(GAME_APK_VERSIONS) <= sup
