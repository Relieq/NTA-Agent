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
from dataclasses import dataclass, field
from typing import Any

from nta_agent.io.api.client import GameClient, ServerConfig
from nta_agent.state.schema import GameState
from nta_agent.state.store import apply_user


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
    client: GameClient = field(init=False)
    state: GameState = field(default_factory=GameState)
    pushes: list[PushRecord] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

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
        account_token: str,
        distinct_id: str = "",
        *,
        lang: str = "vi",
        os: str = "Android 9",
        platform: str = "google",
        version: str = "4.4.4",
        timeout: float = 15,
    ) -> dict:
        """lobby/HD_TryLogin; populates state.user and returns the raw reply."""
        reply = self.client.request(
            "lobby/HD_TryLogin",
            {
                "accountToken": account_token,
                "distinctId": distinct_id,
                "os": os,
                "lang": lang,
                "platform": platform,
                "version": version,
            },
            timeout=timeout,
        )
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
        version: str = "4.4.4",
    ) -> dict:
        """Enter the assigned match server and load state into self.state.

        Flow: GetRoomStateInfos (for the sid) -> SelectGameServer -> game/HD_Entry.
        The Entry ``rst`` is authoritative, so it replaces self.state (preserving user).
        Returns the raw Entry reply.
        """
        if sid is None:
            rooms = self.client.request("lobby/HD_GetRoomStateInfos", {})
            sid = rooms.get("playSid") or rooms.get("allotPlaySid") or 0
        if not sid:
            raise RuntimeError("no game server assigned (allotPlaySid/playSid empty)")

        self.client.request("lobby/HD_SelectGameServer", {"sid": int(sid)})
        entry = self.client.request("game/HD_Entry", {
            "sid": int(sid), "version": version, "isReconnect": False,
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
        return entry

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
