"""Bridge to the headless battle-simulator sidecar (Node) over JSON-RPC/stdio.

Spawns ``node tools/battlesim/server.js`` once and reuses it. Every failure mode
(no Node, spawn error, timeout, protocol error) surfaces as :class:`SimUnavailable`
so callers can fall back to the cheap stats predictor without crashing the loop.
"""
from __future__ import annotations

import json
import queue
import subprocess
import threading
from pathlib import Path

# tools/battlesim/server.js, relative to the repo root (…/nta_agent/execution/predictors/).
_DEFAULT_SERVER = (
    Path(__file__).resolve().parents[3] / "tools" / "battlesim" / "server.js"
)


class SimUnavailable(Exception):
    """The simulator sidecar could not be reached (spawn/timeout/protocol/error)."""


class SimBridge:
    """A persistent JSON-RPC client for the battle-forecast sidecar."""

    def __init__(
        self,
        *,
        node: str = "node",
        server_js: str | Path = _DEFAULT_SERVER,
        env: dict | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.node = node
        self.server_js = str(server_js)
        self.env = env
        self.timeout = timeout
        self._proc: subprocess.Popen | None = None
        self._q: queue.Queue[str] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._next_id = 0
        self._lock = threading.Lock()

    # ---- lifecycle ------------------------------------------------------ #
    def _spawn(self) -> None:
        try:
            self._proc = subprocess.Popen(
                [self.node, self.server_js],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=self.env,
                text=True,
                bufsize=1,
            )
        except (OSError, ValueError) as e:
            self._proc = None
            raise SimUnavailable(f"cannot spawn sidecar: {e}") from e
        self._q = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        proc = self._proc
        if not proc or not proc.stdout:
            return
        for line in proc.stdout:
            line = line.strip()
            if line:
                self._q.put(line)

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def close(self) -> None:
        if self._proc is not None:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
                self._proc.terminate()
            except OSError:
                pass
            self._proc = None

    # ---- rpc ------------------------------------------------------------ #
    def _send(self, method: str, params: dict) -> dict:
        if not self._alive():
            self._spawn()
        proc = self._proc
        assert proc is not None and proc.stdin is not None
        with self._lock:
            self._next_id += 1
            mid = self._next_id
            try:
                proc.stdin.write(json.dumps({"id": mid, "method": method, "params": params}) + "\n")
                proc.stdin.flush()
            except (OSError, ValueError) as e:
                self.close()
                raise SimUnavailable(f"sidecar write failed: {e}") from e
        # Read until we see our id (responses are in order, but stay robust).
        while True:
            try:
                line = self._q.get(timeout=self.timeout)
            except queue.Empty as e:
                self.close()
                raise SimUnavailable("sidecar timed out") from e
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") != mid:
                continue
            if msg.get("error"):
                raise SimUnavailable(str(msg["error"].get("message", msg["error"])))
            return msg.get("result")

    def available(self) -> bool:
        """True if the sidecar spawns and answers a ping."""
        try:
            return self._send("ping", {}) == "pong"
        except SimUnavailable:
            return False

    def forecast(self, forecast_input: dict) -> dict:
        """Run one headless forecast; raises :class:`SimUnavailable` on any failure."""
        result = self._send("forecast", forecast_input)
        if not isinstance(result, dict):
            raise SimUnavailable("sidecar returned no result")
        return result


_bridge: SimBridge | None = None


def get_bridge() -> SimBridge:
    """Process-wide singleton bridge."""
    global _bridge
    if _bridge is None:
        _bridge = SimBridge()
    return _bridge


def forecast(forecast_input: dict) -> dict:
    """Convenience: forecast via the singleton bridge."""
    return get_bridge().forecast(forecast_input)
