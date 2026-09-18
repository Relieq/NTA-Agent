"""Territory threat / incursion model (Phase P1).

Principle (user 2026-09-18): within the CONVEX HULL that contains our territory,
an enemy that touches the boundary or has slipped inside the hull is *intruding*
(a real threat), unlike an enemy far away. Pure geometry over the Tier B
owned/enemy layer — no I/O, no LLM.
"""
from __future__ import annotations

_NEIGHBORS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def _cross(o, a, b) -> int:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def convex_hull(points) -> list[tuple[int, int]]:
    """Convex hull (CCW, no repeated endpoint) via Andrew's monotone chain.

    Fewer than 3 unique points (or all collinear) → returns the sorted unique
    points (a degenerate hull); callers rely on adjacency in that case.
    """
    pts = sorted({(int(x), int(y)) for x, y in points})
    if len(pts) < 3:
        return pts
    lower: list = []
    for p in pts:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list = []
    for p in reversed(pts):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return hull if len(hull) >= 3 else pts


def point_in_hull(p, hull) -> bool:
    """True if p is inside or on a CCW convex ``hull`` (needs >=3 vertices)."""
    if len(hull) < 3:
        return tuple(p) in {tuple(h) for h in hull}
    p = (int(p[0]), int(p[1]))
    n = len(hull)
    for i in range(n):
        if _cross(hull[i], hull[(i + 1) % n], p) < 0:
            return False  # right of an edge -> outside
    return True


def _direction(dx: int, dy: int) -> str:
    # Map grid delta (index y grows downward) to a Vietnamese compass label.
    ns = "Nam" if dy > 0 else ("Bắc" if dy < 0 else "")
    ew = "Đông" if dx > 0 else ("Tây" if dx < 0 else "")
    return (ns + " " + ew).strip() or "trung tâm"


def detect_incursions(owned, enemy_cells, enemy_cities=None, main=0, map_width=600) -> dict:
    """Classify enemy cells that touch/penetrate our territory as threats.

    A threat = an enemy cell that is inside/on the convex hull of ``owned`` OR is
    4-adjacent to an owned cell. Returns ``{"threats": [...], "summary": {...}}``.
    """
    enemy_cities = enemy_cities or {}
    owned_set = {int(c) for c in owned}
    pts = [(c % map_width, c // map_width) for c in owned_set]
    hull = convex_hull(pts)
    mx, my = int(main) % map_width, int(main) // map_width

    threats = []
    for e in enemy_cells:
        e = int(e)
        ex, ey = e % map_width, e // map_width
        inside = point_in_hull((ex, ey), hull)
        adjacent = any((ey + dy) * map_width + (ex + dx) in owned_set
                       for dx, dy in _NEIGHBORS)
        if not (inside or adjacent):
            continue
        threats.append({
            "index": e, "x": ex, "y": ey,
            "is_city": e in enemy_cities,
            "inside_hull": inside, "adjacent": adjacent,
            "dist_to_main": abs(ex - mx) + abs(ey - my),
            "direction": _direction(ex - mx, ey - my),
        })

    threats.sort(key=lambda t: (not t["is_city"], not t["inside_hull"], t["dist_to_main"]))
    summary = {
        "count": len(threats),
        "nearest_dist": threats[0]["dist_to_main"] if threats else None,
        "has_enemy_city": any(t["is_city"] for t in threats),
        "inside_count": sum(1 for t in threats if t["inside_hull"]),
        "directions": sorted({t["direction"] for t in threats}),
    }
    return {"threats": threats, "summary": summary}
