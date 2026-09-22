"""GameSession — authenticated, stateful layer over GameClient.

Responsibilities:
* log in (lobby/HD_TryLogin) and keep the connection alive,
* correlate request/reply (delegated to GameClient),
* capture server *pushes* (state the gate sends unprompted) with best-effort
  decode, so we can observe the live message flow and feed GameState.

The push decode is best-effort: a push arrives on topic ``module/HD_Event`` and
its ``S2C_RESULT.data`` is decoded as ``MODULE_HD_EVENT_S2C`` when that type
exists, else kept raw. This lets us learn unknown flows without guessing.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nta_agent.io.api.client import ApiError, GameClient, ServerConfig
from nta_agent.state.schema import GameState
from nta_agent.state.store import apply_user
from nta_agent.version import GAME_VERSION

# The server rotates the single-use accountToken; reusing a spent one fails here.
TOKEN_INVALID = "ecode.500002"


class TokenChainBroken(RuntimeError):
    """Login failed because the stored accountToken is spent/invalid.

    Recovery needs a fresh token from the app's OAuth flow (see io bootstrap),
    which the agent can drive over ADB.
    """


@dataclass
class PushRecord:
    ts: float
    route: str
    msg_type: str          # the S2C type we decoded as, or "" if raw
    data: dict[str, Any]
    error: str = ""


@dataclass
class GameSession:
    server: ServerConfig
    token_path: Path | None = None  # when set, login reads/writes the rotating token here
    client: GameClient = field(init=False)
    state: GameState = field(default_factory=GameState)
    pushes: list[PushRecord] = field(default_factory=list)
    # called with no args when the token chain is broken; should refresh token_path
    # (e.g. re-auth via the app over ADB) and return True on success.
    token_refresher: Callable[[], bool] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _distinct_id: str = ""
    _sid: int | None = None
    _in_game: bool = False
    _bt_deadlines: dict = field(default_factory=dict)  # build uid -> completion time
    _login_opts: dict = field(default_factory=lambda: {
        "lang": "vi", "os": "Android 9", "platform": "google", "version": GAME_VERSION})

    def __post_init__(self):
        self.client = GameClient(server=self.server)
        self.client.on_push = self._on_push

    # ---- lifecycle ------------------------------------------------------- #
    def connect(self, timeout: float = 15) -> None:
        self.client.connect(timeout=timeout)

    def close(self) -> None:
        self.client.close()

    def login(
        self,
        account_token: str | None = None,
        distinct_id: str = "",
        *,
        lang: str = "vi",
        os: str = "Android 9",
        platform: str = "google",
        version: str = GAME_VERSION,
        timeout: float = 15,
    ) -> dict:
        """lobby/HD_TryLogin; populates state.user and returns the raw reply.

        The accountToken is single-use: the server rotates it and returns the next
        one. If ``token_path`` is set, the token is read from there when not given
        and the rotated token is written back, so the chain self-maintains and the
        agent never needs the app again after the first bootstrap.
        """
        self._distinct_id = distinct_id or self._distinct_id
        self._login_opts = {"lang": lang, "os": os, "platform": platform, "version": version}
        try:
            return self._try_login(account_token, timeout=timeout)
        except ApiError as e:
            if TOKEN_INVALID not in str(e):
                raise
            # spent/invalid token: try to refresh (e.g. app OAuth over ADB) once
            if self.token_refresher and self.token_refresher():
                return self._try_login(None, timeout=timeout)
            raise TokenChainBroken(str(e)) from e

    def _try_login(self, account_token: str | None, *, timeout: float = 15) -> dict:
        if account_token is None:
            if not self.token_path or not self.token_path.exists():
                raise ValueError("no account_token given and token_path is empty")
            account_token = self.token_path.read_text().strip()
        opts = self._login_opts
        reply = self.client.request(
            "lobby/HD_TryLogin",
            {
                "accountToken": account_token,
                "distinctId": self._distinct_id,
                "os": opts["os"],
                "lang": opts["lang"],
                "platform": opts["platform"],
                "version": opts["version"],
            },
            timeout=timeout,
        )
        new_token = reply.get("accountToken")
        if new_token and self.token_path:
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(new_token)
        user = reply.get("user")
        if isinstance(user, dict):
            apply_user(self.state, user)
        self.state.source = "api"
        return reply

    def enter_game(
        self,
        *,
        sid: int | None = None,
        distinct_id: str = "",
        lang: str = "vi",
        version: str = GAME_VERSION,
    ) -> dict:
        """Enter the assigned match server and load state into self.state.

        Flow: GetRoomStateInfos (for the sid) -> SelectGameServer -> game/HD_Entry.
        The Entry ``rst`` is authoritative, so it replaces self.state (preserving user).
        Returns the raw Entry reply.
        """
        distinct_id = distinct_id or self._distinct_id
        is_reconnect = self._in_game and sid is not None
        room_type = 0
        if sid is None:
            rooms = self.client.request("lobby/HD_GetRoomStateInfos", {})
            sid = rooms.get("playSid") or rooms.get("allotPlaySid") or 0
            # current mode = the active room state (state==2); roomType 0=free 1=newbie 2=ranked
            for stt in rooms.get("states") or []:
                if isinstance(stt, dict) and stt.get("state") == 2:
                    room_type = int(stt.get("roomType", 0) or 0)
                    break
        if not sid:
            raise RuntimeError("no game server assigned (allotPlaySid/playSid empty)")

        self.client.request("lobby/HD_SelectGameServer", {"sid": int(sid)})
        entry = self.client.request("game/HD_Entry", {
            "sid": int(sid), "version": version, "isReconnect": is_reconnect,
            "distinctId": distinct_id, "lang": lang, "os": "Android 9",
            "platform": "google", "pos": 0,
        })
        rst = entry.get("rst")
        if isinstance(rst, dict):
            from nta_agent.state.store import from_entry_rst
            user = self.state.user
            self.state = from_entry_rst(rst, user=user.raw or None)
            if not self.state.user.uid:
                self.state.user = user
            self.state.room_type = room_type
        self._sid = int(sid)
        self._in_game = True
        return entry

    def recover(self, timeout: float = 15) -> bool:
        """Rebuild a dropped session: reconnect -> re-login -> re-enter the game.

        Replays the remembered distinct_id/sid. Raises TokenChainBroken (via login)
        if the token is spent and no refresher fixes it. Returns True on success.
        """
        self.client.reconnect(timeout=timeout)
        self.login(distinct_id=self._distinct_id, timeout=timeout)
        if self._sid is not None:
            self.enter_game(sid=self._sid, distinct_id=self._distinct_id)
        return True

    # ---- convenience passthrough ---------------------------------------- #
    def request(self, route: str, params: dict | None = None, timeout: float = 15) -> dict:
        return self.client.request(route, params, timeout=timeout)

    # ---- push capture ---------------------------------------------------- #
    def _push_type(self, route: str) -> str:
        # Pushes are named MODULE_ONEVENT_NOTIFY or MODULE_HD_X_S2C depending on
        # the route; try the common suffixes and the bare route-derived name.
        base = route.replace("/", "_").upper()
        for name in (base + "_NOTIFY", base + "_S2C", base):
            if self.client.codec.has(name):
                return name
        return ""

    def _on_push(self, route: str, payload: dict) -> None:
        raw = payload.get("_raw", b"")
        msg_type = self._push_type(route)
        data: dict[str, Any] = {}
        if msg_type and raw:
            try:
                data = self.client.codec.decode(msg_type, raw)
            except Exception:
                data = {"_raw_len": len(raw)}
        elif raw:
            data = {"_raw_len": len(raw)}
        rec = PushRecord(ts=time.time(), route=route, msg_type=msg_type, data=data)
        with self._lock:
            self.pushes.append(rec)

    def drain_pushes(self) -> list[PushRecord]:
        with self._lock:
            out = list(self.pushes)
            self.pushes.clear()
        return out

    def sync(self) -> GameState:
        """Apply pending player/user update pushes into state, keeping it current."""
        from nta_agent.state.store import accrue_output, apply_notify, expire_build_queue
        for p in self.drain_pushes():
            if isinstance(p.data, dict) and "list" in p.data:
                apply_notify(self.state, p.data)
        # Fill resources from production locally (the client does this; the server
        # only pushes on changes) so stock never freezes between pushes.
        accrue_output(self.state, time.time())
        # Belt-and-suspenders: drop finished builds by wall-clock even if the
        # build-complete push was missed, so construction never freezes.
        self.state.build_queue, self._bt_deadlines = expire_build_queue(
            self.state.build_queue, self._bt_deadlines, time.time())
        # Stamp an absolute completion time so the dashboard can count down live
        # (surplusTime alone is static between server updates -> looks frozen).
        for item in self.state.build_queue:
            uid = str(item.get("uid", ""))
            if uid in self._bt_deadlines:
                item["endAt"] = int(self._bt_deadlines[uid] * 1000)
        return self.state
