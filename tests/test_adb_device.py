"""Integration tests that require a live BlueStacks device (run: pytest -m device)."""

import pytest

from nta_agent.io.adb import DeviceManager


@pytest.fixture(scope="module")
def dm() -> DeviceManager:
    # connect() trusts the configured serial, so check the emulator is really attached
    # (LDPlayer is normally closed day to day — skip instead of failing the suite).
    try:
        d = DeviceManager.connect()
        listed = d._raw(["devices"], timeout=10).decode("utf-8", "ignore")
    except Exception as e:
        pytest.skip(f"no adb/emulator: {e}")
    if f"{d.serial}\tdevice" not in listed:
        pytest.skip(f"emulator {d.serial} not attached")
    return d


@pytest.mark.device
def test_screencap_matches_current_display(dm: DeviceManager):
    # screencap follows the live rotation (the game may lock portrait), while the
    # configured resolution is orientation-agnostic — assert it's one orientation.
    img = dm.screencap()
    assert set(img.size) == {dm.settings.screen_w, dm.settings.screen_h}


@pytest.mark.device
def test_current_focus_reports_a_window(dm: DeviceManager):
    assert dm.current_focus()  # non-empty string


def test_adb_runs_from_its_own_folder(monkeypatch):
    # the adb daemon inherits the working dir of the first adb call; from app\ it
    # locked that folder and broke updates (2026-09-27)
    from nta_agent.config import Settings
    from nta_agent.io import adb as adbmod
    seen = []

    class P:
        returncode, stdout, stderr = 0, b"List of devices attached\n", b""
    monkeypatch.setattr(adbmod.subprocess, "run", lambda args, **kw: seen.append(kw.get("cwd")) or P())
    dm = adbmod.DeviceManager(settings=Settings(adb_path=r"C:\LD\adb.exe", serial="emulator-5554"))
    dm.devices()
    assert seen == [r"C:\LD"]
