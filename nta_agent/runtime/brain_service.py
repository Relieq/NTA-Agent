"""Sparse thin-brain: periodically ask the LLM to edit the live profile."""
from __future__ import annotations

import sys

from nta_agent.brain.digest import digest
from nta_agent.brain.guard import sanitize_edits, sanitize_lessons
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
        self._last_call = -10**9
        self._off = False
        self._build_ids = None  # lazily-loaded valid build ids
        # B1: minimum ticks between event-triggered (urgent) calls, to bound tokens.
        self.min_gap = int(getattr(cfg, "brain_min_gap", 15))
        self._last_loss_id = None  # most recent battle_loss the brain has reacted to

    def _ledger(self):
        """Fresh read of the hands-written failure ledger (small file; reload each use).

        Returns None when no failures_path is configured (e.g. minimal test cfg)."""
        path = getattr(self.cfg, "failures_path", None)
        if path is None:
            return None
        from nta_agent.execution.ledger import FailureLedger
        return FailureLedger(path, cap=getattr(self.cfg, "ledger_cap", 100))

    def _lessons_store(self):
        """The distilled-lessons store, or None when no lessons_path is configured."""
        path = getattr(self.cfg, "lessons_path", None)
        if path is None:
            return None
        from nta_agent.brain.lessons import LessonStore
        return LessonStore(path, cap=getattr(self.cfg, "lessons_cap", 50))

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

    def _decisions(self, state):
        """Pending reserved unlock/policy picks (from decisions.json) for E3 advice."""
        try:
            import json
            return json.loads(self.cfg.decisions_path.read_text(encoding="utf-8")) or []
        except Exception:
            return []

    def _urgent(self, state) -> bool:
        """B1: an event that warrants calling the brain promptly (not just cadence)."""
        try:
            import json
            forts = json.loads(self.cfg.forts_path.read_text(encoding="utf-8"))
        except Exception:
            forts = {}
        if (forts.get("threat_summary") or {}).get("count"):
            return True  # enemy touching our border
        player = (getattr(state, "raw", None) or {}).get("player") or {}
        if len(player.get("injuryPawns") or []) >= 5:
            return True  # heavy casualties
        led = self._ledger()
        if led is not None:
            recent_loss = led.recent(1, kind="battle_loss")
            if recent_loss and recent_loss[0].id != self._last_loss_id:
                self._last_loss_id = recent_loss[0].id
                return True  # a new grounded battle loss to learn from
            if sum(led.aggregate_res(
                    getattr(self.cfg, "res_pressure_window_s", 3600)).values()) >= 5:
                return True  # sustained resource pressure
        return bool(self._decisions(state))  # a reserved decision awaits a recommendation

    def _composition_advice(self) -> list:
        """If the ArmyComposer flagged the strike-group goal infeasible, relay it to the
        user as advice (deterministic — not LLM-dependent), so a request that can't be
        met (e.g. a pawn type isn't unlocked, or it exceeds the army cap) is surfaced."""
        path = getattr(self.cfg, "composition_status_path", None)
        if path is None:
            return []
        try:
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not (isinstance(data, dict) and data.get("blocked")):
            return []
        issues = data.get("issues") or []
        if not issues:
            return []
        return [{"text": "Không tạo được nhóm quân theo yêu cầu: " + "; ".join(issues),
                 "why": "army composition blocked — cần bạn xử lý (mở binh chủng / tăng slot đội)"}]

    def _write_advice(self, advice) -> None:
        try:  # best-effort: never let advice I/O break the brain tick
            import json
            import os
            path = self.cfg.brain_advice_path
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(advice, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except Exception as e:
            sys.stderr.write(f"[brain] advice write failed: {e}\n")

    def _refresh_human_fields(self) -> None:
        """Re-read the dashboard-owned sections the brain never edits (build,
        leveling, forge, army) from disk into the shared profile, right before
        saving, so the brain's save can't clobber a dashboard edit made mid-tick.
        army holds the user's farm group (FarmGroupPanel), which leveling/occupy
        read but the brain must not overwrite."""
        try:
            from nta_agent.execution.profile import load_profile
            disk = load_profile(self.cfg.profile_path)
            for f in ("build", "leveling", "forge", "army"):
                if f == "army":
                    # army.strike_target is the brain's goal — keep the just-set value;
                    # take the human-owned army fields (group/roles/...) from disk.
                    brain_strike = (getattr(self.profile, "army", {}) or {}).get("strike_target")
                    setattr(self.profile, f, getattr(disk, f))
                    if brain_strike is not None:
                        self.profile.army["strike_target"] = brain_strike
                else:
                    setattr(self.profile, f, getattr(disk, f))
        except Exception:
            pass

    def _valid_build_ids(self):
        if self._build_ids is None:
            try:
                from nta_agent.data.config import GameConfig
                self._build_ids = set(GameConfig.load().in_city_build_ids())
            except Exception:
                self._build_ids = set()
        return self._build_ids or None

    def _should_fire(self, state) -> bool:
        if self._off or self._calls >= self.policy.max_calls:
            return False
        if self.policy.should_call(self._tick, self._calls):
            return True  # regular cadence
        # B1: event-driven — fire on urgency, but no more than once per min_gap.
        return (self._tick - self._last_call) >= self.min_gap and self._urgent(state)

    def tick(self, state) -> None:
        self._tick += 1
        if not self._should_fire(state):
            return
        try:
            armies = self.actions.get_player_armys() if self.actions else []
            led = self._ledger()
            store = self._lessons_store()
            dg = digest(state, self.profile, armies, territory=self._territory(state),
                        decisions=self._decisions(state),
                        failures=led.recent(8) if led else None,
                        res_pressure=(led.aggregate_res(
                            getattr(self.cfg, "res_pressure_window_s", 3600)) if led else None),
                        lessons=store.active() if store else None)
            edits = self._propose(dg, self.profile)
            # build.order/skip and army.group are the human's plan (set via the
            # dashboard). The LLM echoes them from the digest; the valid-id/uid
            # filter then emptied them — wiping the user's build order and farm
            # group every brain run. The brain never edits these; it advises via
            # `advice` instead. occupy.max_loss is the user's hard risk cap ("0
            # tổn thất"): the brain may pick the expansion PATTERN but must not
            # raise the loss tolerance, so strip max_loss too (keep the rest of
            # occupy brain-editable).
            if isinstance(edits, dict):
                edits.pop("build", None)
                # army.* is human-owned EXCEPT strike_target (the brain's composition
                # goal) — keep only that from the brain's army edits, drop the rest.
                army_e = edits.pop("army", None)
                if isinstance(army_e, dict) and isinstance(army_e.get("strike_target"), list):
                    edits["army"] = {"strike_target": army_e["strike_target"]}
                if isinstance(edits.get("occupy"), dict):
                    edits["occupy"].pop("max_loss", None)
            valid = {str(a.get("uid")) for a in armies}
            clean = sanitize_edits(edits, self.profile, valid,
                                   valid_build_ids=self._valid_build_ids())
            changed = apply_edits(self.profile, clean)
            # Lessons: distill grounded lessons, auto-apply their SAFE lever fixes
            # (hỗn hợp autonomy — guard already downgraded human-owned fixes to advice),
            # and relay any advice. sanitize_lessons drops lessons without real evidence.
            lesson_advice: list = []
            if store is not None and led is not None:
                for lz in sanitize_lessons(edits, led, valid,
                                           valid_build_ids=self._valid_build_ids()):
                    store.upsert(lz)
                    res = lz.get("resolution") or {}
                    # A lesson tied to a specific situation (trigger.match) is applied
                    # CONTEXTUALLY by the hands when that situation recurs (Inc 3), not
                    # globally. Only broad lessons (no match) change the profile globally.
                    has_match = bool((lz.get("trigger") or {}).get("match"))
                    if isinstance(res.get("lever_edits"), dict):
                        if not has_match and apply_edits(self.profile, res["lever_edits"]):
                            changed = True
                    elif res.get("advice"):
                        lesson_advice.append({"text": res["advice"],
                                              "why": "lesson: " + (lz.get("diagnosis") or "")})
            if changed:
                # Human-owned config (build, leveling, forge, army) is edited by the
                # dashboard in another process. Even though the brain never edits it,
                # saving the whole profile would write our possibly-stale copy and
                # clobber a dashboard edit made since this tick started. Re-read those
                # sections from disk right before saving so the latest dashboard wins.
                self._refresh_human_fields()
                save_profile(self.profile, self.cfg.profile_path)
            advice = list(clean.get("advice") or []) + lesson_advice
            advice = self._composition_advice() + advice  # relay an infeasible comp goal
            self._write_advice(advice)  # B2: human-facing recommendations
            self._calls += 1
            self._last_call = self._tick
            self._on_event("brain_plan", {"changed": changed, "advice": len(advice),
                                          "rationale": (edits or {}).get("rationale", "")})
        except BrainUnavailable as e:
            self._off = True  # stop retrying this run
            sys.stderr.write(f"[brain] disabled: {e}\n")
        except Exception as e:  # never kill the loop
            sys.stderr.write(f"[brain] tick failed: {e}\n")
