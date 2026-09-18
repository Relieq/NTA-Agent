"""Decide whether occupying a resource cell is worth it.

Pure/\u200btestable scoring that combines the battle prediction (win + expected loss),
the cell's resource yield (``land`` config), and its stamina cost (``landAttr``).
Target *discovery* (which cells exist near me) is separate — this evaluates a
candidate once its land id and defenders are known.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from nta_agent.data.config import GameConfig
from nta_agent.execution.predictors.battle import BattlePrediction

MAP_WIDTH = 600  # newbie map is 600x600; index = y*MAP_WIDTH + x


@dataclass
class Candidate:
    index: int
    defenders: list[dict]      # enemy pawns guarding the cell
    hp: tuple[int, int]        # cell durability (proxy for difficulty)
    land_id: int = 0           # land type (for the sim's config-based enemy gen)
    owned_neighbors: int = 0   # # of 4-neighbours already owned (expansion presets)


def discover_targets(
    get_area: Callable[[int], dict],
    center_index: int,
    radius: int,
    my_uid: str,
    map_width: int = MAP_WIDTH,
) -> list[Candidate]:
    """Probe a square radius for occupiable cells **adjacent to owned territory**.

    The server only allows attacking cells that adjoin a cell you own
    (ONLY_ATTACK_ADJOIN_CELL). So we probe once, note owned vs occupiable cells,
    and return occupiable cells with an 8-neighbour we own. One GetAreaInfo per
    probed cell — no packed-chunk decoding.
    """
    cx, cy = center_index % map_width, center_index // map_width
    owned: set[int] = set()
    occupiable: list[Candidate] = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            idx = (cy + dy) * map_width + (cx + dx)
            try:
                area = get_area(idx) or {}
            except Exception:
                area = {}  # unreachable/fogged/forbidden cell (ecode.500000) -> skip below
            if str(area.get("owner", "")) == my_uid:
                owned.add(idx)
                continue
            if area.get("cityId"):
                continue  # someone else's city
            pawns = [p for g in area.get("armys", []) or [] for p in g.get("pawns", []) or []]
            if pawns:
                hp = area.get("hp") or [0, 0]
                occupiable.append(Candidate(index=idx, defenders=pawns,
                                            hp=(int(hp[0]), int(hp[-1])),
                                            land_id=int(area.get("landId", 0) or 0)))

    def owned_nbrs(idx: int) -> int:
        # The server allows attacking only orthogonally-adjoining cells (verified live).
        x, y = idx % map_width, idx // map_width
        return sum((y + ny) * map_width + (x + nx) in owned
                   for nx, ny in ((-1, 0), (1, 0), (0, -1), (0, 1)))

    out = []
    for c in occupiable:
        n = owned_nbrs(c.index)
        if n:  # adjoins at least one owned cell
            c.owned_neighbors = n
            out.append(c)
    return out


def land_yield(config: GameConfig, land_id: int) -> dict[str, int]:
    """The per-collection resource yield of a land type (cereal/timber/stone)."""
    row = config.table("land").get(land_id) or {}
    return {r: int(row.get(r, 0) or 0) for r in ("cereal", "timber", "stone") if row.get(r)}


def is_occupiable(config: GameConfig, land_id: int) -> bool:
    row = config.table("land").get(land_id) or {}
    return bool(row.get("occupy"))


def min_occupy_stamina(config: GameConfig) -> int:
    """Cheapest occupy stamina cost across land tiers (``landAttr``), floor 1.

    Lets ``OccupyCell`` skip discovery when stamina can't afford even the
    cheapest occupy, without hard-coding the cost.
    """
    costs = [int(row.get("need_stamina", 0) or 0)
             for row in config.table("landAttr").values()]
    costs = [c for c in costs if c > 0]
    return min(costs) if costs else 1


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
