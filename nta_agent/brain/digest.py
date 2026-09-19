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
    main = getattr(state, "main_city_index", 0)
    army_rows = []
    for a in (armies or []):
        comp = Counter(str(p.get("id")) for p in (a.get("pawns") or []))
        army_rows.append({"uid": str(a.get("uid")), "name": a.get("name"),
                          "index": int(a.get("index", 0) or 0),
                          "state": int(a.get("state", 0) or 0),
                          "pawns": len(a.get("pawns") or []), "composition": dict(comp)})
    logistics = getattr(profile, "logistics", {}) or {}
    # ready = topped-up, idle, at the city -> brain fills logistics.redeploy[uid]=index.
    from nta_agent.execution.logistics import ready_armies
    ready = [str(a.get("uid")) for a in ready_armies(
        armies or [], main, target=int(logistics.get("target", 9)))]
    player = (getattr(state, "raw", None) or {}).get("player") or {}
    out = {
        "main_city_index": main,
        "resources": res,
        "armies": army_rows,
        "ready_to_redeploy": ready,  # full+idle city armies awaiting a destination
        "injured": len(player.get("injuryPawns") or []),  # dead pawns awaiting revive
        "profile": {"army": profile.army, "occupy": profile.occupy,
                    "build": getattr(profile, "build", {}),
                    "revive": getattr(profile, "revive", {}),
                    "logistics": logistics},
        "notes": list(getattr(profile, "notes", []) or []),
    }
    if territory:  # owned/enemy/frontier summary so the brain can pick expansion + forts
        out["territory"] = territory
    dec = _decisions_digest(decisions)
    if dec:  # pending unlock/policy picks reserved for the human -> brain advises (E3)
        out["decisions"] = dec
    return out
