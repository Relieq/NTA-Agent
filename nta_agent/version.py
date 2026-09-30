"""Single source of truth for the game build the agent targets.

When the game updates, bump ``GAME_VERSION`` here (and re-extract config tables +
regenerate ``nta_agent/data/config/manifest.json`` — see F2 regression guard).
The login handshake (``io/api/session.py``) and the config manifest both read
this so a version bump can never silently disagree between the two.
"""
from __future__ import annotations

# The game client version reported in the login handshake, and pinned by the
# config manifest. Keep in sync with the extracted config tables.
GAME_VERSION = "4.4.8"

# Android app versions (versionName) that BUNDLE the game scripts of GAME_VERSION. The
# handshake sends the scripts' version, not the app's: app 4.4.7 ships 4.4.8 scripts
# (its hot-update manifest says 4.4.8) and the server refused 4.4.7 with ecode 500060.
GAME_APK_VERSIONS = ("4.4.7",)
