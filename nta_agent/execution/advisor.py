"""Sim-advisor: turn the battle predictor from a forecaster into a planner.

Given occupy candidates and the armies that can reach each, evaluate *every*
army with the (sim or stats) predictor and pick the plan that wins with the
lowest predicted loss — instead of only trying the single strongest army. Pure
over an injected ``predict`` callable, so it is testable without the engine.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Recommendation:
    army: dict
    target: int
    prediction: object  # BattlePrediction (win, loss_percent, ...)


@dataclass
class Plan:
    armies: list        # ordered army dicts (selection order)
    target: int
    label: str
    prediction: object  # BattlePrediction, filled by best_plan


def best_plan(candidates, plans_for, predict):
    """Best plan over candidates x candidate orderings.

    ``plans_for(cell_index)`` yields :class:`Plan` objects (prediction unset);
    ``predict(plan)`` returns a BattlePrediction (or None). The winner is the
    winnable plan with the lowest ``loss_percent``; ties break toward fewer
    armies (don't waste troops).
    """
    best = None  # ((loss_percent, n_armies), Plan)
    for c in candidates:
        for plan in plans_for(c.index):
            pred = predict(plan)
            if pred is None or not pred.win:
                continue
            key = (pred.loss_percent, len(plan.armies))
            if best is None or key < best[0]:
                plan.prediction = pred
                best = (key, plan)
    return best[1] if best else None


def best_occupy(
    candidates,
    armies_for: Callable[[int], list[dict]],
    predict: Callable[[dict, object], object],
) -> Recommendation | None:
    """Best (army, target) over all candidates × reachable armies.

    ``armies_for(cell_index)`` returns the armies that can reach that cell;
    ``predict(army, candidate)`` returns a BattlePrediction (or None). The winner
    is the winnable plan with the lowest ``loss_percent``.
    """
    best: tuple[float, Recommendation] | None = None
    for c in candidates:
        for army in armies_for(c.index):
            if not army.get("pawns"):
                continue
            pred = predict(army, c)
            if pred is None or not pred.win:
                continue
            if best is None or pred.loss_percent < best[0]:
                best = (pred.loss_percent, Recommendation(army=army, target=c.index, prediction=pred))
    return best[1] if best else None
