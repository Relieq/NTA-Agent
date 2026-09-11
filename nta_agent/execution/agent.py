"""The agent loop: observe -> decide -> act, over a live :class:`GameSession`.

This is the deterministic "hands" runtime. Each tick it keeps :class:`GameState`
current from server pushes, then lets the :class:`RuleEngine` act. It is built to
run unattended: transient connection drops trigger ``session.recover()`` with
backoff; only a broken token chain with no refresher is fatal. The LLM brain is
not wired here yet; it will sit between observe and the rules.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from nta_agent.execution.actions import Actions
from nta_agent.execution.heuristics import RuleEngine
from nta_agent.io.api.client import ApiError, NotConnected
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

    def __post_init__(self):
        self.actions = Actions(self.session)

    def _emit(self, kind: str, detail: object = "") -> None:
        if self.on_event:
            self.on_event(kind, detail)

    def tick(self) -> list[str]:
        """One observe->decide->act cycle. Returns the rules that fired."""
        self.session.sync()  # apply pending pushes into state
        return self.engine.tick(self.session.state, self.actions)

    def _recover(self) -> None:
        """Reconnect with exponential backoff until the session is live again."""
        delay = 2.0
        while True:
            try:
                self.session.recover()
                self._emit("recovered")
                return
            except TokenChainBroken:
                raise  # unrecoverable without a fresh token — let run() surface it
            except _TRANSIENT + (ApiError,) as e:
                self._emit("recover_retry", e)
                time.sleep(delay)
                delay = min(delay * 2, self.max_backoff)

    def run(self, ticks: int = 0, interval: float = 5.0, on_tick=None) -> None:
        """Run the loop. ``ticks=0`` means forever; ``interval`` seconds between ticks.

        Raises :class:`TokenChainBroken` if the token chain breaks and no
        ``token_refresher`` is configured on the session.
        """
        i = 0
        while ticks == 0 or i < ticks:
            try:
                fired = self.tick()
            except _TRANSIENT as e:
                self._emit("connection_lost", e)
                self._recover()
                continue  # retry the tick immediately after recovery
            if on_tick:
                on_tick(i, fired, self.session.state)
            i += 1
            if ticks and i >= ticks:
                break
            time.sleep(interval)
