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


def _cheby(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def recommend_forts(
    main: int,
    owned,
    forts=None,
    map_width: int = 600,
    max_forts: int = 1,
    radius: int = 6,
) -> list[dict]:
    """Return up to ``max_forts`` fort recommendations, best first.

    Each rec is ``{index, x, y, reason}``. Candidates are owned cells with
    Chebyshev distance from the main city greater than ``radius`` (the free
    speed zone) and not already forts. Ranking is greedy: repeatedly pick the
    candidate maximising ``dist_from_main + spread`` where spread is the minimum
    Chebyshev distance to the main city, existing forts, and already-picked recs
    — pushing picks outward and into distinct directions.
    """
    if max_forts <= 0:
        return []
    fort_set = {int(f) for f in (forts or [])}
    mpos = _pos(int(main), map_width)

    candidates = [
        int(c)
        for c in owned
        if int(c) not in fort_set
        and int(c) != int(main)
        and _cheby(_pos(int(c), map_width), mpos) > radius
    ]
    if not candidates:
        return []

    # Anchors that new picks should spread away from: main + existing forts.
    anchors = [mpos] + [_pos(f, map_width) for f in fort_set]
    picked: list[int] = []
    recs: list[dict] = []

    while candidates and len(recs) < max_forts:
        best = None
        best_score = None
        for c in candidates:
            cpos = _pos(c, map_width)
            frontier = _cheby(cpos, mpos)
            spread_pts = anchors + [_pos(p, map_width) for p in picked]
            spread = min(_cheby(cpos, s) for s in spread_pts)
            score = (frontier + spread, frontier, -c)  # deterministic tiebreak
            if best_score is None or score > best_score:
                best_score = score
                best = c
        cpos = _pos(best, map_width)
        recs.append({
            "index": best,
            "x": cpos[0],
            "y": cpos[1],
            "reason": f"biên giới cách thành chính {_cheby(cpos, mpos)} ô",
        })
        picked.append(best)
        candidates.remove(best)

    return recs
