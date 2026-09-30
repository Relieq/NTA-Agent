"""The game version the agent declares at login.

``nta_agent.version.GAME_VERSION`` is the default; a user override (Settings
``game_version`` / env ``NTA_GAME_VERSION``) replaces it for experiments — the server only
accepts a window of versions (ecode 500060 too low / 500122 too high), and what the agent
sends must still match the protocol + tables it extracted from the game."""
from __future__ import annotations

import inspect

import pytest

from nta_agent import settings
from nta_agent.io.api.session import GameSession
from nta_agent.version import GAME_VERSION, handshake_version


@pytest.fixture
def store(monkeypatch, tmp_path):
    p = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "_path", lambda: p)
    for env in settings.KEYS.values():
        monkeypatch.delenv(env, raising=False)
    return p


def test_default_handshake_is_the_single_source(store):
    assert handshake_version() == GAME_VERSION


def test_session_methods_resolve_the_version_at_call_time():
    # no hard-coded literal default: None -> handshake_version() when called
    for method in ("login", "enter_game"):
        assert inspect.signature(getattr(GameSession, method)).parameters["version"].default is None


def test_user_override_wins_over_the_default(store, monkeypatch):
    settings.set_values({"game_version": "9.9.9"})
    assert handshake_version() == "9.9.9"
    monkeypatch.setenv("NTA_GAME_VERSION", "8.8.8")          # env still beats the file
    assert handshake_version() == "8.8.8"


def test_login_sends_the_overridden_version(store):
    settings.set_values({"game_version": "9.9.9"})
    sent = {}

    class Client:
        def request(self, route, params, timeout=15):
            sent[route] = params
            return {"accountToken": "t" * 40, "user": {}}
    s = GameSession.__new__(GameSession)
    s.client, s._distinct_id, s._login_opts, s.token_path = Client(), "", {}, None
    s._try_login = lambda tok, timeout=15: sent.update(opts=dict(s._login_opts)) or {}
    s.login("tok")
    assert sent["opts"]["version"] == "9.9.9"


def test_settings_validate_the_version_format(store):
    from nta_agent.dashboard.server import update_settings
    assert update_settings({"game_version": "abc"})["ok"] is False
    assert update_settings({"game_version": "4.4.9"})["ok"] is True
    assert handshake_version() == "4.4.9"
    assert update_settings({"game_version": ""})["ok"] is True      # blank = back to default
    assert handshake_version() == GAME_VERSION
