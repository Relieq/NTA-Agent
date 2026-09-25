"""Leveling via buffer armies — pure planning (no I/O).

Spec: docs/superpowers/specs/2026-09-25-buffer-leveling-design.md. Costs come from
``pawnAttr[id*1000+lv]``: ``lv_cost`` ("ctype,0,count|…", CType 7 = exp books),
``lv_time`` (seconds), ``lv_cond`` ("4,2004,N" = Trại Lính at level N).
"""
from __future__ import annotations

EXP_BOOK = 7          # CType
BARRACKS_ID = 2004    # Trại Lính: gates pawn levels (lv_cond)


def _types(s: str) -> dict[int, int]:
    out: dict[int, int] = {}
    for part in (s or "").split("|"):
        bits = part.split(",")
        if len(bits) == 3 and bits[0].strip():
            out[int(bits[0])] = out.get(int(bits[0]), 0) + int(bits[2])
    return out


def level_step(rows, pawn_id: int, lv: int) -> dict | None:
    """Cost of one level-up lv -> lv+1: books, seconds, Trại Lính level needed."""
    row = rows.get(int(pawn_id) * 1000 + int(lv))
    if not row or not row.get("lv_cost"):
        return None
    cond = [int(x) for x in str(row.get("lv_cond") or "0,0,0").split(",") if x.strip()]
    need = cond[2] if len(cond) == 3 and cond[1] == BARRACKS_ID else 0
    return {"books": _types(row["lv_cost"]).get(EXP_BOOK, 0),
            "time_s": int(row.get("lv_time") or 0), "barracks_lv": need}


def pawn_cost(rows, pawn_id: int, lv_from: int, lv_to: int, barracks_lv: int) -> dict:
    """Books + seconds to take one pawn from ``lv_from`` to ``lv_to``; ``blocked_at``
    = the level where Trại Lính (or missing data) stops it, else None."""
    books = time_s = 0
    for lv in range(int(lv_from), int(lv_to)):
        step = level_step(rows, pawn_id, lv)
        if step is None or step["barracks_lv"] > barracks_lv:
            return {"books": books, "time_s": time_s, "blocked_at": lv}
        books += step["books"]
        time_s += step["time_s"]
    return {"books": books, "time_s": time_s, "blocked_at": None}


def demand(armies, target_lv: int) -> dict[int, list[dict]]:
    """Weak pawns (lv < target) of the given armies, grouped by pawn type."""
    out: dict[int, list[dict]] = {}
    for a in armies:
        for p in a.get("pawns") or []:
            lv = int(p.get("lv", 0) or 0)
            if lv < target_lv:
                out.setdefault(int(p["id"]), []).append(
                    {"uid": str(p["uid"]), "army_uid": str(a["uid"]), "lv": lv})
    return out
