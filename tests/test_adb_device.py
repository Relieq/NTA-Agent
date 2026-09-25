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
