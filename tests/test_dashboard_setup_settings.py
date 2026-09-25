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


def test_model_list_filters_to_chat_models():
    assert server.list_openai_models()["ok"] is False           # no key yet
    settings.set_values({"openai_api_key": "sk-secret-model-list-000000"})
    ids = ["gpt-4o-mini", "gpt-4o-mini-2024-07-18", "gpt-4o-audio-preview", "o3-mini",
           "text-embedding-3-small", "whisper-1", "gpt-4o-realtime-preview", "dall-e-3",
           "gpt-4.1", "gpt-image-1", "omni-moderation-latest", "gpt-3.5-turbo-instruct"]

    class Resp(io.BytesIO):
        status = 200
    body = json.dumps({"data": [{"id": i} for i in ids]}).encode()
    r = server.list_openai_models(opener=lambda req, timeout: Resp(body))
    assert r == {"ok": True, "models": ["gpt-4.1", "gpt-4o-mini", "o3-mini"]}

    def denied(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, None)
    r = server.list_openai_models(opener=denied)
    assert r["ok"] is False and "401" in r["error"] and "sk-secret" not in json.dumps(r)


def test_crash_status_carries_last_run_log_tail(tmp_path):
    from nta_agent.dashboard.supervisor import AgentSupervisor
    from nta_agent.runtime.config import RuntimeConfig
    sup = AgentSupervisor(RuntimeConfig(distinct_id="", log_dir=tmp_path))
    (tmp_path / "agent.log").write_text(
        "\n=== agent start 2026-09-25 08:00:00 ===\nold run error\n"
        "\n=== agent start 2026-09-25 08:54:20 ===\nTraceback (most recent call last):\n"
        "ConnectionError: login failed\n", encoding="utf-8")
    sup._last_exit, sup._user_stopped = 1, False
    st = sup._status()
    assert st["engine"] == "CRASHED"
    assert st["log_tail"] == ["Traceback (most recent call last):", "ConnectionError: login failed"]
    f = sup._open_agent_log()
    f.close()
    assert "=== agent start" in (tmp_path / "agent.log").read_text(encoding="utf-8").splitlines()[-1]
