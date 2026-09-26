"""Read wounded-state from a raw army dict (pawns carry hp:[cur,max])."""
from __future__ import annotations


def _hp(pawn: dict) -> tuple[int, int]:
    """(current, max) hp for a raw pawn, or (0,0) when max is unknown.

    Live ``HD_GetPlayerArmys`` pawns carry ``hp`` as a protobuf map
    ``{0: current, 1: max}`` (verified live 2026-09-17). Also accept ``hp:[cur,max]``
    and ``{curHp,maxHp}`` shapes. Unknown max -> (0,0) so we never route on bad
    data (a pawn with no max reads as "not wounded").
    """
    hp = pawn.get("hp")
    if isinstance(hp, dict):
        # Live shape: protobuf map {0: current, 1: max} (keys may be int or str).
        cur = int(hp.get(0, hp.get("0", 0)) or 0)
        mx = int(hp.get(1, hp.get("1", 0)) or 0)
    elif isinstance(hp, (list, tuple)):
        cur = int(hp[0]) if len(hp) else 0
        mx = int(hp[-1]) if len(hp) > 1 else 0
    elif "curHp" in pawn or "maxHp" in pawn:
        cur = int(pawn.get("curHp", 0) or 0)
        mx = int(pawn.get("maxHp", 0) or 0)
    else:
        cur, mx = int(hp or 0), 0  # scalar current only -> max unknown
    return (cur, mx) if mx > 0 else (0, 0)


# ArmyState (engine): 0 NONE(rảnh) 1 MARCH 2 FIGHT 3 DRILL(chiêu mộ) 4 LVING(nâng cấp)
# 5 TONDEN 6 CURING. Chỉ state 0 mới điều/gửi được; mọi state khác đội đang bận.
def is_idle(army: dict) -> bool:
    """True if the army is free to move/send (ArmyState NONE). Marching, fighting,
    recruiting (DRILL), leveling (LVING), tonden and curing all lock it."""
    return int((army or {}).get("state", 0) or 0) == 0


def leveling_pawn_uids(state, now: float | None = None) -> set[str]:
    """Pawn uids being leveled. Their army sits in the drill ground: its ``state``
    stays 0 but it can't move (MoveCellArmy ecode.500080).

    Live shape (verified 2026-09-25): ``player.pawnLevelingQueues`` = a LIST of
    ``{uid, index, auid, puid, id, lv, needTime, surplusTime}``. The older
    ``pawnLvingQueues`` {pawnUIDMap, map} shape is still accepted."""
    import time as _time
    player = (getattr(state, "raw", None) or {}).get("player") or {}
    uids: set[str] = set()
    # The queue runs ONE pawn at a time per city (engine putPawnLvingQueue: only the
    # head has a start time). When we know when the list was read, drop the entries
    # that must have finished since: head needs surplusTime, the rest needTime each.
    at = player.get("_pawnLevelingQueuesAt")
    now = _time.time() if now is None else now
    ends: dict[int, float] = {}
    for item in player.get("pawnLevelingQueues") or []:
        if not (isinstance(item, dict) and item.get("puid")):
            continue
        if at is not None:
            idx = int(item.get("index", 0) or 0)
            first = idx not in ends
            dur = int((item.get("surplusTime") if first else item.get("needTime"))
                      or item.get("needTime") or 0) / 1000
            ends[idx] = (at if first else ends[idx]) + dur
            if ends[idx] <= now:
                continue
        uids.add(str(item["puid"]))
    q = player.get("pawnLvingQueues")
    if isinstance(q, dict):
        uids |= {str(u) for u in (q.get("pawnUIDMap") or {})}
        for item in (q.get("map") or {}).values():
            if isinstance(item, dict) and item.get("puid"):
                uids.add(str(item["puid"]))
    return uids


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
