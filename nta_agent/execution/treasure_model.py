"""Turn a cell's land config into (chest_cost, reward_value); read chest budget.

Lookup per docs/re/treasure-mechanic.md:
  landAttr[land_id].treasures_count = "min,max" chests,
  landAttr[land_id].treasures_lv    = "w1,w2,w3" tier weights (percent),
  reward per tier from treasure.json rows by lv (canonical group).
reward_value is a comparable scalar used only to rank cells.
"""
from __future__ import annotations

from dataclasses import dataclass

_UNLIMITED = 10_000  # free-mode / unobserved-cap sentinel


@dataclass(frozen=True)
class CellLoot:
    chest_cost: int
    reward_value: float


def _avg_reward(treasure_row: dict) -> float:
    total = 0.0
    for chunk in str(treasure_row.get("rewards", "")).split("|"):
        parts = chunk.split(",")
        if len(parts) >= 4:
            try:
                total += (float(parts[2]) + float(parts[3])) / 2
            except ValueError:
                pass
    return total


def _tier_avgs(config) -> dict:
    """Average reward per tier lv (1,2,3), from the first treasure row of each lv."""
    out: dict[int, float] = {}
    for row in config.table("treasure").values():
        lv = int(row.get("lv", 0) or 0)
        if lv and lv not in out:
            out[lv] = _avg_reward(row)
    return out


def cell_loot(land_id: int, config) -> CellLoot:
    la = config.table("landAttr").get(int(land_id))
    if not la:
        return CellLoot(0, 0.0)
    counts = str(la.get("treasures_count", "0,0")).split(",")
    chest_cost = int(counts[-1] or 0)  # upper bound of chest count
    if chest_cost <= 0:
        return CellLoot(0, 0.0)
    weights = [float(w or 0) for w in str(la.get("treasures_lv", "0,0,0")).split(",")]
    tier_avg = _tier_avgs(config)
    per_chest = sum((weights[i] / 100.0) * tier_avg.get(i + 1, 0.0)
                    for i in range(min(3, len(weights))))
    return CellLoot(chest_cost=chest_cost, reward_value=round(per_chest * chest_cost, 2))


def chest_budget(state) -> int:
    """Openable-chest budget: a real state field if present, else unlimited
    sentinel (never block occupy on an unobserved cap — see RE findings)."""
    player = (getattr(state, "raw", None) or {}).get("player", {}) or {}
    cap = player.get("treasureOpenCount")
    return int(cap) if cap is not None else _UNLIMITED
