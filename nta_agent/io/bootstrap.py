"""Token bootstrap over ADB — the one thing the API path can't do alone.

The game's ``accountToken`` is minted by an OAuth login (Google/Facebook/…) that
the standalone API client cannot perform. This module drives the app over ADB
to (re)mint a token and hand it to the API session:

* :func:`read_account_token` — read the current token from the app's localStorage
  (jsb.sqlite) via root; no app interaction.
* :func:`refresh_token_via_app` — force a fresh login: restart the app, tap the
  OAuth button, wait for the token to change, then freeze the app so it won't
  spend the token. Returns the new token (also written to ``token_path``).

These require a rooted emulator (LDPlayer). Coordinates default to LDPlayer's
900x1600 login screen; override per device.
"""
from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path

from nta_agent.io.adb import DeviceManager

PACKAGE = "twgame.global.acers"
TOKEN_KEY = "slg_account_token"
GOOGLE_BUTTON_XY = (450, 1200)  # LDPlayer 900x1600 login screen


def read_account_token(dm: DeviceManager, package: str = PACKAGE) -> str:
    """Read slg_account_token from the app's localStorage (jsb.sqlite) as root."""
    remote_db = f"/data/data/{package}/databases/jsb.sqlite"
    staged = "/sdcard/nta_boot.sqlite"
    dm.su(f"cp {remote_db} {staged} && chmod 644 {staged}")
    local = str(Path(tempfile.gettempdir()) / "nta_boot.sqlite")
    dm.pull(staged, local)
    try:
        con = sqlite3.connect(local)
        row = con.execute("SELECT value FROM data WHERE key=?", (TOKEN_KEY,)).fetchone()
        return (row[0].strip() if row and row[0] else "")
    finally:
        try:
            con.close()
        except Exception:
            pass


def refresh_token_via_app(
    dm: DeviceManager,
    token_path: Path,
    *,
    package: str = PACKAGE,
    google_xy: tuple[int, int] = GOOGLE_BUTTON_XY,
    boot_wait: float = 16.0,
    login_wait: float = 22.0,
    freeze: bool = True,
) -> str:
    """Restart the app, OAuth-login, capture the fresh token, freeze the app.

    Returns the new token and writes it to ``token_path``. Raises RuntimeError if
    no fresh token appears.
    """
    before = ""
    try:
        before = read_account_token(dm, package)
    except Exception:
        pass

    dm.shell(f"am force-stop {package}")
    dm.launch_game()
    time.sleep(boot_wait)
    # A spent token drops the app to the login screen; tap the OAuth button.
    dm.tap(*google_xy)

    deadline = time.time() + login_wait
    token = ""
    while time.time() < deadline:
        time.sleep(3)
        try:
            token = read_account_token(dm, package)
        except Exception:
            token = ""
        if token and token != before and len(token) >= 32:
            break

    if freeze:
        dm.shell(f"am force-stop {package}")  # keep the app from spending the token
    if not (token and len(token) >= 32):
        raise RuntimeError("token refresh failed: no fresh token after OAuth")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token)
    return token


def make_token_refresher(dm: DeviceManager, token_path: Path, **kwargs):
    """Return a zero-arg callable for GameSession.token_refresher."""
    def _refresh() -> bool:
        try:
            refresh_token_via_app(dm, token_path, **kwargs)
            return True
        except Exception:
            return False
    return _refresh
