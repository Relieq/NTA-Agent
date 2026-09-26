"""Deterministic forge decisions (equipment).

User rules (2026-09-18, see memory nta-agent-forge-leveling):
- Only forge COMMON equipment (``equipBase.exclusive_pawn`` empty); never the
  specialized (pawn-locked) ones.
- Baseline: craft (first-forge) each unlocked common equip (``craft_candidates``).
- For user-designated MAIN equips, recast toward a PER-ITEM threshold on the
  EFFECT rolls (value/odds; attack/hp don't count — user 2026-09-23) within a
  PER-ITEM iron budget. No RestoreForge (too costly) — we simply stop as soon as
  a roll meets the threshold, so we keep it.

Pure over the engine shapes (EquipInfo ``attrs``, equipBase/equipEffect rows via
lookups) — see ``parse_attrs`` for the attr layout (RE: engine updateAttr).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# CType -> resource name (engine enum, verified: 1 cereal,2 timber,3 stone,9 iron…).
CTYPE = {1: "cereal", 2: "timber", 3: "stone", 5: "gold", 7: "exp_book",
         9: "iron", 13: "up_scroll", 14: "fixator"}


def parse_cost(s) -> dict:
    """``"2,0,357|3,0,357|9,0,3"`` -> ``{"timber":357,"stone":357,"iron":3}``.

    Each ``ctype,_,amount`` segment; the resource name comes from :data:`CTYPE`."""
    out: dict[str, int] = {}
    for seg in str(s or "").split("|"):
        parts = seg.split(",")
        if len(parts) >= 3:
            try:
                name = CTYPE.get(int(parts[0]))
                if name:
                    out[name] = out.get(name, 0) + int(parts[-1])
            except (ValueError, TypeError):
                continue
    return out


def affordable(cost: dict, resources: dict) -> bool:
    return all(int(resources.get(k, 0) or 0) >= v for k, v in cost.items())


def craft_candidates(equip_slots, base_of, crafted_ids, *, novice=False, exclusive=False):
    """Unlocked equip slots to CRAFT (materialize) via the first forge.

    ``equip_slots``: ``player.equipSlots`` = ``{slotKey: {"id":?, "lv":n, ...}}``.
    A slot with a chosen ``id`` whose equip is COMMON and not yet in ``crafted_ids``
    yields a craft: uid ``"<id>_<lv>"`` (engine EquipSlotObj.uid = id_lv), with its
    forge cost. Exclusive (pawn-locked) equips only with ``exclusive=True`` — the
    player chose it on the dashboard (2026-09-26 spec); otherwise left alone."""
    out = []
    for slot in (equip_slots or {}).values():
        if not isinstance(slot, dict):
            continue
        eid = int(slot.get("id", 0) or 0)
        if not eid or eid in crafted_ids:
            continue
        base = base_of(eid) or {}
        if not is_common(base) and not exclusive:
            continue
        cost_key = "forge_cost_novice" if novice else "forge_cost"
        cost = parse_cost(base.get(cost_key) or base.get("forge_cost"))
        out.append({"uid": f"{eid}_{int(slot.get('lv', 0) or 0)}", "id": eid, "cost": cost})
    return out


def parse_range(s) -> tuple[int, int] | None:
    """``"6,15"`` -> ``(6, 15)``; empty/invalid -> None."""
    try:
        lo, hi = (int(x) for x in str(s).split(","))
        return lo, hi
    except (ValueError, TypeError):
        return None


def is_common(base: dict) -> bool:
    """Common equipment (agent may forge) is not locked to a pawn."""
    return not str((base or {}).get("exclusive_pawn", "") or "").strip()


_MARKUP = re.compile(r"</?c(?:olor=[^>]*)?>", re.IGNORECASE)  # Cocos rich-text tags


def equip_id(equip: dict) -> int:
    """The equipBase id. Live EquipInfo may omit ``id`` — the engine derives it from
    the uid ``"<id>_<lv>"`` (setId) — so fall back to the uid prefix."""
    try:
        eid = int((equip or {}).get("id") or 0)
    except (TypeError, ValueError):
        eid = 0
    if eid:
        return eid
    try:
        return int(str((equip or {}).get("uid", "")).split("_")[0])
    except (TypeError, ValueError):
        return 0


def parse_attrs(equip: dict) -> dict:
    """Engine EquipInfo ``attrs`` -> ``{attack, hp, effects:[{type, value, odds}]}``.

    Each attr is ``[kind, type, value, odds, smeltId]`` (engine updateAttr):
    kind 0 = main stat (type 1 hp / 2 attack), kind 2 = effect (type = equipEffect
    id, value, odds). Items may be ``{"attr": [...]}`` or bare lists."""
    out = {"attack": 0, "hp": 0, "effects": []}
    for a in (equip or {}).get("attrs") or []:
        arr = a.get("attr") if isinstance(a, dict) else a
        if not isinstance(arr, (list, tuple)) or len(arr) < 3:
            continue
        kind, typ, val = int(arr[0] or 0), int(arr[1] or 0), int(arr[2] or 0)
        if kind == 0:
            if typ == 1:
                out["hp"] += val
            elif typ == 2:
                out["attack"] += val
        elif kind == 2:
            odds = int(arr[3] or 0) if len(arr) > 3 else 0
            out["effects"].append({"type": typ, "value": val, "odds": odds})
    return out


def effect_quality(equip: dict, effect_row) -> float | None:
    """How good the equip's EFFECT rolls are, 0..1 (user: only effects matter).

    Mean position of every rolled effect number (value, odds) inside its
    ``equipEffect`` range; attack/hp are ignored. None when nothing is rangeable."""
    fracs = []
    for eff in parse_attrs(equip)["effects"]:
        row = effect_row(eff["type"]) or {}
        for key in ("value", "odds"):
            rng = parse_range(row.get(key, ""))
            if rng is None or rng[1] <= rng[0]:
                continue
            lo, hi = rng
            fracs.append(max(0.0, min(1.0, (eff[key] - lo) / (hi - lo))))
    return sum(fracs) / len(fracs) if fracs else None


def effect_values(equip: dict) -> dict:
    """``{effectType: {"value": v, "odds": o}}`` for the equip's current rolls."""
    return {e["type"]: {"value": e["value"], "odds": e["odds"]}
            for e in parse_attrs(equip)["effects"]}


def unmet_stats(equip: dict, target: dict, effect_row) -> list[str]:
    """Which of the target's criteria the current roll misses.

    Per-stat minimums (``target["mins"] = {"<type>.value"|"<type>.odds": min}``,
    user 2026-09-24): every set minimum must hold; a required effect that wasn't
    rolled counts as missed. Without mins, the legacy composite ``threshold`` on
    :func:`effect_quality` applies (reported as ``"quality"``)."""
    mins = (target or {}).get("mins") or {}
    if mins:
        vals = effect_values(equip)
        out = []
        for key, lo in mins.items():
            typ, _, stat = str(key).partition(".")
            try:
                cur = (vals.get(int(typ)) or {}).get(stat)
            except ValueError:
                cur = None
            if cur is None or cur < float(lo):
                out.append(str(key))
        return out
    q = effect_quality(equip, effect_row)
    if q is None:
        return []  # nothing rangeable to judge -> treat as done
    return [] if q >= float((target or {}).get("threshold", 1.0)) else ["quality"]


def target_met(equip: dict, target: dict, effect_row) -> bool:
    return not unmet_stats(equip, target, effect_row)


@dataclass
class RecastDecision:
    uid: str
    quality: float     # current effect quality (below the target)
    cost: dict         # full forge cost to pay ({} when this recast is free)
    iron: int          # iron charged to the item's budget (0 when free)
    free: bool
    unmet: list = None  # which criteria the current roll misses ("3.odds", "quality")
    kind: str = "recast"   # "recast" | "lock" (exclusive: lock a satisfied wanted line first)
    lock_effect: int = 0   # the effect type to lock when kind == "lock"
    fixator: int = 0       # fixators this recast costs (lock + smelted lines in the pool)


def _satisfied_lines(equip, mins) -> list[int]:
    """Natural (not smelted) effect types whose EVERY set minimum is met."""
    from nta_agent.execution.exclusive import natural_effects
    nat = {x["type"]: x for x in natural_effects(equip)}
    out = []
    for t, cur in nat.items():
        keys = [(k, lo) for k, lo in (mins or {}).items() if str(k).partition(".")[0] == str(t)]
        if keys and all(cur.get(str(k).partition(".")[2], -1) >= float(lo) for k, lo in keys):
            out.append(t)
    return out


def next_recast(equips, base_of, effect_row, targets, resources, *, busy=False,
                pools=None, smelting=False):
    """The next RECAST toward a user target, or None.

    ``equips``: raw EquipInfo dicts (player.equips). ``targets``: ``{uid:
    {threshold: 0..1, budget: iron}}``. A recast pays the equip's full
    ``forge_cost`` (timber/stone/iron…) unless ``nextForgeFree``; only the IRON part
    counts against the item's budget. Stops (None for that item) once its effect
    quality reaches the threshold — no RestoreForge, so the good roll is kept."""
    if busy or smelting or not targets:  # no forge while smelting (ecode.500237)
        return None
    from nta_agent.execution.exclusive import fixator_per_recast, is_exclusive, natural_effects
    by_uid = {str(e.get("uid")): e for e in (equips or []) if isinstance(e, dict)}
    for uid, cfg in targets.items():
        e = by_uid.get(str(uid))
        if e is None:
            continue
        eid = equip_id(e)
        base = base_of(eid) or {}
        excl = is_exclusive(base)
        if not is_common(base) and not excl:
            continue
        pool = (pools or {}).get(eid) if excl else None
        if excl and not pool:
            continue  # no per-match pool known -> can not judge an exclusive equip
        unmet = unmet_stats(e, cfg, effect_row)
        if not unmet:
            continue  # target reached -> keep this roll
        q = effect_quality(e, effect_row) or 0.0
        fixator = 0
        if excl:
            ok = _satisfied_lines(e, cfg.get("mins") or {})
            lock = int(e.get("lockEffect") or 0)
            if lock and lock in {x["type"] for x in natural_effects(e)}:
                if lock not in ok:
                    continue  # locked on an unwanted line: every recast would waste fixators
            elif ok:
                # a wanted line is in: lock it first (a setting, no cost), then pay
                # fixators to roll the other line (user 2026-09-26)
                return RecastDecision(uid=str(uid), quality=q, cost={}, iron=0, free=False,
                                      unmet=unmet, kind="lock", lock_effect=ok[0])
            fixator = fixator_per_recast(e, pool)
            if fixator and (fixator > int(cfg.get("fixator_budget", 0) or 0)
                            or fixator > int((resources or {}).get("fixator", 0) or 0)):
                continue
        free = bool(e.get("nextForgeFree"))
        cost = {} if free else parse_cost(base.get("forge_cost"))
        iron = int(cost.get("iron", 0))
        if not free and (iron > int(cfg.get("budget", 0) or 0)
                         or not affordable(cost, resources)):
            continue
        return RecastDecision(uid=str(uid), quality=q, cost=cost, iron=iron, free=free,
                              unmet=unmet, fixator=fixator)
    return None


def forge_view(equips, base_of, effect_row, targets, *, name_of=None, effect_text=None,
               pools=None):
    """Dashboard rows for the recast panel: every COMMON equip with its current
    effect rolls (filled text + ranges), effect quality, recast count, per-recast
    iron cost and the user's target. Pure; lookups injected."""
    targets = targets or {}
    rows = []
    for e in equips or []:
        if not isinstance(e, dict):
            continue
        eid = equip_id(e)
        base = base_of(eid) or {}
        from nta_agent.execution.exclusive import fixator_per_recast, is_exclusive, smelted_types
        excl = is_exclusive(base)
        if not is_common(base) and not excl:
            continue
        smelted = smelted_types(e)
        effs = []
        for eff in parse_attrs(e)["effects"]:
            row = effect_row(eff["type"]) or {}
            sfx = str(row.get("suffix") or "")
            tmpl = _MARKUP.sub("", (effect_text(eff["type"]) if effect_text else None) or "")
            text = (tmpl.replace("{0}", f"{eff['value']}{sfx}")
                        .replace("{1}", f"{eff['odds']}%")) if tmpl else ""
            effs.append({"type": eff["type"], "value": eff["value"], "odds": eff["odds"],
                         "value_range": list(parse_range(row.get("value", "")) or []),
                         "odds_range": list(parse_range(row.get("odds", "")) or []),
                         "text": text, "smelted": eff["type"] in smelted})
        q = effect_quality(e, effect_row)
        uid = str(e.get("uid"))
        # every effect this equip CAN roll (equipBase.effect "a|b|..."), so the user can
        # set per-stat minimums even for one not rolled right now
        cur = effect_values(e)
        possible = []
        # exclusive: this MATCH pool (HD_GetWorldRandomInfo), never equipBase.effect
        toks = ([str(t) for t in (pools or {}).get(eid) or []] if excl
                else str(base.get("effect", "") or "").split("|"))
        for tok in toks:
            tok = tok.strip()
            if not tok.lstrip("-").isdigit() or not int(tok):
                continue
            t = int(tok)
            row = effect_row(t) or {}
            tmpl = _MARKUP.sub("", (effect_text(t) if effect_text else None) or "")
            possible.append({"type": t, "current": cur.get(t),
                             "label": tmpl.replace("{0}", "[giá trị]").replace("{1}", "[tỉ lệ]")
                             or f"hiệu ứng #{t}",
                             "suffix": str(row.get("suffix") or ""),
                             "value_range": list(parse_range(row.get("value", "")) or []),
                             "odds_range": list(parse_range(row.get("odds", "")) or [])})
        target = targets.get(uid)
        unmet = unmet_stats(e, target, effect_row) if target else []
        rows.append({"uid": uid, "id": eid, "name": (name_of(eid) if name_of else None) or f"#{eid}",
                     "quality": None if q is None else round(q, 3),
                     "effects": effs, "possible": possible,
                     "recast_count": int(e.get("recastCount", 0) or 0),
                     "next_free": bool(e.get("nextForgeFree")),
                     "iron_cost": int(parse_cost(base.get("forge_cost")).get("iron", 0)),
                     "target": target, "met": bool(target) and not unmet, "unmet": unmet,
                     "exclusive": excl,
                     "pawn_id": int(base.get("exclusive_pawn") or 0) if excl else 0,
                     "lock_effect": int(e.get("lockEffect") or 0) if excl else 0,
                     "fixator_per_recast": (fixator_per_recast(e, (pools or {}).get(eid) or [])
                                            if excl else 0),
                     "pool_known": bool((pools or {}).get(eid)) if excl else True,
                     "blocked": _blocked(e, target) if excl else ""})
    return rows


def _blocked(equip, target) -> str:
    """Why the agent will not recast this exclusive equip (shown on the dashboard)."""
    from nta_agent.execution.exclusive import natural_effects
    lock = int((equip or {}).get("lockEffect") or 0)
    if not target or not lock or lock not in {x["type"] for x in natural_effects(equip)}:
        return ""
    if lock not in _satisfied_lines(equip, (target or {}).get("mins") or {}):
        return "đang khoá một dòng không mong muốn — đổi/bỏ khoá trong game"
    return ""
