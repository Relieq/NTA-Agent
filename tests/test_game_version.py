"""F2 — the game version must have a single source of truth.

Always-on (no config tables needed): assert the login handshake defaults read
``nta_agent.version.GAME_VERSION`` rather than a hardcoded literal, so a version
bump can't disagree between the version module and the session layer.
"""
from __future__ import annotations

import inspect

from nta_agent.io.api.session import GameSession
from nta_agent.version import GAME_VERSION


def test_session_login_default_version_is_single_source():
    for method in ("login", "enter_game"):
        fn = getattr(GameSession, method, None)
        if fn is None:
            continue
        default = inspect.signature(fn).parameters["version"].default
        assert default == GAME_VERSION, (
            f"GameSession.{method} version default {default!r} != GAME_VERSION "
            f"{GAME_VERSION!r} — route it through nta_agent.version"
        )


def test_login_opts_uses_game_version():
    # the _login_opts default_factory builds {"version": GAME_VERSION, ...}
    field = GameSession.__dataclass_fields__["_login_opts"]
    assert field.default_factory()["version"] == GAME_VERSION
