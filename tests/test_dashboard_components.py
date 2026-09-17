from pathlib import Path

STATIC = Path("nta_agent/dashboard/static")


def _c(name):
    return (STATIC / "components" / name).read_text(encoding="utf-8")


def _app():
    return (STATIC / "components" / "App.js").read_text(encoding="utf-8")


def test_state_panels_read_state_and_are_mounted():
    assert "/api/state" in _c("ResourcePanel.js")
    assert "hàng đợi" in _c("CityPanel.js")           # queue label
    assert "Đội hành quân" in _c("MiscPanel.js")
    app = _app()
    for comp in ("ResourcePanel", "CityPanel", "MiscPanel"):
        assert comp in app
