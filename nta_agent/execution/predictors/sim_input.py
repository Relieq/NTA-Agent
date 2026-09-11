"""Marshal a :class:`GameState` + target into the sidecar's Forecast Input.

The schema mirrors what ``tools/battlesim`` expects (see the design doc). Only
data we already hold is supplied — the engine derives entry direction and enemy
positions itself, so no coordinates are marshaled here.
"""
from __future__ import annotations

from typing import Any

from nta_agent.state.schema import GameState


def _pawn(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "uid": p.get("uid"),
        "id": int(p.get("id", 0)),
        "lv": int(p.get("lv", 0) or 0),
        "hp": list(p["hp"]) if p.get("hp") else None,
        "buffs": p.get("buffs") or [],
        "skills": p.get("skills") or [],
        "treasures": p.get("treasures") or [],
        "hero": p.get("hero") or None,
    }


def _army(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "uid": a.get("uid"),
        "name": a.get("name") or "D1",
        "index": int(a.get("index", 0)),
        "marchTime": int(a.get("marchTime", 0) or 0),
        "pawns": [_pawn(p) for p in a.get("pawns", []) or []],
    }


def build_forecast_input(
    state: GameState,
    armies: list[dict[str, Any]],
    *,
    target_index: int,
    land_id: int,
    distance: int,
    area_size: int | None = None,
    enemy_army_conf: dict | None = None,
) -> dict[str, Any]:
    """Build the forecast request dict for one attack on ``target_index``.

    ``enemy_army_conf`` is optional; when omitted the engine generates the
    defenders from land config (``getAreaPawnConfInfo``).
    """
    return {
        "playerUid": str(state.user.uid),
        "targetCellIndex": int(target_index),
        "landId": int(land_id),
        "selfToCellDistance": int(distance),
        "areaSize": area_size,
        "armies": [_army(a) for a in armies],
        "enemyArmyConf": enemy_army_conf,
    }
