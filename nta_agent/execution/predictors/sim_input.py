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
        if cur is not None:
            # protobuf omits a zero/unchanged entry: an enemy pawn often carries only
            # {0: cur} — assume it's at full health rather than drop its hp (NaN hp
            # kept a battle from ever ending)
            return [int(cur), int(mx if mx is not None else cur)]
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


# CEffect types of a policy that reach the battle as a fighter buff (engine
# getPolicyBattleBuffs). DEFEND_HALO (38) is alliance-only and left out.
_BATTLE_POLICY_TYPES = frozenset({32, 39, 40, 41, 42, 53, 54, 55, 56, 57, 59, 60, 61, 62})


def _policy_rows() -> dict[int, dict]:
    """The ``policy`` config table ({id: row}); empty when the config is not on disk."""
    try:
        from nta_agent.data.config import GameConfig
        return GameConfig.load().table("policy")
    except Exception:
        return {}


def _pawn_type(pawn_id: int) -> int:
    """pawnBase.type of a pawn (1 pikeman, 2 peltast, 3 archer, 4 sowar); 0 if unknown."""
    try:
        from nta_agent.data.config import GameConfig
        return int((GameConfig.load().table("pawnBase").get(int(pawn_id)) or {}).get("type") or 0)
    except Exception:
        return 0


# policy id (= BuffType id) -> does this pawn get it? (engine checkPawnCanAddPolicyBuff)
_PAWN_FILTER = {
    1030: lambda p: p["lv"] == 1,               # LV_1_POWER
    1045: lambda p: p["lv"] == 6,               # LV_6_POWER
    1049: lambda p: _pawn_type(p["id"]) == 1,   # SPEAR_MASTERY
    1050: lambda p: _pawn_type(p["id"]) == 2,   # SHIELD_MASTERY
    1051: lambda p: _pawn_type(p["id"]) == 3,   # ARCHER_MASTERY
    1052: lambda p: _pawn_type(p["id"]) == 4,   # CAVALRY_MASTERY
    1047: lambda p: p["id"] == 3501,            # CAPTURE_TERRITORY
}


def _policy_buff_specs(state: GameState) -> list[tuple[int, float]]:
    """(policy id, value) for every adopted policy whose effect is a battle buff.

    The server gives each of our fighters these buffs (live record 2026-10-16: +20%
    damage to monsters, policy 1042); the sim used to leave them out and predicted 0
    deaths for a battle that lost a pawn. The same policy in several slots stacks its
    level (``values[min(up-1, last)]``), like the engine's ``addPolicys``. Alliance and
    season policies are not in the player data and stay out.
    """
    player = (getattr(state, "raw", None) or {}).get("player") or {}
    slots = player.get("policySlots") or {}
    ups: dict[int, int] = {}
    for slot in slots.values():
        pid = int(slot.get("id") or 0) if isinstance(slot, dict) else 0
        if pid > 0:
            ups[pid] = ups.get(pid, 0) + 1
    if not ups:
        return []
    rows = _policy_rows()
    out: list[tuple[int, float]] = []
    for pid, up in ups.items():
        row = rows.get(pid)
        if not row or int(row.get("type", 0) or 0) not in _BATTLE_POLICY_TYPES:
            continue
        vals = [float(v) for v in str(row.get("value", "")).split(",") if v.strip()]
        if vals:
            v = vals[min(up - 1, len(vals) - 1)]
            out.append((pid, int(v) if v == int(v) else v))
    return out


def _pawn(p: dict[str, Any], equips_by_pid: dict[int, dict] | None = None,
          policy: list[tuple[int, float]] | None = None) -> dict[str, Any]:
    out = {
        "uid": p.get("uid"),
        "id": int(p.get("id", 0)),
        "lv": int(p.get("lv", 0) or 0),
        "hp": _hp_list(p.get("hp")),
        "buffs": list(p.get("buffs") or []) + [
            {"type": pid, "lv": 1, "provider": p.get("uid"), "round": -1, "times": -1,
             "value": val, "needRound": -1} for pid, val in (policy or [])
            if _PAWN_FILTER.get(pid, lambda _p: True)({"id": int(p.get("id", 0)),
                                                       "lv": int(p.get("lv", 0) or 0)})],
        "skills": p.get("skills") or [],
        # engine fromSvrTreasureInfo does treasure.rewards.map(): protobuf omits an
        # empty repeated field, so a live {uid, id} treasure crashed the forecast
        "treasures": [{**t, "rewards": t.get("rewards") or []}
                      for t in (p.get("treasures") or []) if isinstance(t, dict)],
        "hero": p.get("hero") or None,
    }
    # the pawn's own equip if present, else its type's config loadout
    eq = p.get("equip") or (equips_by_pid or {}).get(int(p.get("id", 0) or 0))
    if eq:
        out["equip"] = eq
    if p.get("point"):  # a chosen formation position reaches the engine
        out["point"] = p["point"]
    return out


def _army(a: dict[str, Any], equips_by_pid: dict[int, dict] | None = None,
          policy: list[tuple[int, float]] | None = None) -> dict[str, Any]:
    return {
        "uid": a.get("uid"),
        "name": a.get("name") or "D1",
        "index": int(a.get("index", 0)),
        "marchTime": int(a.get("marchTime", 0) or 0),
        "pawns": [_pawn(p, equips_by_pid, policy) for p in a.get("pawns", []) or []],
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
    policy = _policy_buff_specs(state)
    if enemy_army_conf:
        # same normalisation as our pawns: hp maps missing the max, treasures without
        # rewards (both crash or stall the engine)
        enemy_army_conf = {**enemy_army_conf, "armys": [
            {**a, "pawns": [{**q,
                             **({"hp": _hp_list(q["hp"])} if isinstance(q.get("hp"), dict) else {}),
                             # protobuf omits a 0 coordinate ({x:3} = (3,0)): an undefined
                             # y/x made distances NaN and the battle never engaged
                             **({"point": {"x": int(q["point"].get("x", 0) or 0),
                                           "y": int(q["point"].get("y", 0) or 0)}}
                                if isinstance(q.get("point"), dict) else {}),
                             "treasures": [{**t, "rewards": t.get("rewards") or []}
                                           for t in (q.get("treasures") or [])
                                           if isinstance(t, dict)]}
                            for q in (a.get("pawns") or [])]}
            for a in (enemy_army_conf.get("armys") or [])]}
    return {
        "playerUid": str(state.user.uid),
        "targetCellIndex": int(target_index),
        "landId": int(land_id),
        "selfToCellDistance": int(distance),
        # 2x2 main city: the engine enters from the city cell nearest the target
        "mainCityIndex": int(getattr(state, "main_city_index", -1) or -1),
        "areaSize": area_size,
        "armies": [_army(a, equips_by_pid, policy) for a in armies],
        "enemyArmyConf": enemy_army_conf,
    }
