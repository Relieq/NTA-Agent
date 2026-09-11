"""MQTT client for the NTA game protocol (mqant gate over MQTT/WebSocket/TLS).

Wire behaviour reverse-engineered from the game client (see docs/PROTOCOL.md):

* Transport: Paho MQTT v3.1.1 over WebSocket path ``/mqtt``, TLS.
* clientId: ``"t" + uuid4``. No MQTT username/password — auth is a login *message*.
* Request: publish protobuf ``MODULE_HD_ACTION_C2S`` to topic
  ``module/HD_Action/<reqId>`` at QoS 1.
* Reply: the gate PUBLISHes back on the same topic; payload is
  ``S2C_RESULT{data,error}`` where ``data`` is ``MODULE_HD_ACTION_S2C``.
  No SUBSCRIBE is needed — the gate routes by connection.
* Correlation: monotonically increasing ``reqId`` carried in the topic tail.

This class is transport-only; login/session orchestration lives a layer up.
"""
from __future__ import annotations

import ssl
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import paho.mqtt.client as mqtt

from nta_agent.io.api.protocol import Codec


@dataclass
class ServerConfig:
    host: str
    port: int = 3653
    use_ssl: bool = True
    ws_path: str = "/mqtt"


class ApiError(RuntimeError):
    """A request returned a non-empty S2C_RESULT.error."""


class NotConnected(RuntimeError):
    """A request was attempted while the MQTT connection was down."""


@dataclass
class GameClient:
    server: ServerConfig
    codec: Codec = field(default_factory=Codec.load)
    client_id: str = field(default_factory=lambda: "t" + uuid.uuid4().hex)
    keepalive: int = 30

    _mqtt: mqtt.Client = field(init=False, default=None)
    _req_id: int = field(init=False, default=0)
    _pending: dict[int, _Pending] = field(init=False, default_factory=dict)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)
    _connected: threading.Event = field(init=False, default_factory=threading.Event)
    on_push: Callable[[str, dict], None] | None = None

    # ---- lifecycle ------------------------------------------------------- #
    def connect(self, timeout: float = 15) -> None:
        c = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            transport="websockets",
            protocol=mqtt.MQTTv311,
            clean_session=True,
        )
        c.ws_set_options(path=self.server.ws_path)
        if self.server.use_ssl:
            ctx = ssl.create_default_context()
            # The gate presents a valid cert for its domain; keep verification on.
            c.tls_set_context(ctx)
        c.on_connect = self._on_connect
        c.on_message = self._on_message
        c.on_disconnect = self._on_disconnect
        self._mqtt = c
        c.connect(self.server.host, self.server.port, keepalive=self.keepalive)
        c.loop_start()
        if not self._connected.wait(timeout):
            c.loop_stop()
            raise TimeoutError("MQTT connect timed out to %s:%d" % (self.server.host, self.server.port))

    def close(self) -> None:
        if self._mqtt:
            self._mqtt.loop_stop()
            self._mqtt.disconnect()
        self._connected.clear()

    def reconnect(self, timeout: float = 15) -> None:
        """Tear down the old MQTT client and open a fresh connection."""
        self.close()
        # Abandon any in-flight requests; the caller re-issues after re-login.
        with self._lock:
            for pending in self._pending.values():
                pending.error = "reconnect"
                pending.event.set()
            self._pending.clear()
        self.connect(timeout=timeout)

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    # ---- request/reply --------------------------------------------------- #
    def request(self, route: str, params: dict[str, Any] | None = None, timeout: float = 15) -> dict:
        """Send ``route`` (e.g. "lobby/HD_TryLogin") and block for the decoded reply."""
        params = params or {}
        msg_name = route.replace("/", "_").upper()
        c2s, s2c = msg_name + "_C2S", msg_name + "_S2C"
        if not self.codec.has(c2s):
            raise KeyError("unknown route %s (no %s in schema)" % (route, c2s))
        if not self._connected.is_set():
            raise NotConnected("not connected — call connect()/reconnect() first")

        with self._lock:
            self._req_id += 1
            req_id = self._req_id
            pending = _Pending(s2c=s2c)
            self._pending[req_id] = pending

        body = self.codec.encode(c2s, params)
        topic = "%s/%s" % (route, req_id)
        self._mqtt.publish(topic, body, qos=1)

        if not pending.event.wait(timeout):
            self._pending.pop(req_id, None)
            raise TimeoutError("request %s timed out" % route)
        if pending.error:
            raise ApiError("%s: %s" % (route, pending.error))
        return pending.data or {}

    # ---- paho callbacks -------------------------------------------------- #
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0 or getattr(reason_code, "is_failure", False) is False:
            self._connected.set()

    def _on_disconnect(self, client, userdata, *args):
        self._connected.clear()

    def _on_message(self, client, userdata, message):
        parts = message.topic.split("/")
        req_id = None
        if parts and parts[-1].isdigit():
            req_id = int(parts[-1])
        try:
            envelope = self.codec.decode("S2C_RESULT", message.payload)
        except Exception:
            return
        error = envelope.get("error") or ""
        data_bytes = envelope.get("data", b"")

        pending = self._pending.pop(req_id, None) if req_id is not None else None
        if pending is not None:
            if error:
                pending.error = error
            elif data_bytes:
                try:
                    pending.data = self.codec.decode(pending.s2c, data_bytes)
                except Exception as e:  # keep raw on decode failure
                    pending.data = {"_raw": data_bytes, "_decode_error": str(e)}
            else:
                pending.data = {}
            pending.event.set()
            return

        # server push (no matching reqId): route to on_push if set
        if self.on_push and not error:
            route = "/".join(parts[:-1]) if req_id is not None else message.topic
            self.on_push(route, {"_raw": data_bytes})


@dataclass
class _Pending:
    s2c: str
    event: threading.Event = field(default_factory=threading.Event)
    data: dict | None = None
    error: str = ""
