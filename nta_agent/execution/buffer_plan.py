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


ARMY_PAWN_MAX = 9  # pawns per army (engine ARMY_PAWN_MAX_COUNT)


def _lv(p) -> int:
    return int(p.get("lv", 0) or 0)


def propose(group_armies, spare_armies, target_lv: int, *, rows, barracks_lv: int,
            exp_book: int, army_count: int, army_cap: int,
            buffer_size: int = ARMY_PAWN_MAX) -> dict:
    """A buffer set for leveling ``group_armies`` to ``target_lv``.

    One buffer per weak pawn type, sized to the weak count (≤ ``buffer_size``). A
    buffer reuses the spare holding most pawns of that type (renamed), fills from
    other spares (``merge``; when the base is full each incoming pawn swaps out one
    of its other-type pawns — ``swap_out``) and recruits the rest. New armies beyond
    the free slots → suggest dismissing the smallest unused spares (never applied
    without the player's approval). Costs follow ``pawn_cost``.
    """
    weak = demand(group_armies, target_lv)
    spares = {str(a["uid"]): a for a in spare_armies}
    used_pawns: set[str] = set()
    used_armies: set[str] = set()
    buffers: list[dict] = []
    new_armies = 0
    for n, (ptype, pawns) in enumerate(sorted(weak.items(), key=lambda kv: -len(kv[1])), 1):
        size = min(buffer_size, len(pawns))

        def of_type(a, ptype=ptype):
            return sorted((p for p in (a.get("pawns") or [])
                           if int(p["id"]) == ptype and str(p["uid"]) not in used_pawns),
                          key=lambda p: (-_lv(p), str(p["uid"])))
        ranked = sorted((a for u, a in spares.items() if u not in used_armies and of_type(a)),
                        key=lambda a: (-len(of_type(a)), str(a["uid"])))
        buf = {"name": f"Nâng Cấp {n}", "base_uid": "", "types": {ptype: size},
               "merge": [], "recruit": {}, "pawns": []}
        have = 0
        foreign: list[str] = []
        if ranked:
            base = ranked.pop(0)
            buf["base_uid"] = str(base["uid"])
            used_armies.add(buf["base_uid"])
            for p in of_type(base)[:size]:
                used_pawns.add(str(p["uid"]))
                buf["pawns"].append({"id": ptype, "lv": _lv(p)})
                have += 1
            foreign = [str(p["uid"]) for p in (base.get("pawns") or [])
                       if int(p["id"]) != ptype]
            room = buffer_size - len(base.get("pawns") or [])
        else:
            new_armies += 1
            room = buffer_size
        for src in ranked:
            for p in of_type(src):
                if have >= size:
                    break
                swap_out = None
                if room <= 0:
                    if not foreign:
                        break
                    swap_out = foreign.pop(0)
                else:
                    room -= 1
                used_pawns.add(str(p["uid"]))
                buf["merge"].append({"from_uid": str(src["uid"]), "pawn_uid": str(p["uid"]),
                                     "pawn_id": ptype, "swap_out": swap_out})
                buf["pawns"].append({"id": ptype, "lv": _lv(p)})
                have += 1
        if have < size:
            buf["recruit"] = {ptype: size - have}
            buf["pawns"] += [{"id": ptype, "lv": 1}] * (size - have)
        buffers.append(buf)

    dismiss: list[str] = []
    short = new_armies - max(0, army_cap - army_count)
    if short > 0:
        merged_from = {m["from_uid"] for b in buffers for m in b["merge"]}
        free = sorted((a for u, a in spares.items() if u not in used_armies and u not in merged_from),
                      key=lambda a: (len(a.get("pawns") or []), str(a["uid"])))
        dismiss = [str(a["uid"]) for a in free[:short]]

    books = time_s = 0
    blocked: set[int] = set()
    pawns_all = [(ptype, p["lv"]) for ptype, ps in weak.items() for p in ps]
    pawns_all += [(p["id"], p["lv"]) for b in buffers for p in b["pawns"]]
    for ptype, lv in pawns_all:
        c = pawn_cost(rows, ptype, lv, target_lv, barracks_lv)
        books += c["books"]
        time_s += c["time_s"]
        if c["blocked_at"] is not None:
            blocked.add(ptype)
    notes = []
    if books > exp_book:
        notes.append(f"thiếu sách exp: cần {books}, có {exp_book} — nâng theo đợt")
    if blocked:
        notes.append("Trại Lính chưa đủ cấp cho loại lính: " + ", ".join(map(str, sorted(blocked))))
    if short > len(dismiss):
        notes.append("không đủ ô đội: cần giải tán thêm hoặc tăng giới hạn đội")
    for b in buffers:
        b.pop("pawns")
    return {"buffers": buffers, "dismiss": dismiss, "books_needed": books,
            "books_have": int(exp_book), "time_s": time_s // 6, "blocked": sorted(blocked),
            "notes": notes}


def swap_pairs(main_army, buffer_army, target_lv: int) -> list[tuple[str, str]]:
    """(weak main pawn, ready buffer pawn) pairs of the SAME type — weakest main
    pawn first, each ready pawn used once."""
    ready: dict[int, list[str]] = {}
    for p in sorted(buffer_army.get("pawns") or [], key=lambda p: (-_lv(p), str(p["uid"]))):
        if _lv(p) >= target_lv:
            ready.setdefault(int(p["id"]), []).append(str(p["uid"]))
    out = []
    for p in sorted(main_army.get("pawns") or [], key=lambda p: (_lv(p), str(p["uid"]))):
        pool = ready.get(int(p["id"]))
        if _lv(p) < target_lv and pool:
            out.append((str(p["uid"]), pool.pop(0)))
    return out


def pick_target(group_armies, buffer_army, target_lv: int) -> str | None:
    """The main army the buffer improves most (most pairs, then lowest total lv)."""
    best = None
    for a in group_armies:
        n = len(swap_pairs(a, buffer_army, target_lv))
        if n:
            key = (-n, sum(_lv(p) for p in a.get("pawns") or []), str(a["uid"]))
            if best is None or key < best[0]:
                best = (key, str(a["uid"]))
    return best[1] if best else None


def meeting_cell(main_index: int, owned, occupancy: dict, cap: int = 5,
                 width: int = 600) -> int | None:
    """An owned 4-neighbour of the main army's cell with room for one more army."""
    x, y = main_index % width, main_index // width
    owned = set(owned)
    for c in sorted(ny * width + nx for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
                    if 0 <= nx < width and 0 <= ny < width):
        if c in owned and occupancy.get(c, 0) < cap:
            return c
    return None


def reshape(buffer_army, target_army, spares_at_city, target_lv: int) -> list[tuple[str, str, str]]:
    """Trades that make the buffer fit ``target_army``'s weak pawns by type:
    ``(buffer pawn out, spare army uid, spare pawn in)``. A buffer pawn of a type
    the target doesn't need (surplus, lowest level first) goes to a spare army in
    the city for a pawn of a type the buffer lacks (highest level first) — e.g. an
    IMP buffer takes one hunter to serve an 8 IMP + 1 hunter army."""
    need: dict[int, int] = {}
    for p in target_army.get("pawns") or []:
        if _lv(p) < target_lv:
            need[int(p["id"])] = need.get(int(p["id"]), 0) + 1
    have: dict[int, list[dict]] = {}
    for p in buffer_army.get("pawns") or []:
        have.setdefault(int(p["id"]), []).append(p)
    surplus: list[dict] = []
    for t, ps in have.items():
        extra = len(ps) - need.get(t, 0)
        if extra > 0:
            surplus += sorted(ps, key=lambda p: (_lv(p), str(p["uid"])))[:extra]
    surplus.sort(key=lambda p: (_lv(p), str(p["uid"])))
    deficit = {t: n - len(have.get(t, [])) for t, n in need.items() if n > len(have.get(t, []))}
    offers = sorted(((str(a["uid"]), p) for a in spares_at_city for p in (a.get("pawns") or [])
                     if int(p["id"]) in deficit),
                    key=lambda sp: (-_lv(sp[1]), sp[0], str(sp[1]["uid"])))
    out: list[tuple[str, str, str]] = []
    for spare_uid, sp in offers:
        t = int(sp["id"])
        if not surplus or deficit.get(t, 0) <= 0:
            continue
        out.append((str(surplus.pop(0)["uid"]), spare_uid, str(sp["uid"])))
        deficit[t] -= 1
    return out
