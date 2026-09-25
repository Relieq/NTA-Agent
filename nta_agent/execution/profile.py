"""Tactics profile: the contract the hands obey (army + occupy policy).

Persisted JSON with defaults; loaded each tick. Later authored by brain/chat
(Track B B3/B4); for now hand/dashboard-editable. See the Track B design.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PROFILE = {
    # army.strike_target = the BRAIN's army-composition goal: a list of
    #   {pawn_id, armies, size} (N armies of one pawn type). The ArmyComposer rule
    #   reconciles current armies toward it (rally/pull/recruit); [] = no goal.
    #   Distinct from army.composition (per-army recruit-fill map used by Recruit).
    #   ONE-SHOT: cleared once the group is assembled (composition_done); the brain or
    #   user sets a new goal when needed. home_city = the main city this profile's
    #   uid/cell-bound fields belong to — a new main city (re-created after capture)
    #   resets them (reset_for_new_game).
    "army": {"group": [], "roles": {}, "onetile": True, "composition": {},
             "strike_target": [], "active": "", "presets": {}, "home_city": 0},
    # occupy.policy is the BRAIN's tactical channel (hands execute it token-free).
    #   order = "auto" | "tank_first" | "dps_first": which army leads the attack
    #   (frame-0 front line). auto lets the planner pick the lowest-loss ordering;
    #   tank_first/dps_first force melee-first / archers-first. max_loss + army.group
    #   stay HUMAN-owned (hard risk cap + army pool); the brain shapes tactics within.
    "occupy": {"max_loss": 0.0, "max_march_ms": 0, "expansion": "none",
               "loot": {"enabled": True, "min_reward_per_chest": 0.0},
               "policy": {"order": "auto"}},
    "revive": {"enabled": True},
    # leveling: exp-book cycle over the FARM GROUP (army.group) + an agent-created
    # leveling army. max_leveling = how many pawns to buffer at once. Disabled
    # until configured. See memory nta-agent-forge-leveling.
    # groups = [{armies:[uid], mode:"direct"|"buffer", target_lv}] — leveling per
    # group (buffer mode: docs/superpowers/specs/2026-09-25-buffer-leveling-design.md);
    # empty = legacy: one direct group = the active formation.
    "leveling": {"enabled": False, "target_lv": 0, "max_leveling": 1, "groups": []},
    # logistics: consolidate under-strength field armies + bring them home to recruit.
    # redeploy = {armyUid: targetIndex} the brain fills to send topped-up armies out.
    # See docs/superpowers/specs/2026-09-19-army-logistics-design.md.
    "logistics": {"enabled": False, "target": 9, "heal_skip_frac": 0.2,
                  "exclude": [], "min_shortfall": 1, "redeploy": {}},
    # forge: auto-craft unlocked COMMON equipment when affordable (user: "agent làm").
    "forge": {"enabled": True},
    "notes": [],
    "build": {"order": [], "skip": []},
}


def _merge(base: dict, over: dict) -> dict:
    # deep-copy so the returned profile never shares mutable state with DEFAULT_PROFILE
    # (rules/brain mutate the profile in place).
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            out[k] = _merge(base[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


@dataclass
class Profile:
    army: dict
    occupy: dict
    notes: list
    build: dict
    revive: dict = field(default_factory=lambda: {"enabled": True})
    leveling: dict = field(default_factory=lambda: {"enabled": False, "target_lv": 0,
                                                    "max_leveling": 1, "groups": []})
    logistics: dict = field(default_factory=lambda: copy.deepcopy(
        DEFAULT_PROFILE["logistics"]))
    forge: dict = field(default_factory=lambda: {"enabled": True})


def load_profile(path) -> Profile:
    """Load the profile, deep-merged over defaults. Missing/invalid → defaults."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        data = {}
    merged = _merge(DEFAULT_PROFILE, data if isinstance(data, dict) else {})
    return Profile(army=merged["army"], occupy=merged["occupy"], notes=merged["notes"],
                   build=merged["build"], revive=merged["revive"], leveling=merged["leveling"],
                   logistics=merged["logistics"], forge=merged["forge"])


def reload_into(profile: Profile, path) -> Profile:
    """Refresh a live Profile's fields IN PLACE from disk. The agent loads the
    profile once at startup, but the dashboard edits profile.json in a separate
    process; without this the agent's stale copy would ignore those edits AND the
    brain's save would clobber them (e.g. build.skip getting reset). Rules share
    this object by reference, so we reassign its attributes rather than the object."""
    fresh = load_profile(path)
    for f in ("army", "occupy", "notes", "build", "revive", "leveling",
              "logistics", "forge"):
        setattr(profile, f, getattr(fresh, f))
    return profile


def save_profile(profile: Profile, path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"army": profile.army, "occupy": profile.occupy,
                             "notes": profile.notes, "build": profile.build,
                             "revive": getattr(profile, "revive", {"enabled": True}),
                             "leveling": getattr(profile, "leveling", {}),
                             "logistics": getattr(profile, "logistics", {}),
                             "forge": getattr(profile, "forge", {"enabled": True})},
                            ensure_ascii=False, indent=1), encoding="utf-8")


def clear_strike_target(path) -> None:
    """One-shot strike goal: drop army.strike_target ON DISK (the runner reloads the
    profile from disk every tick, so an in-memory clear alone would be undone)."""
    prof = load_profile(path)
    prof.army["strike_target"] = []
    save_profile(prof, path)


def reset_for_new_game(path, home_city: int) -> list[str]:
    """A new main city (re-created after capture = a fresh game) invalidates every
    field bound to the old armies/cells: army uids (group, roles, preset groups,
    logistics redeploy/exclude) and the strike goal. Settings (occupy policy, build
    order, leveling/forge toggles, preset NAMES) are kept. Returns cleared keys."""
    prof = load_profile(path)
    a, lg = prof.army, prof.logistics
    cleared = [k for k in ("strike_target", "group", "roles") if a.get(k)]
    a["strike_target"], a["group"], a["roles"] = [], [], {}
    for name, pre in list((a.get("presets") or {}).items()):
        if isinstance(pre, dict) and (pre.get("group") or pre.get("roles")):
            cleared.append(f"presets.{name}")
        a["presets"][name] = {**(pre if isinstance(pre, dict) else {}), "group": [], "roles": {}}
    for k, empty in (("redeploy", {}), ("exclude", [])):
        if lg.get(k):
            cleared.append(f"logistics.{k}")
        lg[k] = empty
    a["home_city"] = int(home_city)
    save_profile(prof, path)
    return cleared


def active_formation(profile: Profile) -> dict:
    """The active preset's formation, or the flat army fields when none is active."""
    name = (profile.army or {}).get("active") or ""
    preset = (profile.army.get("presets") or {}).get(name)
    src = preset if preset else profile.army
    return {"group": src.get("group", []), "roles": src.get("roles", {}),
            "onetile": src.get("onetile", True), "composition": src.get("composition", {})}


def leveling_groups(profile) -> list[dict]:
    """The leveling groups; legacy profiles (no groups) = one DIRECT group made of
    the active formation at ``leveling.target_lv`` (the previous behaviour)."""
    lv = getattr(profile, "leveling", None) or {}
    groups = [g for g in (lv.get("groups") or []) if isinstance(g, dict) and g.get("armies")]
    if groups:
        return [{"armies": [str(u) for u in g["armies"]],
                 "mode": "buffer" if g.get("mode") == "buffer" else "direct",
                 "target_lv": int(g.get("target_lv", lv.get("target_lv", 0)) or 0)}
                for g in groups]
    grp = [str(u) for u in (active_formation(profile).get("group") or [])]
    return [{"armies": grp, "mode": "direct", "target_lv": int(lv.get("target_lv", 0) or 0)}]         if grp else []


def apply_edits(profile: Profile, clean: dict) -> bool:
    """Merge sanitized edits (occupy/army/presets/notes/active) into the profile in
    place. Activating a preset syncs its fields into the flat army.*. Returns
    whether anything changed."""
    changed = False
    if isinstance(clean.get("occupy"), dict):
        for k, v in clean["occupy"].items():
            if profile.occupy.get(k) != v:
                profile.occupy[k] = v
                changed = True
    if isinstance(clean.get("army"), dict):
        for k, v in clean["army"].items():
            if k == "presets" and isinstance(v, dict):
                for name, preset in v.items():
                    if profile.army["presets"].get(name) != preset:
                        profile.army["presets"][name] = preset
                        changed = True
            elif profile.army.get(k) != v:
                profile.army[k] = v
                changed = True
    if "notes" in clean and clean["notes"] != profile.notes:
        profile.notes = list(clean["notes"])
        changed = True
    if isinstance(clean.get("build"), dict):
        for k, v in clean["build"].items():
            if profile.build.get(k) != v:
                profile.build[k] = list(v)
                changed = True
    if isinstance(clean.get("revive"), dict):
        rev = getattr(profile, "revive", None)
        if rev is None:
            profile.revive = rev = {}
        for k, v in clean["revive"].items():
            if rev.get(k) != v:
                rev[k] = v
                changed = True
    if isinstance(clean.get("leveling"), dict):
        lv = getattr(profile, "leveling", None)
        if lv is None:
            profile.leveling = lv = {}
        for k, v in clean["leveling"].items():
            if lv.get(k) != v:
                lv[k] = v
                changed = True
    if isinstance(clean.get("logistics"), dict):
        lg = getattr(profile, "logistics", None)
        if lg is None:
            profile.logistics = lg = {}
        for k, v in clean["logistics"].items():
            if lg.get(k) != v:
                lg[k] = v
                changed = True
    # A preset being active makes THAT preset the source of truth (active_formation
    # reads it). A direct formation edit — e.g. the farm-group picker posting
    # army.group — must therefore land in the active preset, or the preset->flat
    # sync below reverts it to the preset's (empty) group. Mirror edited formation
    # fields into the active preset first, then sync preset -> flat.
    active = profile.army.get("active") or ""
    presets = profile.army.get("presets") or {}
    edited_army = clean.get("army") if isinstance(clean.get("army"), dict) else {}
    if active in presets and isinstance(presets[active], dict):
        for k in ("group", "roles", "onetile", "composition"):
            if k in edited_army and presets[active].get(k) != edited_army[k]:
                presets[active][k] = edited_army[k]
                changed = True
    preset = presets.get(active)
    if preset:
        for k in ("group", "roles", "onetile", "composition"):
            if k in preset and profile.army.get(k) != preset[k]:
                profile.army[k] = preset[k]
                changed = True
    return changed


def composition_target(profile: Profile, area_armys: list, unlocked_ids,
                       composition: dict | None = None) -> tuple | None:
    """The biggest unmet composition gap as ``(army_uid, pawn_id)``, or None.

    Composition = {armyUid: {pawnId: targetCount}} — from ``composition`` when
    given (e.g. the active preset's), else ``profile.army.composition``. Only
    pawns in ``unlocked_ids`` are eligible; picks the largest positive gap.
    """
    comp = composition if composition is not None else ((profile.army or {}).get("composition") or {})
    unlocked = {int(x) for x in (unlocked_ids or [])}
    by_uid = {str(a.get("uid")): a for a in area_armys}
    best = None  # (gap, army_uid, pawn_id)
    for army_uid, targets in comp.items():
        army = by_uid.get(str(army_uid))
        have: dict[int, int] = {}
        for p in (army.get("pawns") if army else []) or []:
            have[int(p.get("id", 0))] = have.get(int(p.get("id", 0)), 0) + 1
        for pid_str, want in (targets or {}).items():
            pid = int(pid_str)
            if pid not in unlocked:
                continue
            gap = int(want) - have.get(pid, 0)
            if gap > 0 and (best is None or gap > best[0]):
                best = (gap, str(army_uid), pid)
    return (best[1], best[2]) if best else None
