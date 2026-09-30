import pytest

from nta_agent import paths, settings
from nta_agent.setup import steps
from nta_agent.version import GAME_VERSION


class FakeDM:
    def __init__(self, version=GAME_VERSION, root=True, rid="rid-1"):
        self.version, self.root, self.rid = version, root, rid
        self.serial = "emulator-5554"
        self.listed = ["emulator-5554"]

    def devices(self):
        return list(self.listed)

    def shell(self, cmd, timeout=30):
        if "dumpsys package" in cmd:
            return f"    versionName={self.version}\n" if self.version else ""
        return ""

    def su(self, cmd, timeout=30):
        if cmd.strip() == "id":
            return "uid=0(root) gid=0(root)" if self.root else "uid=2000(shell)"
        if "thinkingdata" in cmd:
            return f'<map><string name="randomID">{self.rid}</string></map>'
        return ""


@pytest.fixture(autouse=True)
def iso(monkeypatch, tmp_path):
    monkeypatch.setenv("NTA_DATA_DIR", str(tmp_path))


def test_root_step_and_hint():
    assert steps.run_step("root", dm_factory=FakeDM)["ok"] is True
    r = steps.run_step("root", dm_factory=lambda: FakeDM(root=False))
    assert r["ok"] is False and "Root" in r["hint"] and r["doc"] == "README.md#buoc-3-root"


def test_game_version_mismatch_and_override():
    assert steps.run_step("game", dm_factory=FakeDM)["ok"] is True
    bad = steps.run_step("game", dm_factory=lambda: FakeDM(version="9.9.9"))
    assert bad["ok"] is False and "9.9.9" in bad["detail"] and bad["overridable"]
    ov = steps.override("game")
    assert ov["ok"] and ov["overridden"]
    with pytest.raises(KeyError):
        steps.override("token")


def test_distinct_id_saved_to_settings():
    assert steps.run_step("distinct_id", dm_factory=lambda: FakeDM(rid="abc-123"))["ok"]
    assert settings.get("distinct_id") == "abc-123"


def test_token_step_writes_token(monkeypatch):
    monkeypatch.setattr(steps, "read_account_token", lambda dm: "TOKEN123")
    assert steps.run_step("token", dm_factory=FakeDM)["ok"] is True
    assert paths.token_path().read_text(encoding="utf-8") == "TOKEN123"
    monkeypatch.setattr(steps, "read_account_token", lambda dm: "")
    r = steps.run_step("token", dm_factory=FakeDM)
    assert r["ok"] is False and "Đăng nhập" in r["hint"]


def test_exception_becomes_failed_step():
    def boom():
        raise RuntimeError("no device")
    r = steps.run_step("device", dm_factory=boom)
    assert r["ok"] is False and "no device" in r["detail"]


def test_status_ready_only_when_all_ok(monkeypatch):
    assert steps.status()["ready"] is False
    for n in steps.STEPS:
        monkeypatch.setitem(steps._RUNNERS, n, lambda get_dm: {"ok": True, "detail": ""})
        steps.run_step(n, dm_factory=FakeDM)
    assert steps.status()["ready"] is True
    monkeypatch.setitem(steps._RUNNERS, "token", lambda get_dm: {"ok": False, "detail": "x"})
    steps.run_step("token", dm_factory=FakeDM)
    assert steps.status()["ready"] is False


def test_dev_checkout_is_never_gated():
    assert paths.is_packaged() is False
    assert steps.ready() is True


class ApkDM(FakeDM):
    def shell(self, cmd, timeout=30):
        if "pm path" in cmd:
            return "package:/data/app/x/base.apk\n"
        return super().shell(cmd, timeout)

    def pull(self, remote, local, timeout=60):
        with open(local, "wb") as f:
            f.write(b"apk")
        return local


def _stub_gamedata(monkeypatch, found):
    used = {}
    monkeypatch.setattr(paths, "is_packaged", lambda root=None: True)
    monkeypatch.setattr(steps.gamedata, "find_xxtea_key", lambda apk: found)

    def schema(apk, out, key):
        used["key"] = key
        return 891
    monkeypatch.setattr(steps.gamedata, "build_schema", schema)
    monkeypatch.setattr(steps.gamedata, "extract_config_tables", lambda apk, out: (88, []))
    monkeypatch.setattr(steps.gamedata, "decrypt_engine", lambda apk, out, key: 1)
    return used


def test_gamedata_discovers_key_from_apk_without_user_input(monkeypatch):
    used = _stub_gamedata(monkeypatch, "found-key-123456")
    r = steps.run_step("gamedata", dm_factory=ApkDM)
    assert r["ok"] is True and "891 message" in r["detail"]
    assert used["key"] == b"found-key-123456"
    assert settings.get("xxtea_key") is None          # nothing stored


def test_gamedata_user_key_overrides_and_missing_key_fails(monkeypatch):
    used = _stub_gamedata(monkeypatch, None)
    assert steps.run_step("gamedata", dm_factory=ApkDM)["ok"] is False
    settings.set_values({"xxtea_key": "typed-key-000000"})
    assert steps.run_step("gamedata", dm_factory=ApkDM)["ok"] is True
    assert used["key"] == b"typed-key-000000"


def test_readme_has_every_setup_anchor():
    from pathlib import Path
    readme = Path("README.md").read_text(encoding="utf-8")
    for _hint, anchor in steps._HINTS.values():
        assert f'<a id="{anchor}"></a>' in readme, anchor



# ---- issue #79: steps must really talk to adb ----------------------------------
def test_device_step_fails_when_adb_sees_no_device(monkeypatch):
    dm = FakeDM()
    dm.serial, dm.listed = "5555", []
    monkeypatch.setattr(steps, "_ldplayer_adb_debug", lambda: [("leidian0.config", 0)])
    r = steps.run_step("device", dm_factory=lambda: dm)
    assert r["ok"] is False and "không thấy thiết bị" in r["detail"]
    assert "adbDebug" in r["hint"]                      # LDPlayer 14 has no UI toggle


def test_device_step_fixes_a_wrong_serial_when_one_device_is_there():
    dm = FakeDM()
    dm.serial, dm.listed = "5555", ["emulator-5554"]
    r = steps.run_step("device", dm_factory=lambda: dm)
    assert r["ok"] is True and settings.get("adb_serial") == "emulator-5554"


def test_root_step_blames_the_connection_not_root():
    class NoDevice(FakeDM):
        def su(self, cmd, timeout=30):
            raise RuntimeError("adb shell su -c 'id' failed: adb.exe: device '5555' not found")
    r = steps.run_step("root", dm_factory=NoDevice)
    assert r["ok"] is False and "Root" not in r["hint"] and "bước 2" in r["hint"]


def test_ldplayer14_adb_is_a_candidate():
    from nta_agent import config
    assert any("LDPlayer14" in str(p) for p in config._ADB_CANDIDATES)


def test_settings_refuses_a_bare_port_as_serial():
    from nta_agent.dashboard.server import update_settings
    r = update_settings({"adb_serial": "5555"})
    assert r["ok"] is False and "127.0.0.1:5555" in r["error"]


def test_game_step_accepts_the_apk_version_that_bundles_our_handshake_version():
    # 2026-09-30: the Android app is 4.4.7 but its bundled game scripts (what the client
    # sends to the server) are 4.4.8 — the server accepts only the latter
    from nta_agent.version import GAME_APK_VERSIONS
    assert GAME_APK_VERSIONS, "list the app versions that bundle GAME_VERSION"
    r = steps.run_step("game", dm_factory=lambda: FakeDM(version=GAME_APK_VERSIONS[0]))
    assert r["ok"] is True
