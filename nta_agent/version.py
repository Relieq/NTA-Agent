"""Single source of truth for the game build the agent targets.

When the game updates, bump ``GAME_VERSION`` here (and re-extract config tables +
regenerate ``nta_agent/data/config/manifest.json`` — see F2 regression guard).
The login handshake (``io/api/session.py``) and the config manifest both read
this so a version bump can never silently disagree between the two.
"""
from __future__ import annotations

# The game client version reported in the login handshake, and pinned by the
# config manifest. Keep in sync with the extracted config tables.
GAME_VERSION = "4.4.4"
