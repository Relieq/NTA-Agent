"""Validate + clamp LLM-proposed profile edits before applying."""
from __future__ import annotations

import types

_ROLES = {"archer", "tank"}
_EXPANSION = {"none", "spiral", "octopus", "hybrid"}
_OCCUPY_ORDER = {"auto", "tank_first", "dps_first"}
_LESSON_TRIGGER_KEYS = {"monster_id", "resource", "goal"}


def _num(v, lo, hi, default):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _formation(f: dict, valid: set) -> dict:
    """Validate one formation (group/roles/onetile/composition) against real uids."""
    out: dict = {}
    if isinstance(f.get("group"), list):
        out["group"] = [str(u) for u in f["group"] if str(u) in valid]
    if isinstance(f.get("roles"), dict):
        out["roles"] = {str(u): r for u, r in f["roles"].items()
                        if str(u) in valid and r in _ROLES}
    if "onetile" in f:
        out["onetile"] = bool(f["onetile"])
    if isinstance(f.get("composition"), dict):
        comp: dict = {}
        for u, targets in f["composition"].items():
            if str(u) in valid and isinstance(targets, dict):
                comp[str(u)] = {str(pid): int(_num(c, 0, 10 ** 6, 0))
                                for pid, c in targets.items()}
        out["composition"] = comp
    return out


def sanitize_edits(edits: dict, profile, valid_army_uids, valid_build_ids=None) -> dict:
    valid = {str(u) for u in (valid_army_uids or ())}
    out: dict = {}

    occ_in = edits.get("occupy") if isinstance(edits, dict) else None
    if isinstance(occ_in, dict):
        occ: dict = {}
        if "max_loss" in occ_in:
            occ["max_loss"] = _num(occ_in["max_loss"], 0, 100, profile.occupy["max_loss"])
        if "max_march_ms" in occ_in:
            occ["max_march_ms"] = int(_num(occ_in["max_march_ms"], 0, 10 ** 9, 0))
        if "expansion" in occ_in and str(occ_in["expansion"]) in _EXPANSION:
            occ["expansion"] = str(occ_in["expansion"])
        pol_in = occ_in.get("policy")
        if (isinstance(pol_in, dict) and "order" in pol_in
                and str(pol_in["order"]) in _OCCUPY_ORDER):
            occ["policy"] = {"order": str(pol_in["order"])}
        loot_in = occ_in.get("loot")
        if isinstance(loot_in, dict):
            loot: dict = {}
            if "enabled" in loot_in:
                v = loot_in["enabled"]
                loot["enabled"] = (v.lower() in ("1", "true", "yes")
                                   if isinstance(v, str) else bool(v))
            if "min_reward_per_chest" in loot_in:
                loot["min_reward_per_chest"] = _num(loot_in["min_reward_per_chest"], 0, 10 ** 9, 0)
            if loot:
                occ["loot"] = loot
        if occ:
            out["occupy"] = occ

    army_in = edits.get("army") if isinstance(edits, dict) else None
    if isinstance(army_in, dict):
        army: dict = _formation(army_in, valid)  # flat group/roles/onetile/composition
        # strike_target: the composition goal (list of {pawn_id, armies, size}) the
        # ArmyComposer reconciles toward. Validate shape; [] clears the goal.
        if isinstance(army_in.get("strike_target"), list):
            st = []
            for t in army_in["strike_target"]:
                if isinstance(t, dict) and t.get("pawn_id"):
                    pid = int(_num(t["pawn_id"], 1000, 99999, 0))
                    if pid:
                        st.append({"pawn_id": pid,
                                   "armies": int(_num(t.get("armies", 1), 1, 20, 1)),
                                   "size": int(_num(t.get("size", 9), 1, 9, 9))})
            army["strike_target"] = st
        if isinstance(army_in.get("presets"), dict):
            presets = {str(n): _formation(f, valid) for n, f in army_in["presets"].items()
                       if isinstance(f, dict)}
            if presets:
                army["presets"] = presets
        if "active" in army_in:
            name = str(army_in["active"])
            known = set(army.get("presets") or {}) | set(profile.army.get("presets") or {})
            if name == "" or name in known:
                army["active"] = name
        if army:
            out["army"] = army

    lv_in = edits.get("leveling") if isinstance(edits, dict) else None
    if isinstance(lv_in, dict):
        lv: dict = {}
        if "enabled" in lv_in:
            v = lv_in["enabled"]
            lv["enabled"] = (v.lower() in ("1", "true", "yes")
                             if isinstance(v, str) else bool(v))
        if "target_lv" in lv_in:
            lv["target_lv"] = int(_num(lv_in["target_lv"], 0, 1000, 0))
        if "max_leveling" in lv_in:
            lv["max_leveling"] = int(_num(lv_in["max_leveling"], 1, 50, 1))
        if lv:
            out["leveling"] = lv

    rev_in = edits.get("revive") if isinstance(edits, dict) else None
    if isinstance(rev_in, dict) and "enabled" in rev_in:
        v = rev_in["enabled"]
        out["revive"] = {"enabled": (v.lower() in ("1", "true", "yes")
                                     if isinstance(v, str) else bool(v))}

    lg_in = edits.get("logistics") if isinstance(edits, dict) else None
    if isinstance(lg_in, dict):
        lg: dict = {}
        if "enabled" in lg_in:
            v = lg_in["enabled"]
            lg["enabled"] = (v.lower() in ("1", "true", "yes")
                             if isinstance(v, str) else bool(v))
        if "target" in lg_in:
            lg["target"] = int(_num(lg_in["target"], 1, 50, 9))
        if "heal_skip_frac" in lg_in:
            lg["heal_skip_frac"] = _num(lg_in["heal_skip_frac"], 0, 1, 0.2)
        if "min_shortfall" in lg_in:
            lg["min_shortfall"] = int(_num(lg_in["min_shortfall"], 1, 50, 1))
        if isinstance(lg_in.get("exclude"), list):
            lg["exclude"] = [str(u) for u in lg_in["exclude"] if str(u) in valid]
        # redeploy: only known army uids -> a positive cell index
        if isinstance(lg_in.get("redeploy"), dict):
            rd = {}
            for uid, idx in lg_in["redeploy"].items():
                if str(uid) in valid:
                    n = int(_num(idx, 0, 10 ** 9, 0))
                    if n > 0:
                        rd[str(uid)] = n
            lg["redeploy"] = rd
        if lg:
            out["logistics"] = lg

    if isinstance(edits.get("advice"), list):
        advice = []
        for a in edits["advice"]:
            if isinstance(a, dict) and str(a.get("text", "")).strip():
                advice.append({"text": str(a["text"]).strip()[:200],
                               "why": str(a.get("why", "")).strip()[:200]})
        if advice:
            out["advice"] = advice[:10]

    if isinstance(edits.get("notes"), list):
        out["notes"] = [str(s).strip()[:200] for s in edits["notes"] if str(s).strip()][:20]

    # build.order/skip (the dashboard edits this; the brain must NOT — it strips
    # build from its own edits before calling here, see BrainService.tick).
    build_in = edits.get("build") if isinstance(edits, dict) else None
    if isinstance(build_in, dict) and valid_build_ids is not None:
        valid_b = {int(x) for x in valid_build_ids}
        b: dict = {}
        for key in ("order", "skip"):
            if isinstance(build_in.get(key), list):
                b[key] = [int(x) for x in build_in[key]
                          if isinstance(x, int) and int(x) in valid_b]
        if b:
            out["build"] = b
    return out


def _safe_lever_edits(lever, valid_army_uids, valid_build_ids) -> dict:
    """Run a lesson's proposed lever edits through the normal edit guard, then drop
    the human-owned parts (build, max_loss, army.group/roles/...) so a lesson can
    only auto-apply the SAME safe levers the brain may edit. army.strike_target is
    kept (the one army field the brain owns)."""
    dummy = types.SimpleNamespace(occupy={"max_loss": 0}, army={})
    clean = sanitize_edits(lever, dummy, valid_army_uids, valid_build_ids=valid_build_ids)
    clean.pop("build", None)
    clean.pop("advice", None)
    clean.pop("notes", None)
    army_e = clean.pop("army", None)
    if isinstance(army_e, dict) and isinstance(army_e.get("strike_target"), list):
        clean["army"] = {"strike_target": army_e["strike_target"]}
    if isinstance(clean.get("occupy"), dict):
        clean["occupy"].pop("max_loss", None)   # the user's hard risk cap — never a lesson
        if not clean["occupy"]:
            clean.pop("occupy")
    return clean


def sanitize_lessons(edits, ledger, valid_army_uids, valid_build_ids=None) -> list:
    """Validate LLM-proposed lessons into dicts ready for LessonStore.upsert.

    Anti-hallucination: a lesson is DROPPED unless its evidence cites at least one
    event that ``ledger.has(...)`` confirms is real. A resolution that only touches
    human-owned levers (or nothing) is downgraded to advice for the human."""
    raw = edits.get("lessons") if isinstance(edits, dict) else None
    if not isinstance(raw, list):
        return []
    out: list = []
    for le in raw:
        if not isinstance(le, dict):
            continue
        evidence = [str(e) for e in (le.get("evidence") or []) if ledger.has(str(e))]
        if not evidence:
            continue  # grounded-only: no real evidence -> not a lesson
        trig = le.get("trigger") or {}
        match = {k: v for k, v in (trig.get("match") or {}).items()
                 if k in _LESSON_TRIGGER_KEYS}
        trigger = {"kind": str(trig.get("kind", ""))}
        if match:
            trigger["match"] = match
        diagnosis = str(le.get("diagnosis", "")).strip()[:200]
        res_in = le.get("resolution") if isinstance(le.get("resolution"), dict) else {}
        resolution = None
        adv = res_in.get("advice")
        if isinstance(adv, str) and adv.strip():
            resolution = {"advice": adv.strip()[:200]}
        elif isinstance(res_in.get("lever_edits"), dict):
            lever = _safe_lever_edits(res_in["lever_edits"], valid_army_uids, valid_build_ids)
            if lever:
                resolution = {"lever_edits": lever}
        if resolution is None:            # human-owned-only or empty -> advise instead
            if not diagnosis:
                continue
            resolution = {"advice": diagnosis}
        item = {"trigger": trigger, "diagnosis": diagnosis, "resolution": resolution,
                "evidence": evidence}
        if le.get("validated_by"):
            item["validated_by"] = str(le["validated_by"])[:120]
        out.append(item)
    return out[:10]
