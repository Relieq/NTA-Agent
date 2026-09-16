"""When the brain may call the LLM: sparse cadence + hard budget."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BrainPolicy:
    every_ticks: int = 60
    max_calls: int = 50

    def should_call(self, tick: int, calls_made: int) -> bool:
        return (calls_made < self.max_calls and tick > 0
                and tick % self.every_ticks == 0)
