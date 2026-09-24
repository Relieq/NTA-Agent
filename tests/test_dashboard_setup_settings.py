import io
import json
import urllib.error

from nta_agent import settings
from nta_agent.dashboard import server


def test_settings_view_masks_and_update():
    r = server.update_settings({"openai_api_key": "sk-abcdefgh-0123456789-1234"})
    assert r["ok"] is True
    assert server.read_settings()["openai_api_key"]["value"] == "sk-…1234"
    assert "sk-abcdefgh-0123456789-1234" not in json.dumps(r)
    assert server.update_settings({"nope": 1})["ok"] is False
    assert server.update_settings({})["ok"] is False


def test_openai_key_probe_never_echoes_key():
    assert server.test_openai_key()["ok"] is False          # no key yet
    settings.set_values({"openai_api_key": "sk-secret-9999"})

    class Resp(io.BytesIO):
        status = 200
    assert server.test_openai_key(opener=lambda req, timeout: Resp(b"{}")) == {"ok": True}

    def denied(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, None)
    r = server.test_openai_key(opener=denied)
    assert r["ok"] is False and "401" in r["error"] and "sk-secret" not in json.dumps(r)


def test_start_blocked_until_setup_ready(monkeypatch, tmp_path):
    from nta_agent.dashboard.supervisor import AgentSupervisor
    from nta_agent.runtime.config import RuntimeConfig
    from nta_agent.setup import steps
    monkeypatch.setattr(steps, "ready", lambda: False)
    sup = AgentSupervisor(RuntimeConfig(distinct_id="", log_dir=tmp_path))
    r = sup.start()
    assert r["engine"] == "STOPPED" and "Thiết lập" in r["error"]


def test_app_info():
    info = server.read_app_info()
    assert info["version"] == "dev" and info["packaged"] is False
