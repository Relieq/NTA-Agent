"""Rearranging pawns on the player's request: swap two pawns between armies, move pawns
to another (or a new) army, reorder pawns inside an army.

The brain only NAMES armies and pawn TYPES; this module resolves the actual pawns
deterministically (lowest level first, heroes never), checks what the game allows
(both armies in the SAME cell, room under the army cap) and can simulate the result.
PURE: no engine/API. The proposal is confirmed on the dashboard, then
``runtime.pawn_move_queue`` waits for idle armies and sends it.
"""
from __future__ import annotations

import copy
from collections import Counter

from nta_agent.execution.army_composer import _is_hero

W = 600  # world map width: cell index = y * W + x


def _dist(a: int, b: int) -> int:
    return abs(a % W - b % W) + abs(a // W - b // W)


MAX_ARMIES_PER_CELL = 5   # the game lets at most 5 armies stand in one cell


def choose_meet(cells, owned, *, fallback: int | None = None, occupied=None,
                anchor: int | None = None, cap: int = MAX_ARMIES_PER_CELL) -> int | None:
    """The cell where armies standing at ``cells`` should meet: an OWNED cell (armies can
    only be sent into our own land) with ROOM for the arrivals (``cap`` armies per cell,
    ``occupied`` = armies standing on each cell now). Distance is Manhattan (the game
    marches along rows/columns). Default: minimise the longest march — usually halfway,
    or one army's own cell. With ``anchor`` (the cell of an army about to attack, which
    should not be pulled away from the front): the cell nearest to it — its own cell when
    there is room, else the closest owned cell — and the other army walks over.
    Ties: shorter longest/total march, fewer armies there, lower index. ``fallback`` (the
    main city) is always a candidate; None when no cell has room."""
    cells = [int(c) for c in cells]
    cand = {int(o) for o in owned or ()} | ({int(fallback)} if fallback else set())
    occ = occupied or {}
    pool = [c for c in cand
            if occ.get(c, 0) + sum(1 for x in cells if x != c) <= cap]
    if not pool or not cells:
        return None

    def tail(c):
        return (max(_dist(c, x) for x in cells), sum(_dist(c, x) for x in cells),
                occ.get(c, 0), c)
    if anchor is not None:
        return min(pool, key=lambda c: (_dist(c, int(anchor)),) + tail(c))
    return min(pool, key=tail)


def _lv(p: dict) -> int:
    return int(p.get("lv", 0) or 0)


def _pid(p: dict) -> int:
    return int(p.get("id", 0) or 0)


def _int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _pool(army: dict, pawn_id, pos: str = "lowest") -> list:
    """Movable pawns of a type (any type when None), best pick first, heroes never.
    ``pos``: "lowest" level first (default), "last" / "first" = by slot order — the
    player's 'the one at the END of the army' (the army's pawn list is in slot order)."""
    ps = [p for p in army.get("pawns") or []
          if not _is_hero(p) and (pawn_id is None or _pid(p) == pawn_id)]
    if pos == "last":
        return ps[::-1]
    if pos == "first":
        return ps
    return sorted(ps, key=_lv)


def _pos(v) -> str:
    return v if v in ("last", "first") else "lowest"


def reorder_swaps(army: dict, order) -> list:
    """Slot swaps ``[[uid1, uid2], ...]`` (applied in sequence) that put the pawn types
    listed in ``order`` first, in that order; the rest keep their relative order and
    heroes keep their slots. [] when the army is already in that order."""
    rank = {int(t): i for i, t in enumerate(order or [])}
    cur = list(army.get("pawns") or [])
    slots = [i for i, p in enumerate(cur) if not _is_hero(p)]
    want = sorted((cur[i] for i in slots), key=lambda p: rank.get(_pid(p), len(rank)))
    swaps = []
    for k, i in enumerate(slots):
        if str(cur[i].get("uid")) == str(want[k].get("uid")):
            continue
        j = next(j for j in slots[k + 1:] if str(cur[j].get("uid")) == str(want[k].get("uid")))
        swaps.append([str(cur[i].get("uid")), str(cur[j].get("uid"))])
        cur[i], cur[j] = cur[j], cur[i]
    return swaps


def _meet_for(meet, armies):
    """``meet`` is a fixed cell, or a callable ``armies -> cell`` (see ``choose_meet``)."""
    return meet(armies) if callable(meet) else meet


def _holder(armies, not_uid, pid, near):
    """The army (other than ``not_uid``) to take pawns of type ``pid`` from: idle ones first,
    then the one standing at ``near``, then the one holding the most of that type."""
    best = None
    for x in armies or []:
        if str(x.get("uid")) == str(not_uid):
            continue
        n = len(_pool(x, pid, None))
        if n < 1:
            continue
        key = (0 if not x.get("state") else 1, 0 if x.get("index") == near else 1, -n)
        if best is None or key < best[0]:
            best = (key, x)
    return best[1] if best else None


def sanitize_pawn_moves(raw, armies, cap: int = 9, meet=None,
                        pawn_names=None) -> tuple[list, list]:
    """Validate chat-proposed rearrangements into ``(clean, notices)``.

    The game only swaps/moves pawns between armies in the SAME cell (any cell: it must not
    be in battle and the armies must not be marching). ``meet`` = where to gather armies
    that are not (a cell, or a callable picking one from their cells, e.g. halfway): such
    an op is kept with ``gather: True`` and the queue calls the armies there first;
    without a meeting cell it is dropped with a notice.

    ``raw`` entries::

        {"op":"swap",   "army_a":uid, "pawn_a":id, "army_b":uid, "pawn_b":id, "count":n,
                        "pos_a":"last"|"first"?, "pos_b":"last"|"first"?}
        {"op":"move",   "army_from":uid, "army_to":uid|"new", "pawn_id":id?, "count":n,
                        "pos":"last"|"first"?}
        {"op":"reorder","army":uid, "order":[pawn id, ...]}
    """
    by_uid = {str(a.get("uid")): a for a in armies or []}
    out: list = []
    notes: list = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        op = r.get("op")
        count = max(1, _int(r.get("count"), 1) or 1)
        if op == "swap":
            a, b = by_uid.get(str(r.get("army_a"))), by_uid.get(str(r.get("army_b")))
            pa, pb = _int(r.get("pawn_a")), _int(r.get("pawn_b"))
            if a is None or pa is None or pb is None:
                notes.append("Không xác định được đội hoặc loại lính cần đổi — hãy nêu rõ tên đội và loại lính")
                continue
            # The player usually names ONE army ("thay 1 IMP cuối Đội 5 thành 1 Thợ Săn"): the
            # partner is whoever holds the other type — never a guess of the model's.
            tname = (pawn_names or {}).get(pb) or f"loại {pb}"
            if b is None or (b is not a and not _pool(b, pb, None)):
                held = _holder(armies, a.get("uid"), pb, a.get("index"))
                if held is None:
                    notes.append(f"Chưa có lính {tname} nào trong các đội — cần chiêu mộ trước "
                                 "rồi mới đổi được")
                    continue
                if b is not None:
                    notes.append(f"{b.get('name')} không có lính {tname} — lấy từ {held.get('name')}")
                b = held
            if a is b:
                notes.append(f"Hai bên đều là {a.get('name')} — muốn đổi thứ tự lính trong một đội "
                             "thì hãy nói 'đổi thứ tự', còn tráo thì cần hai đội khác nhau")
                continue
            gather = a.get("index") != b.get("index")
            at = _meet_for(meet, [a, b]) if gather else None
            if gather and at is None:
                notes.append(f"{a.get('name')} và {b.get('name')} không ở cùng ô và chưa chọn được ô để "
                             "gặp nhau (chưa đọc được danh sách đất của bạn — thử lại sau ít phút)")
                continue
            xs = _pool(a, pa, _pos(r.get("pos_a")))
            ys = _pool(b, pb, _pos(r.get("pos_b")))
            n = min(count, len(xs), len(ys))
            if n < 1:
                notes.append(f"{a.get('name')} không có lính {(pawn_names or {}).get(pa) or f'loại {pa}'}"
                             if not xs else f"{b.get('name')} không có lính {tname}")
                continue
            out.append({"op": "swap", "a": str(a["uid"]), "b": str(b["uid"]),
                        "name_a": a.get("name") or str(a["uid"]),
                        "name_b": b.get("name") or str(b["uid"]),
                        "index": int((at if gather else a.get("index", 0)) or 0),
                        "gather": gather, "meet": at,
                        "travel": [x.get("name") or str(x["uid"]) for x in (a, b)
                                   if gather and x.get("index") != at],
                        "stay": [x.get("name") or str(x["uid"]) for x in (a, b)
                                 if gather and x.get("index") == at],
                        "pawn_a": pa, "pawn_b": pb,
                        "count": n,
                        "pairs": [[str(xs[i]["uid"]), str(ys[i]["uid"])] for i in range(n)],
                        "spec": {"op": "swap", "army_a": str(a["uid"]), "pawn_a": pa,
                                 "army_b": str(b["uid"]), "pawn_b": pb, "count": n,
                                 "pos_a": _pos(r.get("pos_a")), "pos_b": _pos(r.get("pos_b"))}})
        elif op == "move":
            src = by_uid.get(str(r.get("army_from")))
            dst_uid = str(r.get("army_to"))
            dst = None if dst_uid == "new" else by_uid.get(dst_uid)
            pid = _int(r.get("pawn_id"))
            if src is None or (dst is None and dst_uid != "new") or dst is src:
                notes.append("Không xác định được đội nguồn / đội đích để chuyển lính")
                continue
            gather = dst is not None and src.get("index") != dst.get("index")
            at = _meet_for(meet, [src, dst]) if gather else None
            if gather and at is None:
                notes.append(f"{src.get('name')} và {dst.get('name')} không ở cùng ô và chưa chọn được ô "
                             "để gặp nhau (chưa đọc được danh sách đất của bạn — thử lại sau ít phút)")
                continue
            pool = _pool(src, pid, _pos(r.get("pos")))
            room = cap if dst is None else cap - len(dst.get("pawns") or [])
            target_name = dst.get("name") if dst else "đội mới"
            if room < 1:
                notes.append(f"{target_name} không còn chỗ (tối đa {cap} lính/đội)")
                continue
            n = min(count, len(pool), room)
            if n < min(count, len(pool)):
                notes.append(f"{target_name} chỉ còn chỗ cho {n} lính")
            if n < 1:
                notes.append(f"{src.get('name')} không có lính loại này để chuyển")
                continue
            out.append({"op": "move", "from": str(src["uid"]), "to": dst_uid,
                        "name_from": src.get("name") or str(src["uid"]),
                        "name_to": target_name or dst_uid,
                        "index": int((at if gather else src.get("index", 0)) or 0),
                        "gather": gather, "meet": at,
                        "travel": [x.get("name") or str(x["uid"]) for x in (src, dst)
                                   if gather and x.get("index") != at],
                        "stay": [x.get("name") or str(x["uid"]) for x in (src, dst)
                                 if gather and x.get("index") == at],
                        "pawn_id": pid, "count": n,
                        "pawn_uids": [str(p["uid"]) for p in pool[:n]],
                        "spec": {"op": "move", "army_from": str(src["uid"]), "army_to": dst_uid,
                                 "pawn_id": pid, "count": n, "pos": _pos(r.get("pos"))}})
        elif op == "reorder":
            a = by_uid.get(str(r.get("army")))
            order = [_int(t) for t in r.get("order") or [] if _int(t) is not None]
            if a is None or not order:
                notes.append("Không xác định được đội hoặc thứ tự lính cần đổi")
                continue
            swaps = reorder_swaps(a, order)
            if not swaps:
                notes.append(f"{a.get('name')} đã đúng thứ tự đó rồi")
                continue
            out.append({"op": "reorder", "army": str(a["uid"]),
                        "name": a.get("name") or str(a["uid"]),
                        "index": int(a.get("index", 0) or 0), "gather": False, "meet": None,
                        "order": order, "swaps": swaps,
                        "spec": {"op": "reorder", "army": str(a["uid"]), "order": order}})
    return out, notes


def _fold(text) -> str:
    """lower-case, no accents / spaces: 'Đội 5' -> 'doi5'."""
    import unicodedata
    t = unicodedata.normalize("NFD", str(text or "").lower().replace("đ", "d"))
    return "".join(c for c in t if not unicodedata.combining(c) and not c.isspace())


def mentioned_armies(message, armies):
    """``(resolved uids, unknown tokens)`` for the army names the player typed ('đội D3',
    'đội 5', 'D1'). A token that names no army is unknown — the brain may have guessed
    another one (live 2026-10-01: 'D1' did not exist and the brain picked Đội 5)."""
    import re
    keys = {_fold(a.get("name")): str(a.get("uid")) for a in armies or []}
    folded = unicodedata_fold_spaced(message)
    found, unknown = [], []
    for kind, num in re.findall(r"(?<![a-z0-9])(doi|d)\s*(\d+)(?![0-9])", folded):
        key = next((k for k in keys if re.fullmatch(rf"{kind}0*{int(num)}", k)), None)
        (found if key else unknown).append(keys[key] if key else
                                           ("D" if kind == "d" else "Đội ") + str(int(num)))
    return found, unknown


def unicodedata_fold_spaced(text) -> str:
    """lower-case without accents, keeping spaces (for tokenising a message)."""
    import unicodedata
    t = unicodedata.normalize("NFD", str(text or "").lower().replace("đ", "d"))
    return "".join(c for c in t if not unicodedata.combining(c))


def check_names(message, ops, armies) -> tuple[list, list]:
    """Drop proposals that contradict the army names the player typed: a name that matches
    no army (all dropped, with the list of existing names), or — when the message names
    exactly as many armies as an op involves — an op using other armies than those named."""
    found, unknown = mentioned_armies(message, armies)
    if unknown:
        names = ", ".join(str(a.get("name")) for a in armies or [])
        return [], [(f"Không có đội tên {', '.join(unknown)} (các đội hiện có: {names}) — "
                     "hãy nêu đúng tên đội.")]
    if not found:
        return list(ops), []
    keep, notes = [], []
    named = set(found)
    for m in ops:
        involved = ({m["a"], m["b"]} if m["op"] == "swap"
                    else {m["from"], m["to"]} - {"new"} if m["op"] == "move" else {m["army"]})
        if len(named) == len(involved) and involved != named:
            names = {str(a.get("uid")): a.get("name") for a in armies or []}
            notes.append("Bạn nhắc " + ", ".join(str(names.get(u)) for u in found)
                         + " nhưng đề xuất lại dùng " + ", ".join(str(names.get(u, u))
                                                                   for u in sorted(involved))
                         + " — hãy nói lại cho rõ.")
            continue
        keep.append(m)
    return keep, notes


def apply_moves(ops, armies) -> list:
    """The armies as they would be after ``ops`` (a copy; the input is untouched)."""
    new = copy.deepcopy(list(armies or []))
    by_uid = {str(a.get("uid")): a for a in new}

    def find(army, puid):
        for i, p in enumerate(army.get("pawns") or []):
            if str(p.get("uid")) == puid:
                return i
        return None

    for m in ops or []:
        if m["op"] == "swap":
            a, b = by_uid[m["a"]], by_uid[m["b"]]
            for ua, ub in m["pairs"]:
                i, j = find(a, ua), find(b, ub)
                if i is not None and j is not None:
                    a["pawns"][i], b["pawns"][j] = b["pawns"][j], a["pawns"][i]
        elif m["op"] == "move":
            src = by_uid[m["from"]]
            dst = by_uid.get(m["to"])
            if dst is None:
                dst = {"uid": f"new:{m['from']}", "name": m["name_to"],
                       "index": src.get("index"), "state": 0, "pawns": []}
                by_uid[m["to"]] = dst
                new.append(dst)
            for puid in m["pawn_uids"]:
                i = find(src, puid)
                if i is not None:
                    dst["pawns"].append(src["pawns"].pop(i))
        elif m["op"] == "reorder":
            a = by_uid[m["army"]]
            for u1, u2 in m["swaps"]:
                i, j = find(a, u1), find(a, u2)
                if i is not None and j is not None:
                    a["pawns"][i], a["pawns"][j] = a["pawns"][j], a["pawns"][i]
    return new


def _types(army: dict) -> Counter:
    return Counter(_pid(p) for p in army.get("pawns") or [] if not _is_hero(p))


def strike_conflicts(ops, armies, strike_uids) -> list:
    """What the active strike goal (ArmyComposer) would UNDO after ``ops``: a goal army
    ends up holding another pawn type, or loses pawns of its own type (it would pull
    them back). Reordering never conflicts. ``[]`` = nothing to undo."""
    strike = {str(u) for u in strike_uids or []}
    touched = set()
    for m in ops or []:
        if m["op"] == "swap":
            touched |= {m["a"], m["b"]}
        elif m["op"] == "move":
            touched |= {m["from"], m["to"]}
    touched &= strike
    if not touched:
        return []
    before = {str(a.get("uid")): a for a in armies or []}
    after = {str(a.get("uid")): a for a in apply_moves(ops, armies)}
    out = []
    for uid in sorted(touched):
        if uid not in before:
            continue
        was = _types(before[uid])
        if not was:
            continue
        slot = max(was, key=was.get)
        now = _types(after[uid])
        name = before[uid].get("name") or uid
        if any(t != slot for t in now):
            out.append(f"{name} sẽ lẫn loại lính khác (đội này đang là {slot})")
        elif now[slot] < was[slot]:
            out.append(f"{name} sẽ mất lính loại {slot}")
    return out
