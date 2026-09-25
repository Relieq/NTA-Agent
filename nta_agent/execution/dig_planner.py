"""Plan a dig: the min-time chain of occupies from our territory to a chosen cell.

Pure (no I/O). Only orthogonally adjacent cells can be occupied, so a dig is a
4-neighbour path grown out of the owned set; each new cell costs
``step_cost(idx)`` seconds (march + battle, see ``dig_cost``) or ``None`` when
the dig group can't take it within ``max_loss`` (a *hard* cell).

Enemy territory is kept at arm's length: a cell within Manhattan ``buffer`` of
an enemy cell is forbidden; the next two rings out cost a penalty that fades
with distance, so the path bends away when that is cheap.
"""
from __future__ import annotations

import heapq
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

W = 600  # world map is 600x600, index = y*W + x
HARD_COST = 1e6  # second pass: a hard cell is walkable but dearer than any detour


@dataclass
class Plan:
    path: list[int]           # cells to occupy, in order, ending at the target
    total_s: float            # sum of step costs (+ enemy-proximity penalties)
    reason: str               # ok | no_path | blocked_by_hard | target_unsafe
    hard: list[int] = field(default_factory=list)  # hard cells the path must cross


def xy(idx: int) -> tuple[int, int]:
    return idx % W, idx // W


def neighbors(idx: int) -> list[int]:
    x, y = xy(idx)
    out = []
    if x > 0:
        out.append(idx - 1)
    if x < W - 1:
        out.append(idx + 1)
    if y > 0:
        out.append(idx - W)
    if y < W - 1:
        out.append(idx + W)
    return out


def enemy_distance_map(enemy: Iterable[int], cells: Iterable[int], limit: int) -> dict[int, int]:
    """Manhattan distance from each of ``cells`` to the nearest enemy cell,
    capped at ``limit + 1`` (anything farther is simply 'far')."""
    ens = [xy(e) for e in enemy]
    out: dict[int, int] = {}
    for c in cells:
        cx, cy = xy(c)
        best = limit + 1
        for ex, ey in ens:
            d = abs(cx - ex) + abs(cy - ey)
            if d < best:
                best = d
                if d == 0:
                    break
        out[c] = best
    return out


def _near_enemy(enemy: set[int], reach: int) -> dict[int, int]:
    """Every cell within ``reach`` of an enemy cell -> its distance (multi-source
    BFS over the open grid; terrain doesn't shield from a neighbour)."""
    dist = {e: 0 for e in enemy}
    q = deque(enemy)
    while q:
        c = q.popleft()
        d = dist[c]
        if d >= reach:
            continue
        for n in neighbors(c):
            if n not in dist:
                dist[n] = d + 1
                q.append(n)
    return dist


def _bbox(cells: Iterable[int], margin: int) -> tuple[int, int, int, int]:
    pts = [xy(c) for c in cells]
    return (max(0, min(p[0] for p in pts) - margin), max(0, min(p[1] for p in pts) - margin),
            min(W - 1, max(p[0] for p in pts) + margin), min(W - 1, max(p[1] for p in pts) + margin))


def target_ok(target: int, *, passable: Callable[[int], bool], others: Iterable[int] = (),
              enemy: Iterable[int] = (), buffer: int = 2) -> bool:
    """A cell we may dig to: occupiable land, nobody's, and beyond ``buffer`` of any enemy."""
    enemy = set(enemy)
    if target in enemy or target in set(others) or not passable(target):
        return False
    tx, ty = xy(target)
    return all(abs(tx - ex) + abs(ty - ey) > buffer for ex, ey in (xy(e) for e in enemy))


def plan_path(
    owned: Iterable[int],
    target: int,
    step_cost: Callable[[int], float | None],
    *,
    passable: Callable[[int], bool],
    others: Iterable[int] = (),
    enemy: Iterable[int] = (),
    buffer: int = 2,
    penalty_s: float = 30.0,
    margin: int = 8,
) -> Plan:
    """Dijkstra from every owned cell (cost 0) to ``target``.

    ``passable`` = static terrain (occupiable land); ``others`` = cells held by
    anyone else (not diggable); ``enemy`` = hostile cells (not diggable AND kept
    ``buffer`` away). The search stays inside the bounding box of owned+target
    grown by ``margin``.
    """
    owned = set(owned)
    if target in owned:
        return Plan([], 0.0, "ok")
    enemy = set(enemy)
    blocked = set(others) | enemy
    near = _near_enemy(enemy, buffer + 2) if enemy else {}

    def forbidden(c: int) -> bool:
        return c in blocked or not passable(c) or near.get(c, buffer + 3) <= buffer

    if forbidden(target):
        return Plan([], 0.0, "target_unsafe")

    x0, y0, x1, y1 = _bbox(owned | {target}, margin)
    memo: dict[int, float | None] = {}

    def cost(c: int) -> float | None:
        if c not in memo:
            memo[c] = step_cost(c)
        return memo[c]

    def penalty(c: int) -> float:
        d = near.get(c)
        return penalty_s * (buffer + 3 - d) if d is not None and d > buffer else 0.0

    def search(allow_hard: bool) -> tuple[list[int], float] | None:
        dist: dict[int, float] = {}
        prev: dict[int, int] = {}
        heap: list[tuple[float, int]] = []
        for o in owned:
            ox, oy = xy(o)
            if x0 <= ox <= x1 and y0 <= oy <= y1:
                dist[o] = 0.0
                heap.append((0.0, o))
        heapq.heapify(heap)
        while heap:
            d, c = heapq.heappop(heap)
            if d > dist.get(c, float("inf")):
                continue
            if c == target:
                path = [c]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                path.reverse()
                return [p for p in path if p not in owned], d
            for n in neighbors(c):
                nx, ny = xy(n)
                if not (x0 <= nx <= x1 and y0 <= ny <= y1) or n in owned or forbidden(n):
                    continue
                s = cost(n)
                if s is None:
                    if not allow_hard:
                        continue
                    s = HARD_COST
                nd = d + s + penalty(n)
                if nd < dist.get(n, float("inf")):
                    dist[n] = nd
                    prev[n] = c
                    heapq.heappush(heap, (nd, n))
        return None

    found = search(allow_hard=False)
    if found:
        return Plan(found[0], found[1], "ok")
    found = search(allow_hard=True)
    if found:
        path, total = found
        hard = [c for c in path if cost(c) is None]
        return Plan(path, total - HARD_COST * len(hard), "blocked_by_hard", hard)
    return Plan([], 0.0, "no_path")


def retarget(
    target: int,
    *,
    owned: Iterable[int],
    passable: Callable[[int], bool],
    others: Iterable[int] = (),
    enemy: Iterable[int] = (),
    buffer: int = 2,
    radius: int = 15,
) -> int | None:
    """The free, safe cell nearest the (lost) ``target`` — Manhattan rings out to
    ``radius``; ties break on the lower index for determinism."""
    owned = set(owned)
    enemy = set(enemy)
    blocked = set(others) | enemy | owned
    near = _near_enemy(enemy, buffer) if enemy else {}
    tx, ty = xy(target)
    for r in range(radius + 1):
        ring = []
        for dx in range(-r, r + 1):
            dy = r - abs(dx)
            for sy in ({dy, -dy}):
                x, y = tx + dx, ty + sy
                if 0 <= x < W and 0 <= y < W:
                    ring.append(y * W + x)
        ok = [c for c in ring if c not in blocked and c not in near and passable(c)]
        if ok:
            return min(ok)
    return None


def place_forts(
    path: list[int],
    nodes: Iterable[int],
    lv_of: Callable[[int], int],
    *,
    every: int = 7,
) -> list[int]:
    """Where to build Cứ Điểm along ``path``: once the dig runs more than
    ``every`` cells past the nearest node (main-city cells / forts), pick a cell
    ``every..every+2`` out — the lowest land level (lv1 wastes least), then the
    nearest — and treat it as a new node."""
    node_xy = [xy(n) for n in nodes]

    def d(c: int) -> int:
        cx, cy = xy(c)
        return min((abs(cx - nx) + abs(cy - ny) for nx, ny in node_xy), default=10**9)

    forts: list[int] = []
    start = 0
    i = 0
    while i < len(path):
        if d(path[i]) <= every:
            i += 1
            continue
        hi = min(len(path), i + 3)
        window = [j for j in range(start, hi) if every <= d(path[j]) <= every + 2]
        if not window:  # the dig starts far out (no node near): build right here
            window = list(range(start, hi))
        j = min(window, key=lambda k: (lv_of(path[k]), d(path[k]), k))
        forts.append(path[j])
        node_xy.append(xy(path[j]))
        start = i = j + 1
    return forts
