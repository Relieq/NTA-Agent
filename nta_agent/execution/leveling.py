"""Deterministic pawn-leveling decisions (exp-book path).

User workflow (2026-09-18/19, see memory nta-agent-forge-leveling):
- Only the NORMAL path (``PawnLving`` = exp_book, queued, locks the army).
- The FARM is a GROUP of armies (a cell holds up to ~5; = ``profile.army.group``).
- The agent AUTO-CREATES one dedicated LEVELING army (a buffer): it pulls
  under-target pawns out of the farm group into it (``ChangePawnArmy`` with
  ``isNewCreate`` for the first pawn, plain move after), levels them
  (``PawnLving``), and — when the farm group is home — swaps ready (>=target)
  pawns back into the farm group (``ExchangePawnArmy``). The leveling army is
  dismissed when empty.

Pure over an explicit interface (army dicts ``{uid, index, name, pawns:[{uid,id,
lv}]}``); the raw adapter + create-army param details are verified live when a
workable multi-army state exists.
"""
from __future__ import annotations

from dataclasses import dataclass

LEVEL_ARMY_NAME = "Nâng Cấp"  # the agent's dedicated leveling army (found by name)


@dataclass
class LevelAction:
    kind: str            # "swap" | "level" | "pull" | "dismiss"
    index: int = 0       # the cell the op happens at (the city, when home)
    level_uid: str = ""  # leveling army uid ("" when it must be created)
    pawn_uid: str = ""   # pawn to level (level) or to pull (pull)
    src_uid: str = ""    # source farm army (pull)
    create: bool = False # create the leveling army (pull, isNewCreate)
    farm_uid: str = ""   # farm army for a swap
    ready_uid: str = ""  # leveled pawn (leveling army) -> farm (swap)
    low_uid: str = ""    # under-target pawn (farm) -> leveling army (swap)


def _pawns(army) -> list:
    return (army or {}).get("pawns") or []


def _under(army, target_lv) -> list:
    return sorted([p for p in _pawns(army) if int(p.get("lv", 0) or 0) < target_lv],
                  key=lambda p: int(p.get("lv", 0) or 0))


def find_leveling_army(armies) -> dict | None:
    for a in armies:
        if str(a.get("name", "")) == LEVEL_ARMY_NAME:
            return a
    return None


def next_level_action(farm_armies, level_army, target_lv, *, farm_home=False,
                      queue_uids=(), exp_book=0, max_leveling=1) -> LevelAction | None:
    """The next leveling step, or None. Priority: swap a ready pawn back into the
    farm (finish a cycle) > level an under-target pawn > pull a new one in >
    dismiss the empty leveling army."""
    lv_pawns = _pawns(level_army)
    lv_uid = str((level_army or {}).get("uid", "")) if level_army else ""
    lv_index = int((level_army or {}).get("index", 0) or 0) if level_army else 0
    q = {str(u) for u in (queue_uids or ())}

    # 1) Swap a ready (leveled) pawn into a farm army in place of an under-target one.
    if farm_home and level_army:
        ready = [p for p in lv_pawns if int(p.get("lv", 0) or 0) >= target_lv]
        if ready:
            for fa in farm_armies:
                low = _under(fa, target_lv)
                if low:
                    return LevelAction(kind="swap", index=int(fa.get("index", 0) or 0),
                                       level_uid=lv_uid, farm_uid=str(fa.get("uid", "")),
                                       ready_uid=str(ready[0].get("uid")),
                                       low_uid=str(low[0].get("uid")))

    # 2) Level the lowest under-target pawn already in the leveling army.
    if exp_book > 0 and level_army:
        todo = [p for p in lv_pawns
                if int(p.get("lv", 0) or 0) < target_lv and str(p.get("uid")) not in q]
        if todo:
            p = min(todo, key=lambda p: int(p.get("lv", 0) or 0))
            return LevelAction(kind="level", index=lv_index, level_uid=lv_uid,
                               pawn_uid=str(p.get("uid")))

    # 3) Pull an under-target farm pawn into the leveling army (create it if needed).
    if farm_home and len(lv_pawns) < max_leveling:
        for fa in farm_armies:
            low = _under(fa, target_lv)
            if low:
                return LevelAction(kind="pull", index=int(fa.get("index", 0) or 0),
                                   src_uid=str(fa.get("uid", "")), pawn_uid=str(low[0].get("uid")),
                                   create=(level_army is None), level_uid=lv_uid)

    # 4) Nothing left to level -> dismiss the empty leveling army.
    if level_army and not lv_pawns:
        return LevelAction(kind="dismiss", index=lv_index, level_uid=lv_uid)
    return None
