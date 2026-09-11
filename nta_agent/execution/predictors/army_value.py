"""Config-driven army value — a faithful port of the client's calculateArmysValue.

The game estimates battle losses from an army's *invested value*: for each pawn,
the cumulative recruit + per-level upgrade cost (``getPawnCost(id, 0..lv)``),
weighted per resource type. This computes the same from the extracted config
tables (pawnBase.drill_cost for lv0, pawnAttr.lv_cost for higher levels), giving
the battle predictor a real power measure instead of the hp/lv proxy.

Fidelity notes: the client overrides the *cereal* component with
``PAWN_COST_LV_LIST[lv] * pawnCostMap[id]`` (a server value) and applies a value
weight map ``m``; here cereal comes from the static cost and weights default to 1
per resource. For a *ratio* of two armies these common factors largely cancel,
so this is a strong estimate; wire the server pawnCostMap / weights later to
match the client exactly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from nta_agent.data.config import GameConfig, parse_cost

# CType codes -> resource names (1=cereal, 2=timber, 3=stone); others ignored by default.
_DEFAULT_WEIGHTS = {"cereal": 1.0, "timber": 1.0, "stone": 1.0}


@dataclass
class PawnValuer:
    config: GameConfig
    weights: dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_WEIGHTS))

    def pawn_cost(self, pawn_id: int, level: int) -> dict[str, int]:
        """Cumulative cost to build a pawn up to ``level`` (lv0 recruit + upgrades)."""
        total: dict[str, int] = {}
        base = self.config.pawn_base(pawn_id) or {}
        for res, amt in parse_cost(base.get("drill_cost", "")).items():
            total[res] = total.get(res, 0) + amt
        attr = self.config.table("pawnAttr")
        for lv in range(1, level + 1):
            row = attr.get(pawn_id * 1000 + lv)
            if not row:
                continue
            for res, amt in parse_cost(row.get("lv_cost", "")).items():
                total[res] = total.get(res, 0) + amt
        return total

    def pawn_value(self, pawn: dict) -> float:
        cost = self.pawn_cost(int(pawn.get("id", 0)), int(pawn.get("lv", 0) or 0))
        return float(sum(self.weights.get(res, 0.0) * amt for res, amt in cost.items()))

    def army_value(self, pawns: list[dict]) -> float:
        return sum(self.pawn_value(p) for p in pawns or [])


def config_pawn_power(config: GameConfig | None = None, weights: dict[str, float] | None = None):
    """Return a pawn_power(pawn) callable backed by config value (for BattlePredictor)."""
    valuer = PawnValuer(config or GameConfig.load(), weights or dict(_DEFAULT_WEIGHTS))
    return valuer.pawn_value
