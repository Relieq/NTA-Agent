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

    def applies(self, state: GameState, actions: Actions) -> bool: ...
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

    def applies(self, state: GameState, actions: Actions) -> bool:
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

    def applies(self, state: GameState, actions: Actions) -> bool:
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
class OccupyCell:
    """Occupy a nearby resource cell the agent can win, spending stamina for loot.

    Discovers candidates around the main city (GetAreaInfo probe), predicts each
    with battle-A, and sends the strongest garrison army at the lowest-loss win.
    Discovery is throttled (it costs one request per probed cell).
    """
    name: str = "occupy_cell"
    radius: int = 2
    min_stamina: int = 1
    discover_every: int = 8   # ticks between discovery sweeps
    fail_cooldown: int = 8
    predictor: object = None
    _pending: object = None    # (army_dict, target_index)
    _cooldown: int = 0

    def _pred(self):
        if self.predictor is None:
            from nta_agent.execution.predictors.battle import BattlePredictor
            try:
                self.predictor = BattlePredictor.from_config()
            except FileNotFoundError:
                self.predictor = BattlePredictor()
        return self.predictor

    @staticmethod
    def _best_army(armies: list[dict], pawn_power) -> dict | None:
        # select_armies already returns only armies that can reach the target, so
        # just take the strongest one that has pawns.
        ready = [a for a in armies if a.get("pawns")]
        if not ready:
            return None
        return max(ready, key=lambda a: sum(pawn_power(p) for p in a["pawns"]))

    def applies(self, state: GameState, actions: Actions) -> bool:
        if state.resources.stamina < self.min_stamina or not state.main_city_index:
            return False
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        from nta_agent.execution.occupy_planner import discover_targets
        cands = discover_targets(
            lambda i: actions.get_area(i).get("data", {}),
            state.main_city_index, self.radius, state.user.uid,
        )
        self._cooldown = self.discover_every  # throttle regardless of outcome
        predictor = self._pred()
        # For each candidate, ask the server which of our armies can reach it, then
        # keep the winnable ones. Pick the safest (lowest predicted loss).
        viable = []
        for c in cands:
            army = self._best_army(actions.select_armies(c.index), predictor.pawn_power)
            if not army:
                continue
            pred = predictor.predict(army["pawns"], c.defenders)
            if pred.win:
                viable.append((pred.loss_percent, c.index, army))
        if not viable:
            return False
        _loss, target, army = min(viable, key=lambda v: v[0])
        self._pending = (army, target)
        return True

    def act(self, actions: Actions) -> None:
        if not self._pending:
            return
        army, target = self._pending
        self._pending = None
        try:
            actions.occupy_cell(target, [army])
        except Exception:
            self._cooldown = self.fail_cooldown
            raise


@dataclass
class RuleEngine:
    rules: list[Rule]

    def tick(self, state: GameState, actions: Actions) -> list[str]:
        """Run every applicable rule once; return the names that fired."""
        fired: list[str] = []
        for rule in self.rules:
            try:
                if rule.applies(state, actions):
                    rule.act(actions)
                    fired.append(rule.name)
            except Exception as e:  # a failing rule must not kill the loop
                detail = str(e).split(":")[-1].strip() or type(e).__name__
                fired.append(f"{rule.name}!ERR:{detail}")
        return fired

    @classmethod
    def default(cls) -> RuleEngine:
        return cls(rules=[CollectCityOutput(), BuildOrder(), OccupyCell()])
