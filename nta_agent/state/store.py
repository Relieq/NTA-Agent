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
        # entry carries these flat too; without them exp_book showed 0 despite the
        # account holding books, blocking leveling. Field names verified live.
        exp_book=_res_value(player.get("expBook")),
        up_scroll=_res_value(player.get("upScroll")),
        fixator=_res_value(player.get("fixator")),
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
        # Engine: getBtQueueCount() = DEFAULT_BT_QUEUE_COUNT(2) + policy effect +
        # extra (top-up). Base is 2, not 1; extraBTQueueCount adds paid slots. (A
        # policy that grants a slot isn't in this field — rare; add it if surfaced.)
        build_queue_slots=2 + int(player.get("extraBTQueueCount", 0) or 0),
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


def expire_build_queue(build_queue: list[dict], deadlines: dict[str, float],
                       now: float) -> tuple[list[dict], dict[str, float]]:
    """Drop build-queue items whose time is up, so a missed build-complete push
    never freezes construction. ``deadlines`` maps a queue item's uid to its
    absolute completion time; a uid is stamped ``now + surplusTime`` the first
    time it is seen (surplusTime is the ms remaining at that moment). Returns the
    kept list and the pruned deadlines. Pure — the caller owns the deadline map.
    """
    kept, seen = [], set()
    for item in build_queue or []:
        uid = str(item.get("uid", ""))
        if not uid:
            kept.append(item)  # can't track it -> keep, let the server correct us
            continue
        seen.add(uid)
        if uid not in deadlines:
            deadlines[uid] = now + int(item.get("surplusTime", 0) or 0) / 1000.0
        if now < deadlines[uid]:
            kept.append(item)
    deadlines = {u: d for u, d in deadlines.items() if u in seen}
    return kept, deadlines


# proto.OutPutFlagEnum (engine msg.js) for the fields apply_update_output handles.
_OUTPUT_FLAG = {"granaryCap": 1, "warehouseCap": 2, "cereal": 3, "timber": 4, "stone": 5,
                "expBook": 7, "iron": 8, "gold": 9, "upScroll": 10, "fixator": 11,
                "stamina": 16}


def apply_update_output(state: GameState, out: dict[str, Any]) -> None:
    """Apply an UpdateOutPut block (from ClaimCityOutput or a resource notify).

    Mirrors the engine's ``updateOutputByFlags``: when the block carries ``flags``
    (OutPutFlagEnum) ONLY the flagged entries are authoritative — other fields may be
    present but empty/stale (e.g. ``stone: {}`` on a cereal-only update) and must be
    ignored, or they zero the stock. No ``flags`` = a full update.
    """
    import time as _time
    r = state.resources
    flags = out.get("flags")
    allowed = set(flags) if isinstance(flags, list) and flags else None

    def ok(name: str) -> bool:
        return name in out and (allowed is None or _OUTPUT_FLAG[name] in allowed)

    for name in ("cereal", "timber", "stone"):
        if ok(name):  # OutPutInfo {value, opHour}
            setattr(r, name, _res_value(out[name]))
            # keep the production rate current (opHour rises when a producer levels)
            if isinstance(out[name], dict) and "opHour" in out[name]:
                state.production[name] = int(out[name].get("opHour", 0) or 0)
    for name, attr in (("iron", "iron"), ("gold", "gold"), ("stamina", "stamina"),
                       ("expBook", "exp_book"), ("upScroll", "up_scroll"), ("fixator", "fixator")):
        if ok(name) and isinstance(out[name], (int, float)):
            setattr(r, attr, int(out[name]))
    for name, attr in (("granaryCap", "granary_cap"), ("warehouseCap", "warehouse_cap")):
        if ok(name) and isinstance(out[name], (int, float)):
            setattr(state, attr, int(out[name]))
    # A push carries the authoritative value; restart local accrual from it so we
    # don't double-add the production it already includes (and drop any carried
    # fractional remainder, which belonged to the pre-push base).
    state._output_at = _time.time()
    state._output_frac = {}


def accrue_output(state: GameState, now: float | None = None) -> None:
    """Grow resource stock by production elapsed since the last call.

    The game client fills resources locally from ``opHour`` between server
    pushes; the server only pushes on changes (spending/upgrades), so without
    this the agent's stock freezes between pushes — after the agent spends
    stone/cereal to 0 they stay 0 and every build/recruit stalls. Capped at
    storage. No claiming needed (matches normal play).
    """
    import time as _time
    now = _time.time() if now is None else now
    last = getattr(state, "_output_at", None)
    state._output_at = now
    if last is None or now <= last:
        return
    dt_h = (now - last) / 3600.0
    prod = state.production or {}
    r = state.resources
    caps = {"cereal": state.granary_cap, "timber": state.warehouse_cap,
            "stone": state.warehouse_cap}
    # Resources are ints; a single ~5s tick produces <1 unit, so truncating each
    # tick would drop it all. Carry the fractional remainder between ticks.
    frac = getattr(state, "_output_frac", None)
    if not isinstance(frac, dict):
        frac = state._output_frac = {}
    for name in ("cereal", "timber", "stone"):
        op = int(prod.get(name, 0) or 0)
        if op <= 0:
            continue
        frac[name] = frac.get(name, 0.0) + op * dt_h
        add = int(frac[name])
        if add <= 0:
            continue
        frac[name] -= add
        cap = int(caps.get(name) or 0)
        newv = getattr(r, name, 0) + add
        if cap and newv >= cap:
            newv = cap
            frac[name] = 0.0
        setattr(r, name, newv)


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


_WORLD_ADD_MARCH, _WORLD_REMOVE_MARCH, _WORLD_CAPTURE = 13, 14, 29  # engine NotifyType


def apply_world_notify(state: GameState, notify: dict[str, Any],
                       now: float | None = None) -> GameState:
    """Apply a GAME_ONUPDATEWORLDINFO_NOTIFY ({list: [OnUpdateWorldInfoNotify]}).

    Kept separate from the player notify: NotifyType is shared, so a world item's
    ``type`` must never reach ``apply_player_update`` (type 6 would wipe the build
    queue). Handled: ADD_MARCH / REMOVE_MARCH (world marches, incl. other players'
    — the siege early warning) and CAPTURE aimed at us (sets player.captureInfo
    exactly like the engine's setCaptureInfo: {uid: attacker, time}).
    """
    now = time.time() if now is None else now
    me = str(getattr(state.user, "uid", "") or "")
    for item in notify.get("list", []):
        if not isinstance(item, dict):
            continue
        t = item.get("type")
        if t == _WORLD_ADD_MARCH and isinstance(item.get("data_13"), dict):
            m = dict(item["data_13"])
            m["_rx"] = now
            if m.get("uid"):
                state.world_marches[str(m["uid"])] = m
        elif t == _WORLD_REMOVE_MARCH and isinstance(item.get("data_14"), dict):
            state.world_marches.pop(str(item["data_14"].get("uid", "")), None)
        elif t == _WORLD_CAPTURE and isinstance(item.get("data_29"), dict):
            c = item["data_29"]
            if me and str(c.get("uid", "")) == me:
                state.raw.setdefault("player", {})["captureInfo"] = {
                    "uid": str(c.get("attacker", "")), "time": c.get("time", 0)}
    state.updated_at = time.time()
    return state


def set_world_marches(state: GameState, marches: list, now: float | None = None) -> None:
    """Replace the world-march view from a full ``HD_GetMarchs`` list (resync)."""
    now = time.time() if now is None else now
    state.world_marches = {str(m["uid"]): {**m, "_rx": now}
                           for m in (marches or []) if isinstance(m, dict) and m.get("uid")}


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
