"""The agent loop: observe -> decide -> act, over a live :class:`GameSession`.

This is the deterministic "hands" runtime. It keeps :class:`GameState` current
from server pushes each tick, then lets the :class:`RuleEngine` act. The LLM
brain is not wired here yet; when it is, it will sit between observe and the
rules, emitting high-level intents the rules resolve.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from nta_agent.execution.actions import Actions
from nta_agent.execution.heuristics import RuleEngine
from nta_agent.io.api.session import GameSession


@dataclass
class Agent:
    session: GameSession
    engine: RuleEngine = field(default_factory=RuleEngine.default)
    actions: Actions = field(init=False)

    def __post_init__(self):
        self.actions = Actions(self.session)

    def tick(self) -> list[str]:
        """One observe->decide->act cycle. Returns the rules that fired."""
        self.session.sync()  # apply pending pushes into state
        return self.engine.tick(self.session.state, self.actions)

    def run(self, ticks: int = 0, interval: float = 5.0, on_tick=None) -> None:
        """Run the loop. ``ticks=0`` means forever; ``interval`` seconds between ticks."""
        i = 0
        while ticks == 0 or i < ticks:
            fired = self.tick()
            if on_tick:
                on_tick(i, fired, self.session.state)
            i += 1
            if ticks and i >= ticks:
                break
            time.sleep(interval)
