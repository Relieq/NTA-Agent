"""Fort-placement advisor (C2) — deterministic border-expansion geometry.

Recommends where to build Cứ Điểm (strongholds) so the player extends their
fast+heal reach outward. Candidates are owned cells beyond the main-city speed
radius that are not already forts; picks favour the frontier (far from the main
city) and spread (each pick far from already-chosen recs and existing forts) so
recommendations cover different expansion directions. Pure — no I/O, no LLM.
The agent only recommends; the user builds the fort manually.
"""
from __future__ import annotations


def _pos(index: int, map_width: int) -> tuple[int, int]:
    return index % map_width, index // map_width


def _manh(a: tuple[int, int], b: tuple[int, int]) -> int:
    # 4-directional movement: diagonal costs 2 -> Manhattan distance.
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _block_dist(cpos: tuple[int, int], mpos: tuple[int, int]) -> int:
    """Manhattan distance from a cell to the 2x2 main-city block.

    ``mpos`` is the block's corner (min x, min y); the block spans
    [mx, mx+1] x [my, my+1]. Orthogonally-adjacent cells are distance 1.
    """
    dx = max(mpos[0] - cpos[0], 0, cpos[0] - (mpos[0] + 1))
    dy = max(mpos[1] - cpos[1], 0, cpos[1] - (mpos[1] + 1))
    return dx + dy


def recommend_forts(
    main: int,
    owned,
    forts=None,
    rejected=None,
    map_width: int = 600,
    max_forts: int = 1,
    radius: int = 6,
    enemy=None,
    safety_cap: int = 10,
    enemy_weight: float = 1.0,
    danger_radius: int = 0,
) -> list[dict]:
    """Return up to ``max_forts`` fort recommendations, best first.

    Each rec is ``{index, x, y, reason}``. Candidates are owned cells with
    Manhattan distance from the 2x2 main-city block greater than ``radius`` (the free
    speed zone) and not already forts. Ranking is greedy: repeatedly pick the
    candidate maximising ``dist_from_main + spread + safety`` where spread is the
    minimum Manhattan distance to the main-city block, existing forts, and picked
    recs, and ``safety`` favours candidates far from the enemy (C1).

    ``enemy`` = enemy cell/city indices; a fort near them is exposed. ``safety`` =
    ``min(dist_to_nearest_enemy, safety_cap) * enemy_weight`` (no enemy → constant,
    so ranking is unchanged — backward compatible). ``danger_radius`` > 0 drops
    candidates with an enemy within that Manhattan distance.
    """
    if max_forts <= 0:
        return []
    fort_set = {int(f) for f in (forts or [])}
    rej_set = {int(r) for r in (rejected or [])}
    enemy_pts = [_pos(int(e), map_width) for e in (enemy or ())]
    mpos = _pos(int(main), map_width)

    def enemy_dist(cpos: tuple[int, int]) -> int:
        # No enemy known -> treat as maximally safe (constant across candidates).
        return min((_manh(cpos, ep) for ep in enemy_pts), default=safety_cap)

    candidates = [
        int(c)
        for c in owned
        if int(c) not in fort_set
        and int(c) not in rej_set
        and int(c) != int(main)
        and _block_dist(_pos(int(c), map_width), mpos) > radius
        and (danger_radius <= 0 or enemy_dist(_pos(int(c), map_width)) > danger_radius)
    ]
    if not candidates:
        return []

    # Anchors new picks spread away from: existing forts (main handled via block).
    fort_pts = [_pos(f, map_width) for f in fort_set]
    picked: list[int] = []
    recs: list[dict] = []

    while candidates and len(recs) < max_forts:
        best = None
        best_score = None
        for c in candidates:
            cpos = _pos(c, map_width)
            frontier = _block_dist(cpos, mpos)
            spread = min([frontier] + [_manh(cpos, s)
                         for s in fort_pts + [_pos(p, map_width) for p in picked]])
            safety = min(enemy_dist(cpos), safety_cap) * enemy_weight
            score = (frontier + spread + safety, frontier, -c)  # deterministic tiebreak
            if best_score is None or score > best_score:
                best_score = score
                best = c
        cpos = _pos(best, map_width)
        reason = f"biên giới cách thành chính {_block_dist(cpos, mpos)} ô"
        if enemy_pts:
            reason += f", cách địch {enemy_dist(cpos)} ô"
        recs.append({"index": best, "x": cpos[0], "y": cpos[1], "reason": reason})
        picked.append(best)
        candidates.remove(best)

    return recs


def plan_forts(main, owned, existing_forts, decisions, cap,
               map_width: int = 600, radius: int = 6, enemy=None,
               danger_radius: int = 0):
    """Turn owned cells + user decisions into (recommendations, accepted indices).

    ``decisions`` maps a cell index to "accepted" or "rejected". Accepted cells are
    planned forts: excluded from candidates, used as spread anchors, and counted
    against ``cap``. Rejected cells are never recommended. ``enemy`` (cell/city
    indices) makes placement threat-aware (C1).
    """
    accepted = [int(i) for i, d in decisions.items() if d == "accepted"]
    rejected = [int(i) for i, d in decisions.items() if d == "rejected"]
    anchors = [int(f) for f in (existing_forts or [])] + accepted
    slots = max(0, int(cap) - len(anchors))
    recs = recommend_forts(main, owned, forts=anchors, rejected=rejected,
                           map_width=map_width, max_forts=slots, radius=radius,
                           enemy=enemy, danger_radius=danger_radius)
    return recs, accepted


def fort_zone(main, owned, forts=None, *, map_width: int = 600, radius: int = 6,
              enemy=None, danger_radius: int = 0):
    """The RECOMMENDED ZONE for building a Cứ Điểm: the eligible owned cells the
    user may pick one from (replaces the spammed per-cell recs + accept/reject).

    Eligible = owned, OUTSIDE the free speed radius of the 2x2 main-city block,
    not already a fort, and (when ``danger_radius`` > 0) not within that Manhattan
    distance of an enemy. Pure. Returns a sorted list of cell indices.
    """
    fort_set = {int(f) for f in (forts or [])}
    enemy_pts = [_pos(int(e), map_width) for e in (enemy or ())]
    mpos = _pos(int(main), map_width)

    def enemy_ok(cpos):
        if danger_radius <= 0 or not enemy_pts:
            return True
        return min(_manh(cpos, ep) for ep in enemy_pts) > danger_radius

    zone = [
        int(c) for c in owned
        if int(c) not in fort_set
        and int(c) != int(main)
        and _block_dist(_pos(int(c), map_width), mpos) > radius
        and enemy_ok(_pos(int(c), map_width))
    ]
    return sorted(zone)


def can_build_fort(index, main, owned, forts, cap, *, map_width: int = 600,
                   radius: int = 6, enemy=None, danger_radius: int = 0):
    """Validate a user's fort-build pick: the cell must be in the recommended zone
    and the fort count must be under ``cap``. Returns (ok, reason)."""
    if cap and len({int(f) for f in (forts or [])}) >= int(cap):
        return False, "đã đủ số Cứ Điểm (đạt giới hạn)"
    zone = set(fort_zone(main, owned, forts, map_width=map_width, radius=radius,
                         enemy=enemy, danger_radius=danger_radius))
    if int(index) not in zone:
        return False, "ô không nằm trong vùng gợi ý (phải là đất mình, ngoài bán kính 6)"
    return True, ""
