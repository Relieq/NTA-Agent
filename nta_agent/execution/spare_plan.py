"""Spare armies: sort their pawns into pure single-type armies (pure, no I/O).

User 2026-09-26: the spare (non-farm) armies should be reorganised into armies of
ONE pawn type where possible, mixed only when there aren't enough armies. The
pawns never leave the spare set — only moved (ChangePawnArmy into an army with
room) or swapped one-for-one (ExchangePawnArmy) between spares at the same cell.
"""
from __future__ import annotations

from collections import Counter

CAP = 9  # pawns per army (engine ARMY_PAWN_MAX_COUNT)


def _targets(armies, cap: int) -> list[Counter]:
    """Target composition per army slot: full pure armies of the commonest types
    first, then one army per leftover type while armies remain, the rest mixed."""
    counts = Counter(int(p["id"]) for a in armies for p in a.get("pawns") or [])
    n = len(armies)
    slots: list[Counter] = []
    left = Counter(counts)
    for t, c in counts.most_common():
        for _ in range(c // cap):
            if len(slots) < n:
                slots.append(Counter({t: cap}))
                left[t] -= cap
    rest = [(t, c) for t, c in left.most_common() if c > 0]
    free = n - len(slots)
    bins: list[Counter] = [Counter() for _ in range(free)]
    # one army per leftover type while there are armies for it; overflow -> mixed
    pure_n = free if len(rest) <= free else max(0, free - 1)
    for i, (t, c) in enumerate(rest):
        if i < pure_n:
            bins[i][t] += c
        else:  # first-fit into the remaining (mixed) armies
            while c > 0:
                b = min(range(free), key=lambda k: (sum(bins[k].values()) >= cap, -k))
                room = cap - sum(bins[b].values())
                take = min(room, c) if room > 0 else c
                bins[b][t] += take
                c -= take
    return slots + bins


def _assign(armies, slots: list[Counter]) -> dict[str, Counter]:
    """Give each army the target slot it already overlaps most (fewest moves)."""
    cur = {str(a["uid"]): Counter(int(p["id"]) for p in a.get("pawns") or []) for a in armies}
    free = set(cur)
    out: dict[str, Counter] = {}
    for slot in sorted(slots, key=lambda s: -sum(s.values())):
        best = max(sorted(free), key=lambda u: sum(min(cur[u][t], n) for t, n in slot.items()))
        out[best] = slot
        free.discard(best)
    return out


def purity_ops(armies, cap: int = CAP) -> list[tuple]:
    """Moves/swaps that turn ``armies`` into their target compositions:
    ``("move", from_uid, pawn_uid, to_uid)`` into an army with room, or
    ``("exchange", uid_a, pawn_a, uid_b, pawn_b)``."""
    if len(armies) < 2:
        return []
    target = _assign(armies, _targets(armies, cap))
    pawns = {str(a["uid"]): [dict(p) for p in a.get("pawns") or []] for a in armies}
    ops: list[tuple] = []
    for _ in range(200):
        comp = {u: Counter(int(p["id"]) for p in ps) for u, ps in pawns.items()}
        surplus = {u: comp[u] - target[u] for u in pawns}
        deficit = {u: target[u] - comp[u] for u in pawns}
        op = None
        for a in sorted(pawns):
            for t in sorted(surplus[a]):
                for b in sorted(pawns):
                    if b == a or deficit[b][t] <= 0:
                        continue
                    pa = next(p for p in pawns[a] if int(p["id"]) == t)
                    if len(pawns[b]) < cap:
                        op = ("move", a, str(pa["uid"]), b)
                    else:
                        ys = sorted(surplus[b], key=lambda y: (-deficit[a][y], y))
                        if not ys:
                            continue
                        pb = next(p for p in pawns[b] if int(p["id"]) == ys[0])
                        op = ("exchange", a, str(pa["uid"]), b, str(pb["uid"]))
                    break
                if op:
                    break
            if op:
                break
        if op is None:
            return ops
        ops.append(op)
        pawns = {a["uid"]: a["pawns"] for a in apply_ops(
            [{"uid": u, "pawns": ps} for u, ps in pawns.items()], [op])}
    return ops


def apply_ops(armies, ops) -> list[dict]:
    """The armies after ``ops`` (copies) — for planning and tests."""
    out = {str(a["uid"]): {**a, "pawns": [dict(p) for p in a.get("pawns") or []]} for a in armies}
    for op in ops:
        if op[0] == "move":
            _, src, pawn, dst = op
            p = next(p for p in out[src]["pawns"] if str(p["uid"]) == pawn)
            out[src]["pawns"].remove(p)
            out[dst]["pawns"].append(p)
        else:
            _, a, pa, b, pb = op
            ia = next(i for i, p in enumerate(out[a]["pawns"]) if str(p["uid"]) == pa)
            ib = next(i for i, p in enumerate(out[b]["pawns"]) if str(p["uid"]) == pb)
            out[a]["pawns"][ia], out[b]["pawns"][ib] = out[b]["pawns"][ib], out[a]["pawns"][ia]
    return list(out.values())
