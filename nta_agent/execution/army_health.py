"""Read wounded-state from a raw army dict (pawns carry hp:[cur,max])."""
from __future__ import annotations


def _hp(pawn: dict) -> tuple[int, int]:
    hp = pawn.get("hp") or [0, 0]
    cur = int(hp[0]) if len(hp) else 0
    mx = int(hp[-1]) if len(hp) else 0
    # No max known -> treat as full (never route on bad data).
    return (cur, mx) if mx > 0 else (0, 0)


def army_is_wounded(army: dict) -> bool:
    for p in army.get("pawns") or []:
        cur, mx = _hp(p)
        if mx > 0 and cur < mx:
            return True
    return False


def army_wound_frac(army: dict) -> float:
    """Fraction of the army's max hp that is missing (0.0 = full, 1.0 = empty)."""
    total_max = total_cur = 0
    for p in army.get("pawns") or []:
        cur, mx = _hp(p)
        total_max += mx
        total_cur += min(cur, mx)
    if total_max <= 0:
        return 0.0
    return (total_max - total_cur) / total_max


def nearest_heal_node(army_index, territory, occupancy, capacity):
    """Nearest heal node (main city or a fort) with a free army slot, or None.

    ``territory`` is a Territory (main_city index + forts). ``occupancy`` maps a
    node index to how many armies sit there now; a node is eligible while
    occupancy < capacity.
    """
    nodes = [territory.main_city] + [f.index for f in territory.forts]
    eligible = [n for n in nodes if n and occupancy.get(n, 0) < capacity]
    if not eligible:
        return None
    return min(eligible, key=lambda n: territory.dist(army_index, n))
