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


def _failure_digest(e) -> dict:
    """Compact one FailureEvent (or dict) for the brain prompt."""
    eid = getattr(e, "id", None) or (e.get("id") if isinstance(e, dict) else None)
    kind = getattr(e, "kind", None) or (e.get("kind") if isinstance(e, dict) else None)
    ctx = getattr(e, "context", None)
    if ctx is None and isinstance(e, dict):
        ctx = e.get("context") or {}
    ctx = ctx or {}
    out = {"id": eid, "kind": kind}
    for k in ("cell", "rule", "resource", "self_dead", "aoe", "enemy_ids",
              "counterfactual", "goal", "detail"):
        if k in ctx:
            out[k] = ctx[k]
    return out


def _lesson_digest(lesson) -> dict:
    """Compact one active lesson (Lesson object or dict) for the brain prompt."""
    g = (lambda k: getattr(lesson, k, None)) if not isinstance(lesson, dict) else lesson.get
    return {"id": g("id"), "trigger": g("trigger"), "diagnosis": g("diagnosis"),
            "resolution": g("resolution")}


def digest(state, profile, armies=None, territory=None, decisions=None,
           failures=None, res_pressure=None, lessons=None) -> dict:
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
    # rally points = cells where the farm group (army.group) sits, with free slots
    # (<=5 armies/cell, engine DEFAULT_MAX_ARMY_COUNT) so the brain rallies a ready
    # army to a real destination instead of guessing an index (or its own cell).
    MAX_ARMIES_PER_CELL = 5
    group = {str(u) for u in ((getattr(profile, "army", {}) or {}).get("group") or [])}
    by_cell: dict[int, dict] = {}
    for a in (armies or []):
        idx = int(a.get("index", 0) or 0)
        c = by_cell.setdefault(idx, {"total": 0, "farm": 0})
        c["total"] += 1
        if str(a.get("uid")) in group:
            c["farm"] += 1
    rally = [{"index": idx, "farm_armies": c["farm"],
              "free_slots": max(0, MAX_ARMIES_PER_CELL - c["total"])}
             for idx, c in sorted(by_cell.items()) if c["farm"] > 0]
    player = (getattr(state, "raw", None) or {}).get("player") or {}
    out = {
        "main_city_index": main,
        "resources": res,
        "armies": army_rows,
        "ready_to_redeploy": ready,  # full+idle city armies awaiting a destination
        "rally_points": rally,       # farm-group cells + free slots to rally into
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
    if failures:  # real losses/blocks recorded by hands -> brain learns from them
        out["failures"] = [_failure_digest(e) for e in failures]
    if res_pressure:  # {resource: count} of recent insufficient-resource back-offs
        out["res_pressure"] = dict(res_pressure)
    if lessons:  # grounded lessons distilled from past failures (Inc 2)
        out["lessons"] = [_lesson_digest(le) for le in lessons]
    return out
