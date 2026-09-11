"""Combat-stat army power — a more accurate battle model than resource value.

Resource value (calculateArmysValue) tracks *investment*, not fighting strength.
A cheap-but-deadly unit or a tanky one is mispriced. This model scores a pawn by
its actual combat stats from ``pawnAttr`` — effective power ≈ survivability ×
damage output (``hp * attack``), optionally scaled by attack speed.

It is intentionally a scalar power proxy, not a full battle simulation. It is
structured so more factors (type counters, skills/buffs, hero bonuses, ranges)
can be layered on ``pawn_power`` later without changing callers.
"""
from __future__ import annotations

from dataclasses import dataclass

from nta_agent.data.config import GameConfig


@dataclass
class StatValuer:
    config: GameConfig
    use_speed: bool = False  # if True, weight by attack rate (attack_speed as interval)

    def _attr(self, pawn_id: int, level: int) -> dict:
        # pawnAttr is keyed id*1000+lv; pawns are effectively >=lv1 in combat.
        return self.config.table("pawnAttr").get(pawn_id * 1000 + max(level, 1)) or {}

    def pawn_power(self, pawn: dict) -> float:
        attr = self._attr(int(pawn.get("id", 0)), int(pawn.get("lv", 0) or 0))
        hp = float(attr.get("hp", 0) or 0)
        atk = float(attr.get("attack", 0) or 0)
        power = hp * atk  # survivability x damage
        if self.use_speed:
            # attack_speed is an interval (lower = faster); guard against 0.
            interval = float(attr.get("attack_speed", 0) or 0)
            if interval > 0:
                power /= interval
        return power

    def army_power(self, pawns: list[dict]) -> float:
        return sum(self.pawn_power(p) for p in pawns or [])


def stat_pawn_power(config: GameConfig | None = None, use_speed: bool = False):
    """Return a pawn_power(pawn) callable backed by combat stats (for BattlePredictor)."""
    return StatValuer(config or GameConfig.load(), use_speed=use_speed).pawn_power
