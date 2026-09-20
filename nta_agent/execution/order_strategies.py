"""Candidate selection-orders for the occupy planner (1-tile vs avoid).

The sim's turn order follows selection order (first-selected army seeds the
battle; later armies join as reinforcement waves). We evaluate a few
tactically-meaningful orderings rather than all N! permutations.
"""
from __future__ import annotations


def is_archer_army(army: dict) -> bool:
    """True if a majority of the army's pawns are archers (PawnType 3, id 33xx)."""
    pawns = army.get("pawns") or []
    if not pawns:
        return False
    archers = sum(1 for p in pawns if 3300 <= int(p.get("id", 0)) < 3400)
    return archers * 2 > len(pawns)


def candidate_orders(group: list[dict]) -> list[tuple[str, list[dict]]]:
    """A few candidate (label, ordered-armies) plans for a group of armies."""
    if not group:
        return []
    archers = [a for a in group if is_archer_army(a)]
    others = [a for a in group if not is_archer_army(a)]
    out: list[tuple[str, list[dict]]] = []
    if archers and others:
        out.append(("archers-first", archers + others))
        out.append(("tanks-first", others + archers))
    else:
        out.append(("as-selected", list(group)))
    for a in group:
        out.append((f"single:{a.get('uid')}", [a]))
    return out


def colocated_orders(group: list[dict]) -> list[tuple[str, list[dict]]]:
    """Candidate orders that never mix armies from different cells.

    The sim models the engine's real arrival schedule: the lead army fights at
    frame 0 and every other army joins as a reinforcement wave at frame
    max(1, floor((marchTime_i - marchTime_0)/frameMs)). But we don't feed real
    per-army marchTimes (all 0), so the sim assumes the same-origin schedule
    (waves one frame apart). That's accurate only for armies that DO share an
    origin+distance — i.e. a same-index group, which departs and arrives on that
    schedule. Truly scattered armies (different distances) would arrive on a
    different schedule the sim can't see, so multi-army orders are formed only
    WITHIN a same-index group; every army also gets a single-army order (a lone
    army fights alone regardless, so its origin is harmless).
    """
    from collections import defaultdict
    by_index: dict[int, list[dict]] = defaultdict(list)
    for a in group:
        by_index[int(a.get("index", 0) or 0)].append(a)
    out: list[tuple[str, list[dict]]] = []
    seen: set[tuple[str, ...]] = set()
    for idx in sorted(by_index):
        for label, order in candidate_orders(by_index[idx]):
            key = tuple(str(a.get("uid")) for a in order)
            if key in seen:
                continue
            seen.add(key)
            out.append((label, order))
    return out
