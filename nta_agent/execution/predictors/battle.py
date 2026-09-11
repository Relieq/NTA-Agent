"""Battle predictor (heuristic) — estimate an occupy/attack outcome, pure-API.

The game has no server-side battle forecast: it runs a full client-side battle
engine. Until that engine is ported (the accurate path, "A"), this heuristic
compares army "power" the way the game's own loss estimate does in spirit — via
an army-value ratio — but from the stats available on the wire (AreaPawnInfo:
lv, hp), since the game's exact ``calculateArmysValue`` needs the cost config.

``pawn_power`` is pluggable so the model can be swapped for the real formula
later without changing callers.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


# Loss tiers mirror the client's lossLv buckets (by loss percent).
def _loss_lv(loss_pct: float) -> int:
    if loss_pct <= 15:
        return 1
    if loss_pct < 50:
        return 2
    if loss_pct < 100:
        return 3
    return 4


def default_pawn_power(pawn: dict[str, Any]) -> float:
    """A transparent power proxy from wire stats: prefer hp, fall back to level.

    hp is the most direct combat signal; when absent, a pawn's level stands in
    (a lv-5 pawn counts ~6x a lv-0). Replace this with the ported cost-based
    ``calculateArmysValue`` when the config tables are extracted.
    """
    hp = pawn.get("hp")
    if isinstance(hp, (list, tuple)) and hp:
        hp = hp[-1]  # [cur, max] -> max
    if isinstance(hp, (int, float)) and hp > 0:
        return float(hp)
    return 1.0 + float(pawn.get("lv", 0) or 0)


@dataclass
class BattlePrediction:
    win: bool
    my_power: float
    enemy_power: float
    ratio: float          # my_power / enemy_power (inf if no enemy)
    loss_percent: float   # estimated % of our power lost
    loss_lv: int          # 1..4, mirrors the client's tiers


@dataclass
class BattlePredictor:
    pawn_power: Callable[[dict], float] = default_pawn_power
    win_margin: float = 1.0  # need my_power >= enemy_power * win_margin to expect a win

    @classmethod
    def from_config(cls, config=None, weights=None, win_margin: float = 1.0) -> BattlePredictor:
        """A predictor whose power is the config-driven army value (calculateArmysValue)."""
        from nta_agent.execution.predictors.army_value import config_pawn_power
        return cls(pawn_power=config_pawn_power(config, weights), win_margin=win_margin)

    @classmethod
    def from_stats(cls, config=None, win_margin: float = 1.5, use_speed: bool = False) -> BattlePredictor:
        """A predictor whose power is combat stats (hp*attack) — more accurate than value.

        Defaults to a 1.5x margin: predictions are approximate, so only attack when
        clearly stronger.
        """
        from nta_agent.execution.predictors.combat import stat_pawn_power
        return cls(pawn_power=stat_pawn_power(config, use_speed), win_margin=win_margin)

    def army_power(self, pawns: list[dict]) -> float:
        return sum(self.pawn_power(p) for p in pawns or [])

    def predict(self, my_pawns: list[dict], enemy_pawns: list[dict]) -> BattlePrediction:
        mine = self.army_power(my_pawns)
        enemy = self.army_power(enemy_pawns)
        ratio = mine / enemy if enemy > 0 else float("inf")
        win = mine >= enemy * self.win_margin
        # Loss grows as the enemy's relative power rises; ~0 when we vastly outmatch.
        loss_percent = 0.0 if mine <= 0 else max(0.0, min(100.0 * enemy / mine, 200.0))
        return BattlePrediction(
            win=win, my_power=mine, enemy_power=enemy, ratio=ratio,
            loss_percent=loss_percent, loss_lv=_loss_lv(loss_percent),
        )


def enemy_pawns_of_area(area: dict[str, Any], my_uid: str = "") -> list[dict]:
    """Flatten the hostile pawns of an AreaInfo (armys not owned by me / unowned)."""
    out: list[dict] = []
    for army in area.get("armys", []) or []:
        owner = str(army.get("owner", ""))
        if owner and owner == my_uid:
            continue  # my own army stationed there
        out.extend(army.get("pawns", []) or [])
    return out
