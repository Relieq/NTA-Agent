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


def _lv(p: dict) -> int:
    return int(p.get("lv", 0) or 0)


def _pid(p: dict) -> int:
    return int(p.get("id", 0) or 0)


def _int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _pool(army: dict, pawn_id) -> list:
    """Movable pawns of a type (any type when None): lowest level first, heroes never."""
    ps = [p for p in army.get("pawns") or []
          if not _is_hero(p) and (pawn_id is None or _pid(p) == pawn_id)]
    return sorted(ps, key=_lv)


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


def sanitize_pawn_moves(raw, armies, cap: int = 9) -> tuple[list, list]:
    """Validate chat-proposed rearrangements into ``(clean, notices)``.

    ``raw`` entries::

        {"op":"swap",   "army_a":uid, "pawn_a":id, "army_b":uid, "pawn_b":id, "count":n}
        {"op":"move",   "army_from":uid, "army_to":uid|"new", "pawn_id":id?, "count":n}
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
            if a is None or b is None or a is b or pa is None or pb is None:
                continue
            if a.get("index") != b.get("index"):
                notes.append(f"{a.get('name')} và {b.get('name')} không ở cùng ô — "
                             "cần tập hợp về cùng một ô trước khi đổi lính")
                continue
            xs, ys = _pool(a, pa), _pool(b, pb)
            n = min(count, len(xs), len(ys))
            if n < 1:
                continue
            out.append({"op": "swap", "a": str(a["uid"]), "b": str(b["uid"]),
                        "name_a": a.get("name") or str(a["uid"]),
                        "name_b": b.get("name") or str(b["uid"]),
                        "index": int(a.get("index", 0) or 0), "pawn_a": pa, "pawn_b": pb,
                        "count": n,
                        "pairs": [[str(xs[i]["uid"]), str(ys[i]["uid"])] for i in range(n)]})
        elif op == "move":
            src = by_uid.get(str(r.get("army_from")))
            dst_uid = str(r.get("army_to"))
            dst = None if dst_uid == "new" else by_uid.get(dst_uid)
            pid = _int(r.get("pawn_id"))
            if src is None or (dst is None and dst_uid != "new") or dst is src:
                continue
            if dst is not None and src.get("index") != dst.get("index"):
                notes.append(f"{src.get('name')} và {dst.get('name')} không ở cùng ô — "
                             "cần tập hợp về cùng một ô trước khi chuyển lính")
                continue
            pool = _pool(src, pid)
            room = cap if dst is None else cap - len(dst.get("pawns") or [])
            target_name = dst.get("name") if dst else "đội mới"
            if room < 1:
                notes.append(f"{target_name} không còn chỗ (tối đa {cap} lính/đội)")
                continue
            n = min(count, len(pool), room)
            if n < min(count, len(pool)):
                notes.append(f"{target_name} chỉ còn chỗ cho {n} lính")
            if n < 1:
                continue
            out.append({"op": "move", "from": str(src["uid"]), "to": dst_uid,
                        "name_from": src.get("name") or str(src["uid"]),
                        "name_to": target_name or dst_uid,
                        "index": int(src.get("index", 0) or 0), "pawn_id": pid, "count": n,
                        "pawn_uids": [str(p["uid"]) for p in pool[:n]]})
        elif op == "reorder":
            a = by_uid.get(str(r.get("army")))
            order = [_int(t) for t in r.get("order") or [] if _int(t) is not None]
            if a is None or not order:
                continue
            swaps = reorder_swaps(a, order)
            if not swaps:
                continue
            out.append({"op": "reorder", "army": str(a["uid"]),
                        "name": a.get("name") or str(a["uid"]),
                        "index": int(a.get("index", 0) or 0), "order": order, "swaps": swaps})
    return out, notes


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
