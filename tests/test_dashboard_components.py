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


def test_territory_and_forts_panels():
    terr = _c("TerritoryPanel.js")
    assert "/api/territory" in terr and "/api/forts" in terr
    assert "owned_cells" in terr and "getContext" in terr and "setLineDash" in terr  # radius zone
    forts = _c("FortsPanel.js")
    assert "/api/forts" in forts and "Cứ Điểm" in forts
    app = _app()
    assert "TerritoryPanel" in app and "FortsPanel" in app


def test_territory_map_viewport():
    terr = _c("TerritoryPanel.js")
    # rendering
    assert "fillText" in terr and "accepted" in terr
    assert "labelStep" in terr and "[1, 2, 5, 10, 20, 25, 50, 100]" in terr
    assert "map_width" in terr or "MAPW" in terr        # y-flip uses map width
    # interaction
    assert "@mousedown" in terr and "@mousemove" in terr and "@mouseup" in terr
    assert "wheel" in terr and "getBoundingClientRect" in terr
    assert "Về thành chính" in terr                      # recenter control
    assert "/api/forts/decide" in terr                   # accept/reject on a rec
    assert "Math.min(60" in terr and "Math.max(6" in terr  # zoom clamp
    assert "bán kính 6 ô" in terr                        # legend explains the dashed zone


def test_forts_panel_decision_buttons():
    fp = _c("FortsPanel.js")
    assert "/api/forts/decide" in fp
    assert "Chấp thuận" in fp and "Từ chối" in fp
    assert "accepted" in fp and "rejected" in fp


def test_build_order_panel():
    bo = _c("BuildOrderPanel.js")
    assert "/api/profile" in bo
    assert "draggable" in bo and "Lưu thứ tự xây" in bo and "bỏ qua" in bo
    assert "BuildOrderPanel" in _app()


def test_control_bar_component():
    cb = _c("ControlBar.js")
    assert "/api/agent/status" in cb and '"/api/agent/"' in cb  # status poll + action base
    for a in ("act('start')", "act('pause')", "act('resume')", "act('stop')"):
        assert a in cb
    for engine in ("RUNNING", "PAUSED", "STOPPED", "CRASHED"):
        assert engine in cb
    assert "ControlBar" in _c("StatusHeader.js")


def test_brain_chat_panel_and_final_order():
    ch = _c("BrainChatPanel.js")
    assert "/api/chat" in ch and "Chiến thuật" in ch and "Gửi" in ch
    app = _app()
    order = [app.index(c) for c in ("ResourcePanel", "CityPanel", "MiscPanel", "ArmiesPanel",
        "DecisionsPanel", "EquipmentPanel", "TerritoryPanel", "FortsPanel", "BuildOrderPanel",
        "BrainChatPanel", "EventsPanel")]
    assert order == sorted(order)  # components appear in this order (template runs last)
