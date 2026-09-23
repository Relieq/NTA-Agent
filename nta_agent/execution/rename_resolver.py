"""Deterministic resolver: turn a chat rename PLAN into concrete army renames.

The LLM (even a weak one) is only trusted to PARSE the request into a plan —
[{pawn, name}] pairs — mapping names like "rìu khiên" / "IMP" to pawn ids. The
HANDS then resolve which army each name goes to, by PURE composition, and ask the
player back when the request can't be uniquely satisfied. This keeps army
selection reliable regardless of the model (fixes "renamed the wrong army").
"""
from __future__ import annotations

_PAWN_LABEL = {"3206": "rìu khiên", "3305": "IMP"}


def _pure_pawn(army) -> str | None:
    """The single pawn id an army is made of, or None if mixed/empty."""
    ids = {str(p.get("id")) for p in (army.get("pawns") or []) if p.get("id") is not None}
    return next(iter(ids)) if len(ids) == 1 else None


def resolve_rename_plan(plan, armies):
    """(renames, question). renames = [{uid, name}]; question set (and renames empty)
    when a requested type can't be matched to exactly the right number of PURE armies."""
    want: dict[str, list[str]] = {}
    order: list[str] = []
    for item in plan or []:
        if not isinstance(item, dict):
            continue
        pawn = str(item.get("pawn", "")).strip()
        name = str(item.get("name", "")).strip()
        if not pawn or not name or len(name) > 12 or "\n" in name:
            continue
        if pawn not in want:
            want[pawn] = []
            order.append(pawn)
        want[pawn].append(name)
    if not want:
        return [], ""

    pure_by_pawn: dict[str, list[str]] = {}
    for a in armies or []:
        pp = _pure_pawn(a)
        if pp:
            pure_by_pawn.setdefault(pp, []).append(str(a.get("uid")))
    for uids in pure_by_pawn.values():
        uids.sort()   # deterministic assignment order

    renames: list[dict] = []
    for pawn in order:
        names = want[pawn]
        cands = pure_by_pawn.get(pawn, [])
        label = _PAWN_LABEL.get(pawn, f"pawn {pawn}")
        if len(cands) != len(names):
            return [], (f"Bạn cần {len(names)} đội {label} nhưng có {len(cands)} đội "
                        f"thuần loại đó. Cho tôi biết rõ đội nào (uid) cần đổi tên nhé.")
        renames.extend({"uid": uid, "name": nm} for uid, nm in zip(cands, names))
    return renames, ""
