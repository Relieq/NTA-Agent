"""Marshal a :class:`GameState` + target into the sidecar's Forecast Input.

The schema mirrors what ``tools/battlesim`` expects (see the design doc). Only
data we already hold is supplied — the engine derives entry direction and enemy
positions itself, so no coordinates are marshaled here.
"""
from __future__ import annotations

from typing import Any

from nta_agent.state.schema import GameState


def _hp_list(hp) -> list[int] | None:
    """Normalize a pawn's hp to ``[cur, max]``. Live pawns carry hp as a protobuf
    map ``{0: cur, 1: max}`` (int or str keys) — ``list(hp)`` on that returns the
    KEYS ([0, 1]), which put every pawn into the sim at 1 hp and made it lose every
    battle. Also accept ``[cur, max]`` and ``{curHp, maxHp}``."""
    if isinstance(hp, dict):
        cur = hp.get(0, hp.get("0", hp.get("curHp")))
        mx = hp.get(1, hp.get("1", hp.get("maxHp")))
        if cur is not None and mx is not None:
            return [int(cur), int(mx)]
        return None
    if isinstance(hp, (list, tuple)) and len(hp) >= 2:
        return [int(hp[0]), int(hp[1])]
    return None


def _config_equips(state: GameState) -> dict[int, dict]:
    """Resolve each pawn TYPE's equipped gear from ``configPawnMap`` -> its equip
    (uid, id, attrs). A pawn's own ``equip`` field is empty in the API (the loadout
    lives per-type in configPawnMap and the game applies it at battle), so the sim
    must inject it to see the pawn's real strength — same input the game's forecast
    uses. id is derived from the uid ("6005_1"->6005) when the live shape omits it.
    """
    player = (getattr(state, "raw", None) or {}).get("player") or {}
    equips = {e.get("uid"): e for e in (player.get("equips") or []) if isinstance(e, dict)}
    out: dict[int, dict] = {}
    for pid_str, cfg in (player.get("configPawnMap") or {}).items():
        if not isinstance(cfg, dict):
            continue
        e = equips.get(cfg.get("equipUid"))
        if e:
            uid = str(e.get("uid", ""))
            eid = int(e["id"]) if e.get("id") else (int(uid.split("_")[0]) if "_" in uid else 0)
            out[int(pid_str)] = {"uid": uid, "id": eid, "attrs": e.get("attrs") or []}
    return out


def _pawn(p: dict[str, Any], equips_by_pid: dict[int, dict] | None = None) -> dict[str, Any]:
    out = {
        "uid": p.get("uid"),
        "id": int(p.get("id", 0)),
        "lv": int(p.get("lv", 0) or 0),
        "hp": _hp_list(p.get("hp")),
        "buffs": p.get("buffs") or [],
        "skills": p.get("skills") or [],
        "treasures": p.get("treasures") or [],
        "hero": p.get("hero") or None,
    }
    # the pawn's own equip if present, else its type's config loadout
    eq = p.get("equip") or (equips_by_pid or {}).get(int(p.get("id", 0) or 0))
    if eq:
        out["equip"] = eq
    if p.get("point"):  # a chosen formation position reaches the engine
        out["point"] = p["point"]
    return out


def _army(a: dict[str, Any], equips_by_pid: dict[int, dict] | None = None) -> dict[str, Any]:
    return {
        "uid": a.get("uid"),
        "name": a.get("name") or "D1",
        "index": int(a.get("index", 0)),
        "marchTime": int(a.get("marchTime", 0) or 0),
        "pawns": [_pawn(p, equips_by_pid) for p in a.get("pawns", []) or []],
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
    equips_by_pid = _config_equips(state)
    return {
        "playerUid": str(state.user.uid),
        "targetCellIndex": int(target_index),
        "landId": int(land_id),
        "selfToCellDistance": int(distance),
        # 2x2 main city: the engine enters from the city cell nearest the target
        "mainCityIndex": int(getattr(state, "main_city_index", -1) or -1),
        "areaSize": area_size,
        "armies": [_army(a, equips_by_pid) for a in armies],
        "enemyArmyConf": enemy_army_conf,
    }
