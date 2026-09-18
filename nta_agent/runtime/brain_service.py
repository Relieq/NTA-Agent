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
        self._build_ids = None  # lazily-loaded valid build ids

    def _territory(self, state):
        """Compact owned/enemy/frontier summary from forts.json for the brain."""
        try:
            import json
            data = json.loads(self.cfg.forts_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        main = int(getattr(state, "main_city_index", 0) or 0)
        mx, my = main % 600, main // 600
        enemy = data.get("enemy_cells") or []
        nearest = min((abs(x - mx) + abs(y - my) for x, y in enemy), default=None)
        return {
            "owned": data.get("owned_count", 0),
            "enemy_cells": len(enemy),
            "enemy_cities": len(data.get("enemy_cities") or []),
            "frontier": len(data.get("frontier") or []),
            "nearest_enemy_dist": nearest,
            "fort_recommendations": len(data.get("recommendations") or []),
        }

    def _valid_build_ids(self):
        if self._build_ids is None:
            try:
                from nta_agent.data.config import GameConfig
                self._build_ids = set(GameConfig.load().in_city_build_ids())
            except Exception:
                self._build_ids = set()
        return self._build_ids or None

    def tick(self, state) -> None:
        self._tick += 1
        if self._off or not self.policy.should_call(self._tick, self._calls):
            return
        try:
            armies = self.actions.get_player_armys() if self.actions else []
            dg = digest(state, self.profile, armies, territory=self._territory(state))
            edits = self._propose(dg, self.profile)
            valid = {str(a.get("uid")) for a in armies}
            clean = sanitize_edits(edits, self.profile, valid,
                                   valid_build_ids=self._valid_build_ids())
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
