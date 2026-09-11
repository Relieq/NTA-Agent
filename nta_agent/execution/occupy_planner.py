"""Decide whether occupying a resource cell is worth it.

Pure/\u200btestable scoring that combines the battle prediction (win + expected loss),
the cell's resource yield (``land`` config), and its stamina cost (``landAttr``).
Target *discovery* (which cells exist near me) is separate — this evaluates a
candidate once its land id and defenders are known.
"""
from __future__ import annotations

from dataclasses import dataclass

from nta_agent.data.config import GameConfig
from nta_agent.execution.predictors.battle import BattlePrediction


def land_yield(config: GameConfig, land_id: int) -> dict[str, int]:
    """The per-collection resource yield of a land type (cereal/timber/stone)."""
    row = config.table("land").get(land_id) or {}
    return {r: int(row.get(r, 0) or 0) for r in ("cereal", "timber", "stone") if row.get(r)}


def is_occupiable(config: GameConfig, land_id: int) -> bool:
    row = config.table("land").get(land_id) or {}
    return bool(row.get("occupy"))


@dataclass
class TargetEval:
    target: int
    ok: bool               # winnable, affordable stamina, has yield
    score: float           # higher = better; 0 when not ok
    prediction: BattlePrediction
    yield_total: int
    need_stamina: int
    reason: str = ""


def evaluate_target(
    target: int,
    prediction: BattlePrediction,
    yield_dict: dict[str, int],
    need_stamina: int,
    available_stamina: int,
) -> TargetEval:
    """Score a candidate: require a win + enough stamina; prefer yield, punish loss."""
    yield_total = sum(yield_dict.values())
    reason = ""
    ok = True
    if not prediction.win:
        ok, reason = False, "would lose"
    elif need_stamina > available_stamina:
        ok, reason = False, "not enough stamina"
    elif yield_total <= 0:
        ok, reason = False, "no yield"
    # Prefer high yield and low losses; +1 keeps it finite at 0% loss.
    score = 0.0 if not ok else yield_total / (1.0 + prediction.loss_percent / 100.0)
    return TargetEval(
        target=target, ok=ok, score=score, prediction=prediction,
        yield_total=yield_total, need_stamina=need_stamina, reason=reason,
    )
