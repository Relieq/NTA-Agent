import pytest

from nta_agent import settings


@pytest.fixture(autouse=True)
def _isolate_user_settings(monkeypatch, tmp_path):
    """Tests never see the developer's settings.json or a leaked .env (some tests
    call entry points that load .env into os.environ)."""
    monkeypatch.setattr(settings, "_path", lambda: tmp_path / "_settings.json")
    for env in settings.KEYS.values():
        monkeypatch.delenv(env, raising=False)
