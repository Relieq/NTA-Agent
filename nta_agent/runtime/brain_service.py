"""Sparse thin-brain: periodically ask the LLM to edit the live profile."""
from __future__ import annotations

import sys

from nta_agent.brain.digest import digest
from nta_agent.brain.guard import sanitize_edits
from nta_agent.brain.llm import BrainUnavailable
from nta_agent.brain.policies import BrainPolicy
from nta_agent.execution.profile import apply_edits, save_profile


class BrainService:
    def __init__(self, profile, cfg, on_event=None, actions=None,
                 llm_propose=None, policy=None):
        self.profile = profile
        self.cfg = cfg
        self._on_event = on_event or (lambda *a: None)
        self.actions = actions
        self.policy = policy or BrainPolicy(
            every_ticks=getattr(cfg, "brain_every_ticks", 60),
            max_calls=getattr(cfg, "brain_max_calls", 50))
        if llm_propose is None:
            from nta_agent.brain import llm as _llm
            def llm_propose(dg, p):
                return _llm.propose(dg, p)
        self._propose = llm_propose
        self._tick = 0
        self._calls = 0
        self._off = False

    def tick(self, state) -> None:
        self._tick += 1
        if self._off or not self.policy.should_call(self._tick, self._calls):
            return
        try:
            armies = self.actions.get_player_armys() if self.actions else []
            dg = digest(state, self.profile, armies)
            edits = self._propose(dg, self.profile)
            valid = {str(a.get("uid")) for a in armies}
            clean = sanitize_edits(edits, self.profile, valid)
            changed = apply_edits(self.profile, clean)
            if changed:
                save_profile(self.profile, self.cfg.profile_path)
            self._calls += 1
            self._on_event("brain_plan", {"changed": changed,
                                          "rationale": (edits or {}).get("rationale", "")})
        except BrainUnavailable as e:
            self._off = True  # stop retrying this run
            sys.stderr.write(f"[brain] disabled: {e}\n")
        except Exception as e:  # never kill the loop
            sys.stderr.write(f"[brain] tick failed: {e}\n")
