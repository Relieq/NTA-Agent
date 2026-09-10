"""Integration tests that require a live BlueStacks device (run: pytest -m device)."""

import pytest

from nta_agent.io.adb import DeviceManager


@pytest.fixture(scope="module")
def dm() -> DeviceManager:
    return DeviceManager.connect()


@pytest.mark.device
def test_screencap_matches_configured_resolution(dm: DeviceManager):
    img = dm.screencap()
    assert img.size == (dm.settings.screen_w, dm.settings.screen_h)


@pytest.mark.device
def test_current_focus_reports_a_window(dm: DeviceManager):
    assert dm.current_focus()  # non-empty string
