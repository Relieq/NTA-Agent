"""Game caps that grow with the main city (read from the game's own config).

Pawns per army is NOT a constant 9: the engine's ``getArmyPawnMaxCount`` reads
effect 63 (ARMY_PAWN_MAX) of the main city's ``buildAttr`` row — lv1 3, lv2-4 5,
lv5 7, lv6+ 9 — and 9 is only its fallback (issue #83).
"""
from __future__ import annotations

MAIN_CITY_ID = 2001
ARMY_PAWN_MAX_EFFECT = 63
DEFAULT_PAWN_CAP = 9  # engine ARMY_PAWN_MAX_COUNT (the fallback)


def _effect(row: dict | None, typ: int) -> int | None:
    for part in str((row or {}).get("effects") or "").split("|"):
        a, _, b = part.partition(",")
        if a.strip() == str(typ) and b.strip().lstrip("-").isdigit():
            return int(b)
    return None


def main_city_lv(state) -> int:
    main = int(getattr(state, "main_city_index", 0) or 0)
    lvs = [int(b.lv) for b in (getattr(state, "builds", None) or [])
           if int(b.id) == MAIN_CITY_ID and (not main or int(b.index) == main)]
    return max(lvs, default=0)


def pawn_cap_at(config, lv: int) -> int:
    try:
        row = config.table("buildAttr").get(MAIN_CITY_ID * 1000 + int(lv))
    except Exception:
        row = None
    return _effect(row, ARMY_PAWN_MAX_EFFECT) or DEFAULT_PAWN_CAP


def army_pawn_cap(state, config=None) -> int:
    """Pawns an army may hold right now (unknown level/config -> 9)."""
    lv = main_city_lv(state)
    if not lv:
        return DEFAULT_PAWN_CAP
    if config is None:
        try:
            from nta_agent.data.config import GameConfig
            config = GameConfig.load()
        except Exception:
            return DEFAULT_PAWN_CAP
    return pawn_cap_at(config, lv) if config else DEFAULT_PAWN_CAP


def next_cap_level(config, lv: int, cap: int, max_lv: int = 30) -> tuple[int, int] | None:
    """(main-city level, cap) of the next raise above ``cap``, if any."""
    for nxt in range(int(lv) + 1, max_lv + 1):
        c = pawn_cap_at(config, nxt)
        if c > cap:
            return nxt, c
    return None
