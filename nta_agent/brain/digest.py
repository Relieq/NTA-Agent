"""Compact, token-cheap game summary for the brain prompt."""
from __future__ import annotations

from collections import Counter


def _decisions_digest(decisions) -> list:
    """Compact pending reserved decisions (unlock/policy) for the brain to advise on."""
    out = []
    for d in decisions or []:
        opts = [{"id": o.get("id"), "name": o.get("name")} for o in (d.get("options") or [])]
        out.append({"track": d.get("track"), "lv": d.get("lv"), "options": opts})
    return out


def digest(state, profile, armies=None, territory=None, decisions=None) -> dict:
    r = state.resources
    res = {k: getattr(r, k, 0) for k in
           ("cereal", "timber", "stone", "iron", "gold", "stamina",
            "exp_book", "up_scroll", "fixator")}
    army_rows = []
    for a in (armies or []):
        comp = Counter(str(p.get("id")) for p in (a.get("pawns") or []))
        army_rows.append({"uid": str(a.get("uid")), "name": a.get("name"),
                          "pawns": len(a.get("pawns") or []), "composition": dict(comp)})
    player = (getattr(state, "raw", None) or {}).get("player") or {}
    out = {
        "main_city_index": getattr(state, "main_city_index", 0),
        "resources": res,
        "armies": army_rows,
        "injured": len(player.get("injuryPawns") or []),  # dead pawns awaiting revive
        "profile": {"army": profile.army, "occupy": profile.occupy,
                    "build": getattr(profile, "build", {}),
                    "revive": getattr(profile, "revive", {})},
        "notes": list(getattr(profile, "notes", []) or []),
    }
    if territory:  # owned/enemy/frontier summary so the brain can pick expansion + forts
        out["territory"] = territory
    dec = _decisions_digest(decisions)
    if dec:  # pending unlock/policy picks reserved for the human -> brain advises (E3)
        out["decisions"] = dec
    return out
