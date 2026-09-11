"""Deterministic rule engine — the "hands" decide without spending LLM tokens.

A :class:`Rule` inspects :class:`GameState` and, when it applies, performs one
action via :class:`Actions`. The :class:`RuleEngine` runs every applicable rule
per tick (rules must be idempotent). Strategy-level choices (which build order,
whom to attack) belong to the brain, not here — these rules are the routine
housekeeping that keeps the account ticking over.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
    fail_cooldown: int = 20  # ticks to wait after a rejection before retrying
    _cooldown: int = 0

    def applies(self, state: GameState) -> bool:
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        # Collect only when storage has room; at cap the server rejects it and the
        # gathered output would overflow anyway.
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
        try:
            actions.collect_city_output()
        except Exception:
            self._cooldown = self.fail_cooldown  # back off, then surface the error
            raise


@dataclass
class BuildOrder:
    """Upgrade buildings along a priority order, respecting prereqs and cost.

    ``sequence`` is a list of build ids in priority order (like the old fixed
    build order); when None, all owned buildings are considered lowest-id first.
    Needs the config tables; if they're absent the rule simply never applies.
    """
    name: str = "build_order"
    sequence: list[int] | None = None
    config: object | None = None
    _pending: object = None  # (Building, BuildUpgrade) chosen in applies()
    _blocked: set = field(default_factory=set)  # (uid, target_lv) the server rejected
    _sig: tuple = ()  # last builds signature; changing it clears blocks (retry)

    def _cfg(self):
        if self.config is None:
            from nta_agent.data.config import GameConfig
            try:
                self.config = GameConfig.load()
            except FileNotFoundError:
                self.config = False  # sentinel: unavailable
        return self.config or None

    def applies(self, state: GameState) -> bool:
        cfg = self._cfg()
        if not cfg:
            return False
        # When any building level changes, retry previously-blocked steps.
        sig = tuple(sorted((b.uid, b.lv) for b in state.builds))
        if sig != self._sig:
            self._sig = sig
            self._blocked.clear()
        from nta_agent.execution.build_planner import next_upgrade
        self._pending = next_upgrade(state, cfg, self.sequence, self._blocked)
        return self._pending is not None

    def act(self, actions: Actions) -> None:
        if not self._pending:
            return
        build, up = self._pending
        self._pending = None
        try:
            actions.upgrade_build(build.index, uid=build.uid)
        except Exception:
            # Server rejected (a condition we can't verify locally) — back off this
            # exact step until the situation changes, and surface the error.
            self._blocked.add((build.uid, up.level))
            raise


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
                detail = str(e).split(":")[-1].strip() or type(e).__name__
                fired.append(f"{rule.name}!ERR:{detail}")
        return fired

    @classmethod
    def default(cls) -> RuleEngine:
        return cls(rules=[CollectCityOutput(), BuildOrder()])
