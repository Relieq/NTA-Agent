"""Compact, token-cheap game summary for the brain prompt."""
from __future__ import annotations

from collections import Counter


def digest(state, profile, armies=None) -> dict:
    r = state.resources
    res = {k: getattr(r, k, 0) for k in
           ("cereal", "timber", "stone", "iron", "gold", "stamina",
            "exp_book", "up_scroll", "fixator")}
    army_rows = []
    for a in (armies or []):
        comp = Counter(str(p.get("id")) for p in (a.get("pawns") or []))
        army_rows.append({"uid": str(a.get("uid")), "name": a.get("name"),
                          "pawns": len(a.get("pawns") or []), "composition": dict(comp)})
    return {
        "main_city_index": getattr(state, "main_city_index", 0),
        "resources": res,
        "armies": army_rows,
        "profile": {"army": profile.army, "occupy": profile.occupy},
        "notes": list(getattr(profile, "notes", []) or []),
    }
