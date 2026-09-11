"""Economy predictor — reasons about resource production from live server data.

Needs no static config: it works purely from the live ``value`` and ``opHour``
(per-hour production) the server sends, plus storage caps. It answers the
questions the resource rules and (later) the brain need: how full is each store,
when will it cap, and is production being wasted at the cap.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from nta_agent.state.schema import GameState

# cereal is capped by the granary; timber/stone by the warehouse.
_CAP_OF = {"cereal": "granary", "timber": "warehouse", "stone": "warehouse"}


@dataclass
class ResourceForecast:
    name: str
    value: int
    rate: int   # per hour
    cap: int

    @property
    def fraction(self) -> float:
        return self.value / self.cap if self.cap > 0 else 0.0

    @property
    def at_cap(self) -> bool:
        return self.cap > 0 and self.value >= self.cap

    @property
    def hours_to_cap(self) -> float:
        if self.rate <= 0 or self.cap <= 0:
            return math.inf
        return max(0.0, (self.cap - self.value) / self.rate)

    @property
    def wasting(self) -> bool:
        """At cap while still producing — that production is lost."""
        return self.at_cap and self.rate > 0


class EconomyPredictor:
    def __init__(self, state: GameState):
        self.state = state

    def _cap(self, name: str) -> int:
        which = _CAP_OF.get(name)
        return self.state.granary_cap if which == "granary" else self.state.warehouse_cap

    def forecasts(self) -> list[ResourceForecast]:
        r = self.state.resources
        prod = self.state.production
        return [
            ResourceForecast(name, getattr(r, name), int(prod.get(name, 0)), self._cap(name))
            for name in ("cereal", "timber", "stone")
        ]

    def should_collect(self, at: float = 0.85) -> bool:
        """True if any store is at/over ``at`` of its cap (worth collecting)."""
        return any(f.cap > 0 and f.fraction >= at for f in self.forecasts())

    def wasting(self) -> list[str]:
        """Resources whose production is currently being lost at the cap."""
        return [f.name for f in self.forecasts() if f.wasting]

    def soonest_to_cap(self) -> ResourceForecast | None:
        caps = [f for f in self.forecasts() if f.hours_to_cap != math.inf]
        return min(caps, key=lambda f: f.hours_to_cap) if caps else None
