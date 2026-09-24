import pytest

from nta_agent import settings


@pytest.fixture
def store(monkeypatch, tmp_path):
    p = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "_path", lambda: p)
    for env in settings.KEYS.values():
        monkeypatch.delenv(env, raising=False)
    return p


def test_env_wins_over_file(store, monkeypatch):
    settings.set_values({"openai_model": "gpt-x"})
    assert settings.get("openai_model") == "gpt-x"
    monkeypatch.setenv("OPENAI_MODEL", "gpt-env")
    assert settings.get("openai_model") == "gpt-env"


def test_secret_is_encrypted_on_disk_and_masked_in_view(store):
    settings.set_values({"openai_api_key": "sk-test-1234567890-xyzabcd"})
    assert "sk-test-1234567890-xyzabcd" not in store.read_text(encoding="utf-8")
    assert settings.get("openai_api_key") == "sk-test-1234567890-xyzabcd"
    v = settings.view()
    assert v["openai_api_key"] == {"set": True, "value": "sk-…abcd"}
    assert v["openai_model"] == {"set": False, "value": ""}


def test_blank_clears_and_unknown_rejected(store):
    settings.set_values({"openai_api_key": "sk-abc12345"})
    settings.set_values({"openai_api_key": ""})
    assert settings.get("openai_api_key") is None
    with pytest.raises(KeyError):
        settings.set_values({"evil": "x"})


def test_corrupt_file_is_empty(store):
    store.write_text("{not json", encoding="utf-8")
    assert settings.get("distinct_id") is None
    assert settings.get("distinct_id", "d") == "d"


def test_undecryptable_secret_reads_as_missing(store):
    store.write_text('{"openai_api_key": {"dpapi": "AAAA"}}', encoding="utf-8")
    assert settings.get("openai_api_key") is None


def test_short_secret_mask_reveals_little():
    assert settings.mask("0123456789abcdef") == "…ef"
    assert settings.mask("sk-proj-0123456789abcdefghij") == "sk-…ghij"
