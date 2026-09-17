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


def test_armies_and_events_panels():
    assert "/api/armies" in _c("ArmiesPanel.js")
    assert "tốc hành quân" in _c("ArmiesPanel.js")
    ev = _c("EventsPanel.js")
    assert "/api/events" in ev
    assert "[object Object]" not in ev and "rationale" in ev  # object detail formatting preserved
    app = _app()
    assert "ArmiesPanel" in app and "EventsPanel" in app


def test_decisions_and_equipment_panels():
    dec = _c("DecisionsPanel.js")
    assert "/api/decisions" in dec and "/api/command" in dec and "reroll" in dec
    eq = _c("EquipmentPanel.js")
    assert "/api/equipment" in eq and "equip" in eq
    app = _app()
    assert "DecisionsPanel" in app and "EquipmentPanel" in app
