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
            pawns = _hostile_pawns(area, my_uid)
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


def discover_frontier(
    get_area: Callable[[int], dict],
    frontier,
    my_uid: str,
    map_width: int = MAP_WIDTH,
) -> list[Candidate]:
    """Build occupiable Candidates from a precomputed FRONTIER set (unclaimed cells
    orthogonally adjacent to owned — from ``territory.scan_map`` over map chunks).

    Follows the owned frontier as territory grows (no fixed radius) and only probes
    the frontier cells themselves. Keeps defended, non-city, unowned cells (wild
    "Đất Hoang" is NPC-guarded); each is adjacent to owned by construction.
    """
    out: list[Candidate] = []
    for idx in frontier or ():
        try:
            area = get_area(int(idx)) or {}
        except Exception:
            area = {}  # unreachable/fogged cell -> falls through the checks below
        if str(area.get("owner", "")) == my_uid or area.get("cityId"):
            continue
        pawns = _hostile_pawns(area, my_uid)
        if not pawns:
            continue  # empty/impassable frontier cell -> not an occupy target
        hp = area.get("hp") or [0, 0]
        out.append(Candidate(index=int(idx), defenders=pawns,
                             hp=(int(hp[0]), int(hp[-1])),
                             land_id=int(area.get("landId", 0) or 0), owned_neighbors=1))
    return out


def _hostile_pawns(area: dict, my_uid: str) -> list[dict]:
    """The pawns guarding a cell — NOT my own armies standing or fighting there (live
    2026-09-25: 26 of 27 'defenders' were ours, so the sim fought copies of our armies
    until it timed out)."""
    from nta_agent.execution.predictors.battle import enemy_pawns_of_area
    return enemy_pawns_of_area(area, str(my_uid))


def discover_around(
    get_area: Callable[[int], dict],
    centers,
    radius: int,
    my_uid: str,
    map_width: int = MAP_WIDTH,
) -> list[Candidate]:
    """Discover occupiable cells around SEVERAL centers in one deduped probe pass.

    Occupy needs an army on a cell orthogonally adjacent to the target, so the
    reachable targets sit next to where armies already are — probe around the city
    AND each idle army, not just the city. Each map cell is fetched at most once.
    """
    centers = {int(c) for c in centers if c}
    probe: set[int] = set()
    for ctr in centers:
        cx, cy = ctr % map_width, ctr // map_width
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                probe.add((cy + dy) * map_width + (cx + dx))

    owned: set[int] = set()
    occupiable: list[Candidate] = []
    for idx in probe:
        try:
            area = get_area(idx) or {}
        except Exception:
            area = {}
        if str(area.get("owner", "")) == my_uid:
            owned.add(idx)
            continue
        if area.get("cityId"):
            continue
        pawns = _hostile_pawns(area, my_uid)
        if pawns:
            hp = area.get("hp") or [0, 0]
            occupiable.append(Candidate(index=idx, defenders=pawns,
                                        hp=(int(hp[0]), int(hp[-1])),
                                        land_id=int(area.get("landId", 0) or 0)))

    def owned_nbrs(idx: int) -> int:
        x, y = idx % map_width, idx // map_width
        return sum((y + ny) * map_width + (x + nx) in owned
                   for nx, ny in ((-1, 0), (1, 0), (0, -1), (0, 1)))

    out = []
    for c in occupiable:
        n = owned_nbrs(c.index)
        if n:
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


def plan_rally(idle_group, city, target_indices, evaluate, max_loss=0.0):
    """Decide whether to consolidate scattered idle group armies at the city.

    Occupy attacks only with co-located armies (scattered origins arrive in
    staggered waves and lose pawns). When no single/co-located force wins a
    frontier cell, but the FULL idle group — once rallied together at the city —
    WOULD win one at ``<= max_loss``, this returns ``(armies_to_move,
    target_index)`` so the caller marches the not-yet-home armies home; a
    co-located attack from the city can then follow. Returns ``None`` when there
    is nothing to consolidate or the combined force still can't win.

    ``evaluate(armies, target_index)`` predicts the battle for ``armies`` already
    re-based to the city; it returns an object with ``.win`` and
    ``.loss_percent`` (or ``None``).
    """
    idle_group = list(idle_group or [])
    if len(idle_group) < 2:
        return None  # a lone army is already the single-army case
    scattered = [a for a in idle_group if int(a.get("index", 0) or 0) != city]
    if not scattered:
        return None  # already all home -> a co-located plan should have been found
    combined = [{**a, "index": city} for a in idle_group]
    for t in target_indices:
        pred = evaluate(combined, t)
        if (pred is not None and getattr(pred, "win", False)
                and getattr(pred, "loss_percent", 100.0) <= max_loss):
            return (scattered, t)
    return None


def _manhattan(a: int, b: int, width: int = MAP_WIDTH) -> int:
    return abs(a % width - b % width) + abs(a // width - b // width)


def bridge_hop(launch: int, target: int, owned, zone_centers, *, radius: int = 6,
               width: int = MAP_WIDTH, min_gain: int = 2):
    """Pick a forward owned cell to relay through before attacking a FAR target.

    March speed is only boosted between two speed-zone cells (engine
    ``isCanUpSpeed``: both endpoints must be zone cells). A direct march to a
    target OUTSIDE the zone gets no boost over its full (long) distance. Staging
    at the in-zone owned cell NEAREST the target — reached by a fast in-zone
    march — then hopping the short remaining distance is faster. Forts extend the
    zone, so late game the target is already in-zone and no hop is needed.

    ``zone_centers`` are cell indices whose ``radius`` (Manhattan) neighbourhood
    is the speed zone (the main-city block corners + forts). Returns the staging
    cell index, or ``None`` when attacking directly from ``launch`` is already
    best (target near/in the zone, or no closer in-zone owned cell).
    """
    owned = {int(c) for c in owned}
    centers = [int(c) for c in zone_centers]
    if not centers:
        return None

    def in_zone(cell: int) -> bool:
        return any(_manhattan(cell, c, width) <= radius for c in centers)

    direct = _manhattan(launch, target, width)
    if direct <= radius or in_zone(target):
        return None  # target is near/in the zone already — a direct march is fine
    # the in-zone owned cell closest to the target (must be closer than launch is)
    best, best_d = None, _manhattan(launch, target, width)
    for cell in owned:
        if cell == launch or not in_zone(cell):
            continue
        d = _manhattan(cell, target, width)
        if d < best_d:
            best, best_d = cell, d
    # only worth a relay if it shortens the final (un-boosted) hop meaningfully
    if best is not None and (direct - best_d) >= min_gain:
        return best
    return None


def full_hp_pawns(pawns):
    """Copy pawns with hp restored to full (cur = max) — to simulate 'if healed'.
    Handles hp shapes {0:cur,1:max}/{"0":..}/[cur,max]."""
    out = []
    for p in pawns or []:
        q = dict(p)
        hp = p.get("hp")
        mx = None
        if isinstance(hp, dict):
            mx = hp.get(1, hp.get("1"))
        elif isinstance(hp, (list, tuple)) and len(hp) > 1:
            mx = hp[-1]
        if mx is not None:
            q["hp"] = [int(mx), int(mx)]
        out.append(q)
    return out


def _seg_point_dist(px, py, ax, ay, bx, by) -> float:
    """Euclidean distance from point (px,py) to segment (ax,ay)-(bx,by)."""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def heal_convenient(army_index, target, heal_nodes, *, radius: int = 4,
                    path_margin: float = 1.5, map_width: int = MAP_WIDTH) -> bool:
    """'Tiện đường' to heal: the army is within ``radius`` cells (Manhattan) of a
    heal node, OR its straight route to ``target`` passes within ``path_margin``
    of one (i.e. it goes through/near the main city or a fort)."""
    ax, ay = army_index % map_width, army_index // map_width
    tx, ty = target % map_width, target // map_width
    for n in heal_nodes:
        nx, ny = int(n) % map_width, int(n) // map_width
        if abs(ax - nx) + abs(ay - ny) < radius:
            return True
        if _seg_point_dist(nx, ny, ax, ay, tx, ty) <= path_margin:
            return True
    return False
