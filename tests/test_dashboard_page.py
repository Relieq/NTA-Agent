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
