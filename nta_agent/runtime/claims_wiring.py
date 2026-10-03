"""Wire the ArmyClaims priority list into the rules (one place instead of ad-hoc lists).

Each rule that moves or reshapes armies gets a source returning the armies a HIGHER-priority
owner holds right now. ``occupy_cell`` keeps its own richer wiring in the runner (it also reads
the dig step and the composer's busy set) and ``recruit`` keeps its composer lock: its
"locked is non-empty" means "a strike group is being assembled", a different meaning.
"""
from __future__ import annotations

from nta_agent.execution.claims import ArmyClaims

# rule name -> (attribute the rule reads, the owner level it ranks at)
RULE_HOOKS = {
    "heal_routing": ("locked_source", "heal"),
    "logistics": ("locked_source", "logistics"),
    "spare_armies": ("excluded_source", "spares"),
    "leveling": ("excluded_source", "logistics"),
    "buffer_leveling": ("excluded_source", "buffers"),
    "army_composer": ("excluded_source", "composer"),
}


def wire_claims(rules, claims: ArmyClaims, composer=None) -> None:
    for rule in rules:
        hook = RULE_HOOKS.get(getattr(rule, "name", ""))
        if hook is not None:
            attr, owner = hook
            setattr(rule, attr, lambda o=owner: claims.blocked_for(o))
        if getattr(rule, "name", "") == "heal_routing":
            # a dig WAITS for its group to heal ("dig_heal_wait") and relies on HealRouting to
            # send it: the dig group is not held away from healing (the player's chat still is)
            rule.locked_source = lambda: (
                claims.blocked_for("heal") - (claims.held_by("dig") - claims.held_by("pawn_moves")))
        if getattr(rule, "name", "") == "buffer_leveling" and composer is not None:
            # lương: the composer's next recruit comes before a level-up
            rule.cereal_hold_source = lambda c=composer: int(getattr(c, "cereal_need", 0) or 0)


def recruit_locked(composer, others=frozenset()) -> set:
    """What the generic Recruit must stand down for: the composer's incomplete armies, the
    chat's pawn moves, and — the whole time a strike goal is being assembled — a marker,
    because the lock alone is empty while the composer waits for cereal to recruit into a
    NEW army (live 2026-10-03: Recruit spent that cereal on lone pawns -> stray D1/D2)."""
    out = set(getattr(composer, "locked_uids", set()) or ()) | set(others)
    if getattr(composer, "assembling", False):
        out.add("*composer-goal")
    return out
