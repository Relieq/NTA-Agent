"""Candidate tank troop ORDERS: which pawn is first in the army list.

Battle positions come from advancing off a shared entry point; who acts first
(attackIndex = attackSpeed desc, ties broken by list order) reaches the front and
tanks. So the lever is the pawn ORDER in ``army.pawns``, applied via
``ExchangePawnArmy`` swaps. (Grid points do not reach battle — see the design's
Correction note.)
"""
from __future__ import annotations


def _max_hp(pawn: dict) -> int:
    hp = pawn.get("hp")
    if isinstance(hp, (list, tuple)) and hp:
        return int(hp[-1] if len(hp) > 1 else hp[0])
    if isinstance(hp, dict):
        return int(hp.get("1", hp.get("0", 0)))
    return 0


def candidate_orderings(army: dict) -> list[tuple[str, list[dict]]]:
    """[(label, ordered_pawns)]: beefy-first (HP desc) + keep; keep-only when trivial.

    A stable sort keeps equal-HP pawns in their current relative order, so
    beefy-first only reshuffles when HP actually differs.
    """
    pawns = list(army.get("pawns") or [])
    if len(pawns) < 2:
        return [("keep", pawns)]
    out = [("keep", pawns)]
    beefy = sorted(pawns, key=_max_hp, reverse=True)
    if [p.get("uid") for p in beefy] != [p.get("uid") for p in pawns]:
        out.insert(0, ("beefy-first", beefy))
    return out


def swaps_for(current_uids: list[str], target_uids: list[str]) -> list[tuple[str, str]]:
    """Selection-sort swaps (by uid) turning ``current`` order into ``target``.

    Each swap maps to one ExchangePawnArmy call. Returns [] when already ordered.
    """
    cur = list(current_uids)
    pos = {u: i for i, u in enumerate(cur)}
    swaps: list[tuple[str, str]] = []
    for i, want in enumerate(target_uids):
        if cur[i] == want:
            continue
        j = pos[want]
        a, b = cur[i], cur[j]
        swaps.append((a, b))
        cur[i], cur[j] = cur[j], cur[i]
        pos[a], pos[b] = j, i
    return swaps
