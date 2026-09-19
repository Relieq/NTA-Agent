"""Build and update :class:`GameState` from the game's own data shapes.

Two entry points today:

* :func:`from_novice_data` — the tutorial ``slg_novice_data_<uid>`` snapshot
  (a full client-side game state), used to bootstrap and to test the model.
* :func:`apply_user` — the ``user`` object from ``LOBBY_HD_TRYLOGIN_S2C``.

Both the novice snapshot and live S2C messages share field names, so the same
mapping serves API updates as we wire more routes (``apply_s2c`` later).
"""
from __future__ import annotations

import time
from typing import Any

from nta_agent.state.schema import (
    Area,
    Building,
    GameState,
    Hero,
    March,
    Resources,
    Slot,
    User,
)


def _slots(d: dict[str, Any] | None) -> list[Slot]:
    out: list[Slot] = []
    for k, v in (d or {}).items():
        try:
            out.append(Slot(slot=int(k), lv=int(v.get("lv", 0)), id=int(v.get("id", 0))))
        except (ValueError, AttributeError):
            continue
    return sorted(out, key=lambda s: s.slot)


def _building(b: dict[str, Any]) -> Building:
    p = b.get("point") or {}
    return Building(
        index=int(b.get("index", 0)),
        id=int(b.get("id", 0)),
        lv=int(b.get("lv", 0)),
        uid=str(b.get("uid", "")),
        point=(int(p.get("x", 0)), int(p.get("y", 0))),
    )


def _hp(v: Any) -> tuple[int, int]:
    """Area hp is [current, max] in the game; tolerate int or missing."""
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        return (int(v[0]), int(v[1]))
    if isinstance(v, (int, float)):
        return (int(v), int(v))
    return (0, 0)


def _area(raw: dict[str, Any]) -> Area:
    return Area(
        index=int(raw.get("index", 0)),
        owner=str(raw.get("owner", "")),
        city_id=int(raw.get("cityId", 0)),
        land_id=int(raw.get("landId", 0)),
        hp=_hp(raw.get("hp")),
        buildings=[_building(b) for b in raw.get("builds", [])],
        raw=raw,
    )


def from_novice_data(nd: dict[str, Any], user: dict[str, Any] | None = None) -> GameState:
    """Construct a GameState from a tutorial novice_data snapshot."""
    novice_user = nd.get("noviceUser") or {}
    res = Resources(
        cereal=int(nd.get("cereal", 0)),
        timber=int(nd.get("timber", 0)),
        stone=int(nd.get("stone", 0)),
        iron=int(nd.get("iron", 0)),
        gold=int(novice_user.get("gold", 0)),
        stamina=int(nd.get("stamina", 0)),
        exp_book=int(nd.get("expBook", 0)),
        up_scroll=int(nd.get("upScroll", 0)),
        fixator=int(nd.get("fixator", 0)),
    )
    areas = {int(k): _area(v) for k, v in (nd.get("areas") or {}).items()}
    heroes = [
        Hero(lv=int(h.get("lv", 0)), avatar_army_uid=str(h.get("avatarArmyUID", "")), raw=h)
        for h in nd.get("heroSlots", [])
    ]
    marches = [March(uid=str(m.get("uid", "")), raw=m) for m in nd.get("marchs", [])]

    state = GameState(
        resources=res,
        areas=areas,
        marches=marches,
        pawn_slots=_slots(nd.get("pawnSlots")),
        policy_slots=_slots(nd.get("policySlots")),
        equip_slots=_slots(nd.get("equipSlots")),
        heroes=heroes,
        chapter=int(nd.get("chapter", 0)),
        land_score=int(nd.get("landScore", 0)),
        source="novice",
        raw=nd,
    )
    if user:
        apply_user(state, user)
    return state


def _res_value(v: Any) -> int:
    """Resources are flat ints in novice mode but {value, opHour} in a live match."""
    if isinstance(v, dict):
        return int(v.get("value", 0))
    if isinstance(v, (int, float)):
        return int(v)
    return 0


def from_entry_rst(rst: dict[str, Any], user: dict[str, Any] | None = None) -> GameState:
    """Build GameState from GAME_HD_ENTRY_S2C.rst (authoritative live match state)."""
    player = rst.get("player") or {}
    res = Resources(
        cereal=_res_value(player.get("cereal")),
        timber=_res_value(player.get("timber")),
        stone=_res_value(player.get("stone")),
        iron=_res_value(player.get("iron")),
        gold=_res_value(player.get("gold")),
        stamina=int(player.get("stamina", 0) or 0),
    )
    heroes = [
        Hero(lv=int(h.get("lv", 0)), avatar_army_uid=str(h.get("avatarArmyUID", "")), raw=h)
        for h in player.get("heroSlots", [])
    ]

    def _op(v):  # OutPutInfo {value, opHour} -> opHour
        return int(v.get("opHour", 0)) if isinstance(v, dict) else 0

    production = {
        name: _op(player.get(name))
        for name in ("cereal", "timber", "stone")
        if isinstance(player.get(name), dict)
    }
    # Entry builds are {uid,id,lv} with no area index — they sit in the main city,
    # so their area index is mainCityIndex (the target for HD_UpAreaBuild).
    main_city_index = int(player.get("mainCityIndex", 0) or 0)
    builds = []
    for b in player.get("builds", []):
        if isinstance(b, dict):
            bld = _building(b)
            if not bld.index:
                bld.index = main_city_index
            builds.append(bld)
    state = GameState(
        resources=res,
        heroes=heroes,
        builds=builds,
        land_score=int(player.get("landCount", 0) or 0),
        main_city_index=main_city_index,
        build_queue=list(player.get("btQueues") or []),
        build_queue_slots=1 + int(player.get("extraBTQueueCount", 0) or 0),
        production=production,
        granary_cap=int(player.get("granaryCap", 0) or 0),
        warehouse_cap=int(player.get("warehouseCap", 0) or 0),
        source="api",
        raw=rst,
    )
    if user:
        apply_user(state, user)
    elif player.get("uid"):
        state.user = User(uid=str(player["uid"]), raw=player)
    return state


def apply_update_output(state: GameState, out: dict[str, Any]) -> None:
    """Apply an UpdateOutPut block (from ClaimCityOutput or a resource notify)."""
    r = state.resources
    for name in ("cereal", "timber", "stone"):
        if name in out:  # OutPutInfo {value, opHour}
            setattr(r, name, _res_value(out[name]))
    for name, attr in (("iron", "iron"), ("gold", "gold"), ("stamina", "stamina"),
                       ("expBook", "exp_book"), ("upScroll", "up_scroll"), ("fixator", "fixator")):
        if name in out and isinstance(out[name], (int, float)):
            setattr(r, attr, int(out[name]))


def apply_player_update(state: GameState, item: dict[str, Any]) -> None:
    """Apply one OnUpdatePlayerInfoNotify item (a tagged union keyed by ``type``).

    Fields are named ``data_<type>``; only the one matching ``type`` is set.
    Handled: resources (data_1/data_41 = UpdateOutPut), the build queue
    (data_6 = repeated BTInfo) and a completed/upgraded building (data_5 =
    AreaBuildInfo). Without the build ones, a finished upgrade never clears
    ``build_queue`` nor bumps the building level, so the state (and dashboard)
    stayed frozen on "đang xây" and build_order saw the slot permanently full.
    """
    for key in ("data_1", "data_41"):
        block = item.get(key)
        if isinstance(block, dict):
            apply_update_output(state, block)
    # UPDATE_BT_QUEUE: the authoritative build queue. A finished build sends the
    # queue without it (often empty) — replace wholesale so it can clear.
    if item.get("type") == 6:
        q = item.get("data_6")
        state.build_queue = list(q) if isinstance(q, list) else []
    # A single building at its new level (build complete / upgraded).
    bld = item.get("data_5")
    if isinstance(bld, dict):
        _apply_build_update(state, bld)


def _apply_build_update(state: GameState, info: dict[str, Any]) -> None:
    """Merge one AreaBuildInfo (index,uid,id,lv,point) into ``state.builds``."""
    b = _building(info)
    if not b.index:
        b.index = state.main_city_index
    for existing in state.builds:
        if (b.uid and existing.uid == b.uid) or (existing.id == b.id and existing.index == b.index):
            existing.lv = b.lv
            if b.uid:
                existing.uid = b.uid
            return
    state.builds.append(b)


def apply_notify(state: GameState, notify: dict[str, Any]) -> GameState:
    """Apply an On*UpdateInfo notify ({list: [OnUpdatePlayerInfoNotify, ...]})."""
    for item in notify.get("list", []):
        if isinstance(item, dict):
            apply_player_update(state, item)
    state.updated_at = time.time()
    return state


def apply_user(state: GameState, user: dict[str, Any]) -> GameState:
    """Populate the User block from a LOBBY_HD_TRYLOGIN_S2C ``user`` object."""
    state.user = User(
        uid=str(user.get("uid", "")),
        nickname=str(user.get("nickname", "")),
        login_type=str(user.get("loginType", "")),
        session_id=str(user.get("sessionId", "")),
        raw=user,
    )
    state.updated_at = time.time()
    return state
