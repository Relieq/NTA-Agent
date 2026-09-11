"""Deterministic rule engine — the "hands" decide without spending LLM tokens.

A :class:`Rule` inspects :class:`GameState` and, when it applies, performs one
action via :class:`Actions`. The :class:`RuleEngine` runs every applicable rule
per tick (rules must be idempotent). Strategy-level choices (which build order,
whom to attack) belong to the brain, not here — these rules are the routine
housekeeping that keeps the account ticking over.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class Rule(Protocol):
    name: str

    def applies(self, state: GameState) -> bool: ...
    def act(self, actions: Actions) -> None: ...


def _caps(state: GameState) -> tuple[int, int]:
    """(granaryCap, warehouseCap) from the live player block; 0 if unknown."""
    player = (state.raw or {}).get("player") or {}
    return int(player.get("granaryCap", 0) or 0), int(player.get("warehouseCap", 0) or 0)


@dataclass
class CollectCityOutput:
    """Collect the main city's output while storage has room for it.

    Safe and always beneficial; skipped when storage is at cap (the server would
    reject it anyway) to avoid pointless requests.
    """
    name: str = "collect_city_output"

    def applies(self, state: GameState) -> bool:
        granary, warehouse = _caps(state)
        if not (granary or warehouse):
            return False  # caps unknown -> don't guess
        r = state.resources
        return (
            (granary and r.cereal < granary)
            or (warehouse and r.timber < warehouse)
            or (warehouse and r.stone < warehouse)
        )

    def act(self, actions: Actions) -> None:
        actions.collect_city_output()


@dataclass
class RuleEngine:
    rules: list[Rule]

    def tick(self, state: GameState, actions: Actions) -> list[str]:
        """Run every applicable rule once; return the names that fired."""
        fired: list[str] = []
        for rule in self.rules:
            try:
                if rule.applies(state):
                    rule.act(actions)
                    fired.append(rule.name)
            except Exception as e:  # a failing rule must not kill the loop
                fired.append(f"{rule.name}!ERR:{type(e).__name__}")
        return fired

    @classmethod
    def default(cls) -> RuleEngine:
        return cls(rules=[CollectCityOutput()])
