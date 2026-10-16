"""Revive-injured helpers: pick the best dead pawn and a revive destination.

Dead pawns (``player.injuryPawns`` = ``{uid,id,lv,deadTime}``) are revived via
``HD_CureInjuryPawn`` into an army stationed at the main city, or a new army.
"""
from __future__ import annotations

NEW_ARMY_NAME = "Cứu Hộ"


def best_injured(injury_pawns: list[dict]) -> dict | None:
    """The highest-value dead pawn (by level, then id), or None."""
    if not injury_pawns:
        return None
    return max(injury_pawns, key=lambda p: (int(p.get("lv", 0) or 0), int(p.get("id", 0) or 0)))


def _occupancy(army: dict) -> int:
    return len(army.get("pawns") or []) + len(army.get("curingPawns") or [])


def _is_rescue(a: dict) -> bool:
    return str(a.get("name", "")).startswith(NEW_ARMY_NAME)


def revive_target(armies: list[dict], main_index: int, capacity_hint: int = 9,
                  origin: str | None = None) -> tuple[str, str]:
    """Where to revive into: (army_uid, army_name).

    1. the pawn's own army (``origin`` uid) when it stands at the main city and has a free slot;
    2. else the rescue army ("Cứu Hộ") at the city with room — it takes the pawn home later;
    3. else a NEW rescue army (named "Cứu Hộ 2", ... when one exists already).

    Never a spare or a leveling buffer: a pawn put there was lost to the army it belongs to
    (and to the rules that recruit into / reshape those). ``capacity_hint`` is only a hint — if
    wrong the server rejects (ecode.500019) and the rule backs off.
    """
    at_city = [a for a in armies if int(a.get("index", 0) or 0) == main_index]
    if origin:
        for a in at_city:
            if str(a.get("uid")) == str(origin) and not _is_rescue(a)                     and int(a.get("state", 0) or 0) == 0 and _occupancy(a) < capacity_hint:
                return str(a.get("uid", "")), str(a.get("name", "") or "")
    for a in at_city:
        if _is_rescue(a) and int(a.get("state", 0) or 0) == 0 and _occupancy(a) < capacity_hint:
            return str(a.get("uid", "")), str(a.get("name", "") or "")
    names = {str(a.get("name", "")) for a in armies}
    name, k = NEW_ARMY_NAME, 1
    while name in names:
        k += 1
        name = f"{NEW_ARMY_NAME} {k}"
    return "", name
