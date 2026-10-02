"""Who may touch which army: one ordered list of owners instead of per-rule exclusion lists.

Several features move or reshape armies (the player's chat orders, a dig, the composer's strike
group, buffer swaps, spare sorting, healing, farming, logistics). Each registered **owner** says
which army uids it holds right now; a rule asking ``blocked_for(name)`` gets the armies held by
owners with a STRICTLY HIGHER priority (an owner never blocks itself, a lower one never blocks it).

Providers are read on every call, so they can read persisted state (``buffers.json``) and the
answer does not depend on the order the rules ran in this tick or on a restart.

Priority, highest first (user 2026-10-02): chat pawn moves, dig group, composer strike armies,
buffer swaps (buffers + armies stepping over), spares being gathered/sorted, heal, occupy/farm,
logistics/direct leveling.
"""
from __future__ import annotations

ORDER = ("pawn_moves", "dig", "composer", "buffers", "spares", "heal", "occupy", "logistics")


class ArmyClaims:
    def __init__(self, order=ORDER):
        self.order = tuple(order)
        self._providers: dict[str, object] = {}

    def register(self, owner: str, provider) -> None:
        """``provider()`` -> iterable of army uids ``owner`` holds now."""
        if owner not in self.order:
            raise ValueError(f"unknown owner {owner!r}")
        self._providers[owner] = provider

    def held_by(self, owner: str) -> set[str]:
        fn = self._providers.get(owner)
        if fn is None:
            return set()
        try:
            return {str(u) for u in (fn() or ())}
        except Exception:   # a broken provider never blocks (or unblocks) the others
            return set()

    def blocked_for(self, owner: str) -> set[str]:
        """Armies held by owners ranked above ``owner`` (``owner`` may be a rule name that is
        not itself an owner: then it ranks below every owner)."""
        cut = self.order.index(owner) if owner in self.order else len(self.order)
        out: set[str] = set()
        for o in self.order[:cut]:
            out |= self.held_by(o)
        return out
