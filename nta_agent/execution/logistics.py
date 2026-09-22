"""Army-logistics planner (pure): consolidate co-located armies, bring under-strength
armies home to recruit, and expose armies ready for the brain to redeploy.

The hands rule turns a :class:`LogisticsAction` into game calls; keeping the decision
pure makes it testable and auditable. Game constraints it encodes (verified from the
engine): a pawn moves between two armies on the SAME cell index (HD_ChangePawnArmy),
recruiting only fills an idle army AT the main city index, and an army is movable only
while idle (state NONE). See docs/superpowers/specs/2026-09-19-army-logistics-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from nta_agent.execution.army_health import _hp, army_wound_frac, is_idle


@dataclass
class LogisticsAction:
    kind: str                       # "consolidate" | "bring_home"
    index: int = 0                  # cell the action happens on
    from_uid: str = ""              # consolidate: donor army
    to_uid: str = ""                # consolidate: keeper army
    pawn_uids: list[str] = field(default_factory=list)  # consolidate: pawns to move
    army: dict | None = None        # bring_home: the AreaArmyInfo to march home


def _pawn_hp(p: dict) -> int:
    cur, _mx = _hp(p)
    return cur


def _count(a: dict) -> int:
    return len(a.get("pawns") or [])


def _eligible(armies, main_city, forts, exclude, heal_skip_frac):
    """Idle FIELD armies we may touch: not at the city, not on a fort, not excluded,
    and not wounded enough to need healing (that is HealRouting's job)."""
    forts = {int(f) for f in forts or []}
    exclude = {str(u) for u in exclude or []}
    out = []
    for a in armies or []:
        idx = int(a.get("index", 0) or 0)
        if not is_idle(a) or idx == main_city or idx in forts:
            continue
        if str(a.get("uid", "")) in exclude:
            continue
        if army_wound_frac(a) >= heal_skip_frac:
            continue
        out.append(a)
    return out


def plan_logistics(armies, main_city, forts=(), *, target=9, heal_skip_frac=0.2,
                   exclude=(), min_shortfall=1) -> LogisticsAction | None:
    """Next logistics action, or None. Consolidation is preferred (fewer trips):
    within a co-located group, move the highest-hp pawns into the fullest army until
    it is full; then the emptied/short army is brought home for Recruit to top up."""
    elig = _eligible(armies, main_city, forts, exclude, heal_skip_frac)
    if not elig:
        return None

    # --- consolidate: a co-located group with room to pack pawns into a keeper ---
    groups: dict[int, list] = {}
    for a in elig:
        groups.setdefault(int(a["index"]), []).append(a)
    for idx, group in groups.items():
        if len(group) < 2:
            continue
        keeper = max(group, key=_count)
        room = target - _count(keeper)
        if room <= 0:
            continue
        # pick the donor with the most pawns; move its highest-hp pawns into keeper.
        donors = [a for a in group if a["uid"] != keeper["uid"] and _count(a) > 0]
        if not donors:
            continue
        donor = max(donors, key=_count)
        ranked = sorted(donor.get("pawns") or [], key=_pawn_hp, reverse=True)
        move = ranked[:room]
        if not move:
            continue
        return LogisticsAction(kind="consolidate", index=idx,
                               from_uid=str(donor["uid"]), to_uid=str(keeper["uid"]),
                               pawn_uids=[str(p["uid"]) for p in move])

    # --- bring home: the neediest under-strength field army ---
    short = [a for a in elig if target - _count(a) >= min_shortfall]
    if not short:
        return None
    army = max(short, key=lambda a: target - _count(a))
    return LogisticsAction(kind="bring_home", index=int(army["index"]), army=army)


def ready_armies(armies, main_city, *, target=9) -> list[dict]:
    """Armies full, idle and at the main city — topped up and awaiting the brain's
    redeploy decision. Surfaced in the digest / dashboard, never auto-sent by hands."""
    out = []
    for a in armies or []:
        if (is_idle(a) and int(a.get("index", 0) or 0) == main_city
                and _count(a) >= target):
            out.append(a)
    return out
