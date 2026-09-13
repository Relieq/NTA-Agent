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
