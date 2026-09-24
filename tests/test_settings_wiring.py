import pytest

from nta_agent import settings


@pytest.fixture(autouse=True)
def iso(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "s.json")
    for env in settings.KEYS.values():
        monkeypatch.delenv(env, raising=False)


def test_brain_reads_key_from_settings_each_call():
    from nta_agent.brain import llm
    with pytest.raises(llm.BrainUnavailable):
        llm.default_chat()
    settings.set_values({"openai_api_key": "sk-abc12345"})
    assert callable(llm.default_chat())  # no restart needed


def test_distinct_id_from_settings_and_optional_for_dashboard():
    from nta_agent.runtime.config import ConfigError, RuntimeConfig
    with pytest.raises(ConfigError):
        RuntimeConfig.from_env({})
    assert RuntimeConfig.from_env({}, require_distinct=False).distinct_id == ""
    settings.set_values({"distinct_id": "abc", "brain_max_calls": "7"})
    cfg = RuntimeConfig.from_env({})
    assert cfg.distinct_id == "abc" and cfg.brain_max_calls == 7


def test_adb_settings_used():
    from nta_agent import config
    settings.set_values({"adb_path": r"X:\adb.exe", "adb_serial": "emulator-5556"})
    s = config.Settings.detect()
    assert s.adb_path == r"X:\adb.exe" and s.serial == "emulator-5556"
