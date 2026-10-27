"""Between matches: wait for the match the account applied to instead of crashing.

After a season ends the account has no game server until the next match opens (live
2026-10-27: applied to ranked, opening 09:00 next day -> ``enter_game`` found no sid and the
agent crashed). ``wait_for_match`` keeps retrying, sleeps until just after the opening time,
and writes ``lobby.json`` for the dashboard. Applying to a NEW match is the player's choice:
it happens only on a dashboard request (``lobby_request.json``), never on its own.

Room states (engine ``RoomStateType``): 0 NONE (opens at ``time``, ms), 1 IN_MATCH (``time`` =
ms left), 2 IN_GAME, 3 CLOSE, 4 NOT_OPEN. Proto defaults are omitted on the wire: no
``state`` = 0, no ``roomType`` = 0 (free). The engine's ``isInApply`` is
``cancelApplySurplusTime != -1`` with a missing field read as 0, i.e. applied.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ROOM_NAMES = {0: "Tự do", 1: "Tân thủ", 2: "Xếp hạng"}
NONE, IN_MATCH, IN_GAME, CLOSE, NOT_OPEN = 0, 1, 2, 3, 4
MIN_WAIT_S = 60       # opened but no server yet: try again soon
MAX_WAIT_S = 900      # far from the opening: look again every 15 min (status stays fresh)
AFTER_OPEN_S = 30     # come back just after the opening time
REQUEST_TTL_S = 600   # an apply click older than this is ignored


def _room_rows(rooms: dict, now: float) -> list[dict]:
    out = []
    for s in (rooms or {}).get("states") or []:
        if not isinstance(s, dict):
            continue
        st = int(s.get("state") or 0)
        t = s.get("time")
        opens = None
        if t:
            if st == NONE:
                opens = int(t) / 1000
            elif st == IN_MATCH:
                opens = now + int(t) / 1000
        rt = int(s.get("roomType") or 0)
        out.append({"room_type": rt, "room_name": ROOM_NAMES.get(rt, str(rt)),
                    "state": st, "opens_at": opens})
    return out


def lobby_status(rooms: dict, team: dict, now: float) -> dict:
    info = (team or {}).get("teamInfo") or {}
    surplus = info.get("cancelApplySurplusTime")
    applied = bool(info) and int(surplus if surplus is not None else 0) != -1
    rows = _room_rows(rooms, now)
    rt = int(info.get("roomType") or 0) if applied else None
    opens = next((r["opens_at"] for r in rows if r["room_type"] == rt), None) if applied else None
    return {"state": "applied" if applied else "not_applied",
            "room_type": rt, "room_name": ROOM_NAMES.get(rt) if rt is not None else None,
            "opens_at": opens, "rooms": rows,
            "can_play": [int(x) for x in (rooms or {}).get("canPlayRoomTypes") or []]}


def next_check_delay(status: dict, now: float) -> float:
    opens = status.get("opens_at") if status.get("state") == "applied" else None
    if opens is None:
        return MAX_WAIT_S
    return max(MIN_WAIT_S, min(MAX_WAIT_S, opens - now + AFTER_OPEN_S))


def _read(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(path: Path, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _apply_request(cfg, session, status: dict, done_seq, clock) -> tuple[object, dict | None]:
    """Run the player's pending 'apply' request once. Returns (handled seq, result|None)."""
    req = _read(cfg.lobby_request_path)
    seq = req.get("seq")
    if seq is None or seq == done_seq or req.get("op") != "apply":
        return done_seq, None
    at = req.get("at")
    if at is not None and clock() - float(at) > REQUEST_TTL_S:
        return seq, None  # a click from long ago (agent was off) must not apply a later season
    try:
        rt = int(req.get("room_type"))
    except (TypeError, ValueError):
        rt = None
    if rt is None or rt not in (status.get("can_play") or []):
        return seq, {"ok": False, "room_type": rt, "at": clock(),
                     "error": "máy chủ không mở chế độ này cho tài khoản"}
    try:
        session.client.request("lobby/HD_ApplyNewServer", {"roomType": rt})
    except Exception as e:  # a refusal is reported to the player, never fatal
        return seq, {"ok": False, "room_type": rt, "at": clock(), "error": str(e)[:200]}
    return seq, {"ok": True, "room_type": rt, "at": clock()}


def wait_for_match(cfg, build, *, on_event=None, sleep=time.sleep, clock=time.time,
                   step_s: float = 5.0):
    """``build(cfg)`` until it returns a session; while it raises ``NoMatchError`` keep the
    lobby status in ``cfg.lobby_path`` and sleep until just after the opening time (woken
    early by a new dashboard request)."""
    from nta_agent.io.api.session import NoMatchError
    last_state = None
    done_seq = None
    applied = None
    while True:
        try:
            session = build(cfg)
        except NoMatchError as e:
            now = clock()
            status = lobby_status(e.rooms, e.team, now)
            done_seq, res = _apply_request(cfg, e.session, status, done_seq, clock)
            if res is not None:
                applied = res
                if on_event:
                    on_event("match_apply", res)
            if applied is not None:
                status["apply"] = applied
            status["updated_at"] = now
            delay = MIN_WAIT_S if (res and res.get("ok")) else next_check_delay(status, now)
            status["next_check_at"] = now + delay
            _write(cfg.lobby_path, status)
            key = (status["state"], status["room_type"], status["opens_at"])
            if key != last_state and on_event:
                on_event("match_wait", {k: status[k] for k in
                                        ("state", "room_type", "room_name", "opens_at")})
            last_state = key
            try:
                e.session.close()
            except Exception:
                pass
            waited = 0.0
            while waited < delay:  # in steps, so a new request wakes it early
                chunk = min(step_s, delay - waited)
                sleep(chunk)
                waited += chunk
                if _read(cfg.lobby_request_path).get("seq") not in (None, done_seq):
                    break
            continue
        _write(cfg.lobby_path, {"state": "in_game", "updated_at": clock()})
        return session
