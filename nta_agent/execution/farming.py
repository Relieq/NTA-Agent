"""Pick which resource cells to occupy: winnable (<=max_loss), highest loot per
chest, within the chest budget. Pure over an injected predict + loot lookup."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FarmPick:
    cell: object
    plan: object
    loot: object


def plan_farm(candidates, predict, loot_of, *, budget, max_loss,
              min_reward_per_chest=0.0, max_march_ms=0, march_of=None):
    """Return FarmPicks ordered best-first, greedily filling the chest budget.

    ``predict(cell)`` -> a winnable Plan (``.prediction.win``/``.loss_percent``,
    ``.armies``) or None; ``loot_of(cell)`` -> CellLoot.
    """
    scored = []
    for c in candidates:
        if max_march_ms and march_of and march_of(c) > max_march_ms:
            continue
        loot = loot_of(c)
        if loot.chest_cost <= 0:
            continue
        per = loot.reward_value / loot.chest_cost
        if per < min_reward_per_chest:
            continue
        plan = predict(c)
        if plan is None or not plan.prediction.win or plan.prediction.loss_percent > max_loss:
            continue
        scored.append((per, loot, plan, c))
    scored.sort(key=lambda t: t[0], reverse=True)  # best reward/chest first
    picks, spent = [], 0
    for _per, loot, plan, c in scored:
        if spent + loot.chest_cost > budget:
            continue
        picks.append(FarmPick(cell=c, plan=plan, loot=loot))
        spent += loot.chest_cost
    return picks
