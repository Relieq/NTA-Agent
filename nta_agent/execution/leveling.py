"""Deterministic pawn-leveling decisions (exp-book path).

User workflow (2026-09-18, see memory nta-agent-forge-leveling):
- Only the NORMAL path (``PawnLving`` = exp_book, queued, locks the army). Never
  up_scroll.
- A dedicated LEVELING army holds pawns being leveled (its army is locked while
  leveling). When the fixed FARM army is home, swap leveled pawns into the farm
  army (and send the farm's under-level pawns back to the leveling army). Repeat.

Pure over an explicit interface (army dicts ``{uid, index, pawns:[{uid,id,lv}]}``),
so no live-shape guessing leaks into the tested logic; the raw adapter + rule
wiring + live verification are done separately.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LevelAction:
    kind: str            # "swap" (finish a cycle) | "level" (PawnLving a pawn)
    # level:
    index: int = 0       # leveling army's cell (the city)
    army_uid: str = ""   # leveling army uid
    pawn_uid: str = ""   # pawn to PawnLving
    # swap:
    farm_uid: str = ""
    ready_uid: str = ""  # leveled pawn (leveling army) -> into the farm army
    low_uid: str = ""    # under-level pawn (farm army) -> into the leveling army


def _pawns(army) -> list:
    return (army or {}).get("pawns") or []


def pawns_needing_level(level_army, target_lv, queue_uids) -> list:
    """Pawns in the leveling army below target and not already in the level queue."""
    q = {str(u) for u in (queue_uids or ())}
    return [p for p in _pawns(level_army)
            if int(p.get("lv", 0) or 0) < target_lv and str(p.get("uid")) not in q]


def ready_pawns(level_army, target_lv) -> list:
    """Pawns in the leveling army that have reached the target level."""
    return [p for p in _pawns(level_army) if int(p.get("lv", 0) or 0) >= target_lv]


def next_level_action(farm_army, level_army, target_lv, *,
                      farm_home=False, queue_uids=(), exp_book=0) -> LevelAction | None:
    """The next leveling action, or None.

    Priority: when the farm army is home, first SWAP a ready (leveled) pawn into
    it in place of an under-level farm pawn (completing the cycle); otherwise
    LEVEL the lowest under-level pawn in the leveling army (needs exp_book)."""
    if farm_home:
        ready = ready_pawns(level_army, target_lv)
        low = sorted([p for p in _pawns(farm_army) if int(p.get("lv", 0) or 0) < target_lv],
                     key=lambda p: int(p.get("lv", 0) or 0))
        if ready and low:
            return LevelAction(kind="swap",
                               index=int((farm_army or {}).get("index", 0) or 0),
                               farm_uid=str((farm_army or {}).get("uid", "")),
                               army_uid=str((level_army or {}).get("uid", "")),
                               ready_uid=str(ready[0].get("uid")),
                               low_uid=str(low[0].get("uid")))
    if exp_book > 0:
        todo = pawns_needing_level(level_army, target_lv, queue_uids)
        if todo:
            p = min(todo, key=lambda p: int(p.get("lv", 0) or 0))  # lowest first
            return LevelAction(kind="level",
                               index=int((level_army or {}).get("index", 0) or 0),
                               army_uid=str((level_army or {}).get("uid", "")),
                               pawn_uid=str(p.get("uid")))
    return None
