"""Own-territory model (main city, forts, garrisons) + geometry — Tier A.

Built cheaply from player state fields (no packed-chunk decode). Foundation for
the fort-placement advisor (C2).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Fort:
    index: int
    auto_support: bool


@dataclass
class Territory:
    main_city: int
    forts: list = field(default_factory=list)
    garrisons: list = field(default_factory=list)
    map_width: int = 600

    def pos(self, index: int) -> tuple[int, int]:
        return (index % self.map_width, index // self.map_width)

    def dist(self, a: int, b: int) -> int:
        ax, ay = self.pos(a)
        bx, by = self.pos(b)
        return max(abs(ax - bx), abs(ay - by))  # Chebyshev

    def near_main(self, index: int, radius: int = 6) -> bool:
        return self.dist(self.main_city, index) <= radius

    def nodes(self) -> list:
        return [self.main_city] + [f.index for f in self.forts]


def build_territory(state, map_width: int = 600) -> Territory:
    player = (getattr(state, "raw", None) or {}).get("player", {}) or {}
    main = int(player.get("mainCityIndex", 0) or 0)
    forts = [Fort(index=int(f.get("index", 0)), auto_support=bool(f.get("val")))
             for f in (player.get("fortAutoSupports") or []) if isinstance(f, dict)]
    garrisons = [int(d.get("index", 0)) for d in (player.get("armyDists") or [])
                 if isinstance(d, dict)]
    return Territory(main_city=main, forts=forts, garrisons=garrisons, map_width=map_width)
