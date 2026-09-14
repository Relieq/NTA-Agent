"""Candidate formations for a melee army: which pawn stands in front (tanks).

Enemies target the closest pawn, so the front slot draws fire. We permute pawns
among the slots they already occupy — putting the beefiest pawn in front — and
let the sim score the options.
"""
from __future__ import annotations


def _max_hp(pawn: dict) -> int:
    hp = pawn.get("hp")
    if isinstance(hp, (list, tuple)) and hp:
        return int(hp[-1] if len(hp) > 1 else hp[0])
    if isinstance(hp, dict):
        return int(hp.get("1", hp.get("0", 0)))
    return 0


def slot_order(army: dict, target: int, map_width: int = 600) -> list[dict]:
    """Occupied slots ordered front->back (front = nearer the target approach)."""
    pts = [p["point"] for p in army.get("pawns", []) if p.get("point")]
    ai = int(army.get("index", 0))
    dx = (target % map_width) - (ai % map_width)
    dy = (target // map_width) - (ai // map_width)
    # Front = toward the target: sort by the coordinate that decreases distance.
    if abs(dx) >= abs(dy):
        key = (lambda pt: pt["x"]) if dx < 0 else (lambda pt: -pt["x"])
    else:
        key = (lambda pt: pt["y"]) if dy < 0 else (lambda pt: -pt["y"])
    return sorted(pts, key=key)


def candidate_formations(army: dict, target: int, map_width: int = 600):
    """[(label, {pawn_uid: point})]: beefy-front + keep; keep-only when trivial."""
    pawns = army.get("pawns") or []
    keep = {p["uid"]: p["point"] for p in pawns if p.get("point")}
    if len(pawns) < 2:
        return [("keep", keep)]
    out = [("keep", keep)]
    slots = slot_order(army, target, map_width)
    ranked = sorted(pawns, key=_max_hp, reverse=True)  # beefiest first
    beefy = {p["uid"]: slots[i] for i, p in enumerate(ranked) if i < len(slots)}
    if beefy and beefy != keep:
        out.insert(0, ("beefy-front", beefy))
    return out
