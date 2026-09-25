from pathlib import Path

from nta_agent.dashboard.page import INDEX_HTML

STATIC = Path("nta_agent/dashboard/static")


def _read(rel):
    return (STATIC / rel).read_text(encoding="utf-8")


def test_shell_mounts_vue_app():
    assert 'id="app"' in INDEX_HTML
    assert "/static/vendor/vue.global.prod.js" in INDEX_HTML
    assert "/static/app.css" in INDEX_HTML
    assert 'type="module"' in INDEX_HTML and "/static/app.js" in INDEX_HTML


def test_app_module_imports_components():
    app = _read("app.js")
    assert "./components/App.js" in app
    assert "createApp" in app


def test_design_system_defines_tokens():
    css = _read("app.css")
    for tok in ("--bg", "--panel", "--border", "--accent", "--muted"):
        assert tok in css


def test_status_header_component_present():
    hdr = _read("components/StatusHeader.js")
    assert "/api/state" in hdr
    assert "NTA Agent" in hdr


def test_setup_and_settings_panels_wired():
    app = _read("components/App.js")
    assert "SetupPanel" in app and "SettingsPanel" in app and 'id:"setup"' in app
    setup = _read("components/SetupPanel.js")
    assert "/api/setup/run" in setup and "/api/setup/override" in setup
    st = _read("components/SettingsPanel.js")
    assert "/api/settings" in st and "/api/settings/test-key" in st
    assert 'type="password"' not in st or "secret" in st  # secrets never pre-filled


def test_chat_panel_confirms_strike_and_shows_edits_in_words():
    js = _read("components/BrainChatPanel.js")
    assert "strike_target:strike.value.targets" in js and "confirmStrike" in js
    assert "applied_text" in js and "JSON.stringify(o.applied)" not in js
