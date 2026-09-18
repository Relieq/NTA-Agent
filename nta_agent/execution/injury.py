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


def revive_target(armies: list[dict], main_index: int, capacity_hint: int = 9) -> tuple[str, str]:
    """Where to revive into: (army_uid, army_name).

    Prefer an army stationed at the main city with room (pawns + curing <
    ``capacity_hint``); otherwise ("", NEW_ARMY_NAME) to create a fresh army.
    ``capacity_hint`` is only a hint — if wrong the server rejects (ecode.500019)
    and the rule backs off, so no hard-coded limit is trusted.
    """
    for a in armies:
        if int(a.get("index", 0) or 0) == main_index and _occupancy(a) < capacity_hint:
            return str(a.get("uid", "")), str(a.get("name", "") or "")
    return "", NEW_ARMY_NAME
