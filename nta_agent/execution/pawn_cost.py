"""Pawn recruit/level cereal cost — PER MATCH.

The client (``getPawnCost``) overrides the table's cereal count with
``PAWN_COST_LV_LIST[lv] * pawnCostMap[pawnId]`` whenever the server sent a base cost for
the pawn (``HD_GetWorldRandomInfo.pawnCostMap``; siege 3501/3502 keep the table). In the
2026-09 match 3305 cost 312, not the table's 216 — trusting the table made Recruit try
with cereal it didn't have (ecode.500012).
"""
from __future__ import annotations

PAWN_COST_LV_LIST = (1, 2, 4, 6, 8, 10)   # engine constant, indexed by pawn level
_TABLE_ONLY = {3501, 3502}


def cereal_cost(pawn_id: int, table_cost: int, cost_map: dict | None, lv: int = 0) -> int:
    """Cereal for one pawn of ``pawn_id`` at level ``lv`` (``table_cost`` = the config table's)."""
    base = int((cost_map or {}).get(int(pawn_id), 0) or 0)
    if not base or int(pawn_id) in _TABLE_ONLY or not 0 <= int(lv) < len(PAWN_COST_LV_LIST):
        return int(table_cost)
    return PAWN_COST_LV_LIST[int(lv)] * base
