"""Wear levelling inside an army: the pawns that lost the most hp swap places with same-type
pawns that still have plenty (player 2026-10-03), so a group whose front line is hurt can go on
without a trip to a heal node.

Same pawn type only (a tank is never swapped with an archer), and only with a pawn BEHIND it
(an earlier list slot reaches the front first among equal attack speeds, see ``formation``),
and only with one that has more current hp. Pairs are listed most-wounded first; the caller
tries 1, 2, ... pairs and keeps the smallest set the battle simulator calls clean.
"""
from __future__ import annotations

from nta_agent.execution.army_health import _hp


def balance_swaps(pawns, max_pairs: int = 6) -> list[list[tuple[str, str]]]:
    """Cumulative swap lists: element ``k-1`` holds the first ``k`` (wounded uid, healthy uid)
    pairs. Empty when no useful swap exists."""
    pawns = list(pawns or [])
    info = []
    for pos, p in enumerate(pawns):
        cur, mx = _hp(p)
        info.append((pos, str(p.get("uid") or ""), int(p.get("id", 0) or 0), cur, mx))
    wounded = sorted((x for x in info if x[1] and x[4] > 0 and x[3] < x[4]),
                     key=lambda x: (-(x[4] - x[3]), x[0]))
    used: set[int] = set()
    pairs: list[tuple[str, str]] = []
    for w in wounded:
        if w[0] in used:
            continue
        helpers = [h for h in info if h[1] and h[0] not in used and h[0] > w[0]
                   and h[2] == w[2] and h[3] > w[3]]
        if not helpers:
            continue
        h = max(helpers, key=lambda x: (x[3], -x[0]))
        used.update((w[0], h[0]))
        pairs.append((w[1], h[1]))
        if len(pairs) >= max_pairs:
            break
    return [pairs[:k] for k in range(1, len(pairs) + 1)]


def apply_swaps(pawns, swaps) -> list:
    """The pawn list after swapping each (uid, uid) pair's slots (the input is not touched)."""
    out = list(pawns or [])
    pos = {str(p.get("uid")): i for i, p in enumerate(out)}
    for a, b in swaps or ():
        i, j = pos.get(str(a)), pos.get(str(b))
        if i is None or j is None:
            continue
        out[i], out[j] = out[j], out[i]
        pos[str(a)], pos[str(b)] = j, i
    return out
