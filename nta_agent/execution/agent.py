"""The agent loop: observe -> decide -> act, over a live :class:`GameSession`.

This is the deterministic "hands" runtime. Each tick it keeps :class:`GameState`
current from server pushes, then lets the :class:`RuleEngine` act. It is built to
run unattended: transient connection drops trigger ``session.recover()`` with
backoff; only a broken token chain with no refresher is fatal. The LLM brain is
not wired here yet; it will sit between observe and the rules.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from nta_agent.execution.actions import Actions
from nta_agent.execution.captcha import CaptchaRequired
from nta_agent.execution.heuristics import RuleEngine
from nta_agent.io.api.client import ApiError, NotConnected, is_session_error
from nta_agent.io.api.session import GameSession, TokenChainBroken

# Errors that mean "connection/session is stale" — recoverable by reconnecting.
_TRANSIENT = (NotConnected, TimeoutError, ConnectionError, OSError)


@dataclass
class Agent:
    session: GameSession
    engine: RuleEngine = field(default_factory=RuleEngine.default)
    actions: Actions = field(init=False)
    max_backoff: float = 60.0
    on_event: callable | None = None  # on_event(kind, detail) for logging
    captcha: object = None  # a CaptchaSolver (or None): solves ANTI_CHEAT challenges
    health: object = None   # a HealthMonitor (or None): F1 proactive staleness recovery

    def __post_init__(self):
        self.actions = Actions(self.session)

    def _emit(self, kind: str, detail: object = "") -> None:
        if self.on_event:
            self.on_event(kind, detail)

    def tick(self) -> list[str]:
        """One observe->decide->act cycle. Returns the rules that fired."""
        self.session.sync()  # apply pending pushes into state
        try:
            return self.engine.tick(self.session.state, self.actions)
        except CaptchaRequired as e:
            if self.captcha is not None:
                res = self.captcha.solve()
                self._emit("captcha_solved" if res.get("rst") else "captcha_failed", res)
                return ["captcha_solved"]
            self._emit("captcha_detected", str(e))
            return ["captcha_detected"]

    def _recover(self) -> None:
        """Reconnect with exponential backoff (+jitter) until the session is live."""
        delay = 2.0
        while True:
            try:
                self.session.recover()
                if self.health is not None:
                    self.health.note_recover_ok()
                self._emit("recovered")
                return
            except TokenChainBroken:
                raise  # unrecoverable without a fresh token — let run() surface it
            except _TRANSIENT + (ApiError,) as e:
                if self.health is not None:
                    self.health.note_recover_fail()
                self._emit("recover_retry", e)
                time.sleep(delay + random.uniform(0, delay * 0.1))  # jitter
                delay = min(delay * 2, self.max_backoff)

    def _probe(self) -> bool:
        """Actively test the connection with a cheap read. True if it answered."""
        try:
            self.actions.get_marches()  # a successful request touches last_activity
            return True
        except Exception:
            return False

    def _health_check(self) -> bool:
        """F1: catch a silent half-open connection. If the session looks stale, probe
        it; on a failed probe, recover. Returns True if a recovery ran (re-loop)."""
        last = getattr(self.session, "last_activity", None)
        if self.health is None or last is None or not self.health.is_stale(last):
            return False
        if self._probe():
            return False  # probe answered -> connection is alive, activity refreshed
        self._emit("stale_recover",
                   round(self.health.status(last).get("last_activity_age", 0), 1))
        self._recover()
        return True

    def run(self, ticks: int = 0, interval: float = 5.0, on_tick=None, control=None) -> None:
        """Run the loop. ``ticks=0`` means forever; ``interval`` seconds between ticks.

        ``control`` is an optional zero-arg callable returning "run", "pause", or
        "stop": pause keeps the session synced but skips acting; stop ends the loop.

        Raises :class:`TokenChainBroken` if the token chain breaks and no
        ``token_refresher`` is configured on the session.
        """
        i = 0
        while ticks == 0 or i < ticks:
            mode = control() if control else "run"
            if mode == "stop":
                break
            if self._health_check():
                continue  # a silent half-open connection was detected + recovered
            try:
                if mode == "pause":
                    self.session.sync()  # keep state fresh + session alive; do not act
                    fired = []
                else:
                    fired = self.tick()
            except _TRANSIENT as e:
                self._emit("connection_lost", e)
                self._recover()
                continue  # retry the tick immediately after recovery
            except ApiError as e:
                # A session-down ApiError (e.g. "Service(type:game) not found",
                # re-raised from a rule) is recoverable; a real ecode is not.
                if is_session_error(e):
                    self._emit("connection_lost", e)
                    self._recover()
                    continue
                raise
            if on_tick:
                on_tick(i, fired, self.session.state)
            i += 1
            if ticks and i >= ticks:
                break
            time.sleep(interval)
