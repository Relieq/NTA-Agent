"""Territory-expansion presets: bias which winnable cell to occupy next.

Two common patterns (user 2026-09-18, see memory nta-agent-strategy):
- **spiral (xoắn ốc):** each new cell touches only ONE owned cell — single-file,
  minimal exposure, easy to wall off when attacked (no protection mode).
- **octopus (bạch tuộc):** reach toward / grab resource-rich (lv5) land fast to
  lock it from the enemy (you can only occupy adjacent cells).
- **hybrid:** value first, then low exposure.

Pure ranking over already-discovered candidates; the caller still enforces
winnability/budget. `owned_neighbors` = how many 4-neighbours are already owned;
`land_value` = a richness proxy (sum of the cell's resource yield).
"""
from __future__ import annotations

MODES = ("spiral", "octopus", "hybrid")

_NEIGHBORS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def owned_neighbors(index: int, owned: set[int], map_width: int) -> int:
    x, y = index % map_width, index // map_width
    return sum(1 for nx, ny in _NEIGHBORS if (y + ny) * map_width + (x + nx) in owned)


def land_value(config, land_id: int) -> int:
    """Resource richness of a land type (sum of its yield); higher = richer (lv5)."""
    from nta_agent.execution.occupy_planner import land_yield
    try:
        return sum(land_yield(config, land_id).values())
    except Exception:
        return 0


def sort_key(mode: str, *, owned_neighbors: int, land_value: int,
             loss_percent: float) -> tuple:
    """Ranking key for a winnable candidate — lower is preferred."""
    if mode == "spiral":
        return (owned_neighbors, loss_percent)
    if mode == "octopus":
        return (-land_value, loss_percent)
    if mode == "hybrid":
        return (-land_value, owned_neighbors, loss_percent)
    return (loss_percent,)  # unknown mode -> safest win
