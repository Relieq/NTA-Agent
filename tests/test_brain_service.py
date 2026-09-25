import json
from types import SimpleNamespace

from nta_agent.brain.policies import BrainPolicy
from nta_agent.execution.profile import load_profile
from nta_agent.runtime.brain_service import BrainService

_RES = ("cereal", "timber", "stone", "iron", "gold", "stamina",
        "exp_book", "up_scroll", "fixator")


def _cfg(tmp_path):
    return SimpleNamespace(profile_path=tmp_path / "profile.json")


def _state():
    return SimpleNamespace(main_city_index=7,
                           resources=SimpleNamespace(**{k: 0 for k in _RES}), raw={})


def test_applies_sanitized_edits_in_place_and_emits(tmp_path):
    prof = load_profile("none")
    events = []
    actions = SimpleNamespace(get_player_armys=lambda: [{"uid": "A", "name": "D1", "pawns": []}])
    before_group = list(prof.army.get("group") or [])
    svc = BrainService(prof, _cfg(tmp_path), on_event=lambda k, d: events.append((k, d)),
                       actions=actions, policy=BrainPolicy(every_ticks=1, max_calls=5),
                       llm_propose=lambda dg, p: {"occupy": {"expansion": "octopus"},
                                                  "army": {"group": ["A"]}, "rationale": "tune"})
    svc.tick(_state())
    assert prof.occupy["expansion"] == "octopus"   # mutated in place
    assert prof.army.get("group") == before_group  # army is human-owned; brain ignores it
    assert any(k == "brain_plan" for k, d in events)
    assert (tmp_path / "profile.json").exists()  # persisted


def test_skips_off_cadence_and_survives_unavailable(tmp_path):
    from nta_agent.brain.llm import BrainUnavailable
    prof = load_profile("none")

    def boom(dg, p):
        raise BrainUnavailable("no key")

    svc = BrainService(prof, _cfg(tmp_path),
                       actions=SimpleNamespace(get_player_armys=list),
                       policy=BrainPolicy(every_ticks=10, max_calls=5), llm_propose=boom)
    svc.tick(_state())          # tick 1: off cadence -> no call, no raise
    for _ in range(9):
        svc.tick(_state())      # tick 10: fires but BrainUnavailable -> swallowed
    assert prof.occupy["max_loss"] == 0.0   # unchanged


def test_territory_summary_from_forts_json(tmp_path):
    import json
    fp = tmp_path / "forts.json"
    fp.write_text(json.dumps({
        "owned_count": 23, "enemy_cells": [[104, 100], [200, 200]],
        "enemy_cities": [{"x": 104, "y": 100, "type": 1}], "frontier": [[99, 100]],
        "recommendations": [],
    }), encoding="utf-8")
    cfg = SimpleNamespace(profile_path=tmp_path / "profile.json", forts_path=fp)
    svc = BrainService(load_profile("none"), cfg)
    st = SimpleNamespace(main_city_index=100 * 600 + 100)  # (100,100)
    terr = svc._territory(st)
    assert terr["owned"] == 23 and terr["enemy_cells"] == 2 and terr["frontier"] == 1
    assert terr["nearest_enemy_dist"] == 4  # (104,100) is 4 away


def test_territory_none_when_no_file(tmp_path):
    cfg = SimpleNamespace(profile_path=tmp_path / "p.json", forts_path=tmp_path / "missing.json")
    svc = BrainService(load_profile("none"), cfg)
    assert svc._territory(SimpleNamespace(main_city_index=1)) is None


def _cfg2(tmp_path):
    return SimpleNamespace(profile_path=tmp_path / "profile.json",
                           forts_path=tmp_path / "forts.json",
                           decisions_path=tmp_path / "decisions.json",
                           brain_advice_path=tmp_path / "brain_advice.json")


def test_writes_brain_advice(tmp_path):
    import json
    actions = SimpleNamespace(get_player_armys=list)
    svc = BrainService(load_profile("none"), _cfg2(tmp_path), actions=actions,
                       policy=BrainPolicy(every_ticks=1, max_calls=5),
                       llm_propose=lambda dg, p: {"advice": [{"text": "Nâng kho", "why": "sắp tràn"}]})
    svc.tick(_state())
    adv = json.loads((tmp_path / "brain_advice.json").read_text(encoding="utf-8"))
    assert adv == [{"text": "Nâng kho", "why": "sắp tràn"}]


def test_blocked_composition_surfaced_as_advice(tmp_path):
    import json
    cfg = _cfg2(tmp_path)
    cfg.composition_status_path = tmp_path / "composition_status.json"
    cfg.composition_status_path.write_text(
        json.dumps({"active": True, "blocked": True,
                    "issues": ["pawn 3305 chưa unlock — không chiêu mộ được 35 lính còn thiếu"]}),
        encoding="utf-8")
    actions = SimpleNamespace(get_player_armys=list)
    svc = BrainService(load_profile("none"), cfg, actions=actions,
                       policy=BrainPolicy(every_ticks=1, max_calls=5),
                       llm_propose=lambda dg, p: {"advice": []})
    svc.tick(_state())
    adv = json.loads((tmp_path / "brain_advice.json").read_text(encoding="utf-8"))
    assert adv and "3305" in adv[0]["text"]      # the block was relayed to the user


def test_event_trigger_fires_on_threat_off_cadence(tmp_path):
    import json
    cfg = _cfg2(tmp_path)
    cfg.forts_path.write_text(json.dumps({"threat_summary": {"count": 2}}), encoding="utf-8")
    calls = []
    actions = SimpleNamespace(get_player_armys=list)
    svc = BrainService(load_profile("none"), cfg, actions=actions,
                       policy=BrainPolicy(every_ticks=9999, max_calls=5),
                       llm_propose=lambda dg, p: (calls.append(1) or {}))
    svc.tick(_state())  # cadence not due, but a threat -> urgent -> fires
    assert calls == [1]


def test_no_fire_when_quiet_off_cadence(tmp_path):
    calls = []
    actions = SimpleNamespace(get_player_armys=list)
    svc = BrainService(load_profile("none"), _cfg2(tmp_path), actions=actions,
                       policy=BrainPolicy(every_ticks=9999, max_calls=5),
                       llm_propose=lambda dg, p: (calls.append(1) or {}))
    svc.tick(_state())  # no threat / no decisions -> not urgent -> no call
    assert calls == []


def test_brain_never_edits_build_order(tmp_path):
    """The LLM echoes build from the digest; the brain must strip it so the human's
    build.order/skip (set via dashboard) is never clobbered."""
    from pathlib import Path

    from nta_agent.execution.profile import load_profile as _load
    from nta_agent.execution.profile import save_profile as _save
    cfg = _cfg(tmp_path)
    Path(cfg.profile_path).parent.mkdir(parents=True, exist_ok=True)
    disk = _load(str(cfg.profile_path))               # the human's build, on disk
    disk.build = {"order": [2001, 2008], "skip": [2000]}
    _save(disk, str(cfg.profile_path))
    prof = _load(str(cfg.profile_path))
    actions = SimpleNamespace(get_player_armys=lambda: [{"uid": "A", "name": "D1", "pawns": []}])
    svc = BrainService(prof, cfg,
                       actions=actions, policy=BrainPolicy(every_ticks=1, max_calls=5),
                       llm_propose=lambda dg, p: {"build": {"order": [], "skip": []},
                                                  "occupy": {"expansion": "octopus"}})
    svc.tick(_state())
    saved = json.loads(Path(cfg.profile_path).read_text(encoding="utf-8"))
    assert saved["build"] == {"order": [2001, 2008], "skip": [2000]}  # untouched
    assert prof.occupy["expansion"] == "octopus"                     # other edits still apply


def test_brain_save_does_not_clobber_dashboard_build_edit(tmp_path):
    """Race: the dashboard writes a new build to disk after the tick started; the
    brain's save must not overwrite it with its stale in-memory build."""
    import json as _json
    from pathlib import Path
    prof = load_profile("none")
    prof.build = {"order": [1], "skip": []}          # brain's stale copy
    cfg = _cfg(tmp_path)
    Path(cfg.profile_path).parent.mkdir(parents=True, exist_ok=True)
    # "dashboard" wrote a newer build to disk mid-tick
    from nta_agent.execution.profile import load_profile as _load
    from nta_agent.execution.profile import save_profile as _save
    disk = _load(str(cfg.profile_path)); disk.build = {"order": [2001, 2004], "skip": [2000]}
    _save(disk, str(cfg.profile_path))
    actions = SimpleNamespace(get_player_armys=lambda: [{"uid": "A", "name": "D1", "pawns": []}])
    svc = BrainService(prof, cfg, actions=actions,
                       policy=BrainPolicy(every_ticks=1, max_calls=5),
                       llm_propose=lambda dg, p: {"occupy": {"expansion": "octopus"}})  # brain edit -> save
    svc.tick(_state())
    saved = _json.loads(Path(cfg.profile_path).read_text(encoding="utf-8"))
    assert saved["build"] == {"order": [2001, 2004], "skip": [2000]}  # dashboard's, not [1]
    assert saved["occupy"]["expansion"] == "octopus"                   # brain edit persisted


def test_brain_save_does_not_clobber_dashboard_farm_group(tmp_path):
    """The user sets the farm group (army.group) via the dashboard mid-tick; the
    brain's save must re-read it from disk, not overwrite it with its stale copy.
    Without this, leveling/occupy never see the group and never run."""
    import json as _json
    from pathlib import Path

    from nta_agent.execution.profile import load_profile as _load
    from nta_agent.execution.profile import save_profile as _save
    prof = load_profile("none")
    prof.army = {**prof.army, "group": []}            # brain's stale/empty copy
    cfg = _cfg(tmp_path)
    Path(cfg.profile_path).parent.mkdir(parents=True, exist_ok=True)
    # "dashboard" wrote the user's farm group to disk mid-tick
    disk = _load(str(cfg.profile_path))
    disk.army = {**disk.army, "group": ["1789811706664002", "1789755140946001"]}
    _save(disk, str(cfg.profile_path))
    actions = SimpleNamespace(get_player_armys=lambda: [{"uid": "A", "name": "D1", "pawns": []}])
    svc = BrainService(prof, cfg, actions=actions,
                       policy=BrainPolicy(every_ticks=1, max_calls=5),
                       llm_propose=lambda dg, p: {"occupy": {"expansion": "octopus"}})  # brain edit -> save
    svc.tick(_state())
    saved = _json.loads(Path(cfg.profile_path).read_text(encoding="utf-8"))
    assert saved["army"]["group"] == ["1789811706664002", "1789755140946001"]  # user's, not []
    assert saved["occupy"]["expansion"] == "octopus"                              # brain edit persisted


def test_brain_cannot_raise_max_loss_but_can_set_expansion(tmp_path):
    """max_loss is the user's hard risk cap; the brain must not raise it (would
    undo the no-loss policy). It may still pick the expansion pattern."""
    prof = load_profile("none")
    prof.occupy["max_loss"] = 0.0
    actions = SimpleNamespace(get_player_armys=lambda: [{"uid": "A", "name": "D1", "pawns": []}])
    svc = BrainService(prof, _cfg(tmp_path), actions=actions,
                       policy=BrainPolicy(every_ticks=1, max_calls=5),
                       llm_propose=lambda dg, p: {"occupy": {"max_loss": 7.4,
                                                             "expansion": "octopus"}})
    svc.tick(_state())
    assert prof.occupy["max_loss"] == 0.0        # user's cap kept
    assert prof.occupy["expansion"] == "octopus"  # pattern still brain-editable

def test_urgent_fires_on_new_battle_loss(tmp_path):
    from nta_agent.execution.ledger import FailureLedger
    led = FailureLedger(tmp_path / "failures.json")
    led.record("battle_loss", {"self_dead": 2, "counterfactual": {"best_order": "tank_first"}})
    cfg = SimpleNamespace(profile_path=tmp_path / "profile.json",
                          failures_path=tmp_path / "failures.json",
                          forts_path=tmp_path / "missing_forts.json",
                          decisions_path=tmp_path / "missing_dec.json",
                          res_pressure_window_s=3600, ledger_cap=100)
    svc = BrainService(load_profile("none"), cfg)
    assert svc._urgent(_state()) is True          # a new loss -> urgent
    assert svc._urgent(_state()) is False         # same loss already reacted to


def test_digest_carries_failures_to_the_llm(tmp_path):
    from nta_agent.execution.ledger import FailureLedger
    led = FailureLedger(tmp_path / "failures.json")
    led.record("battle_loss", {"self_dead": 1, "counterfactual": {"best_order": "tank_first"}})
    cfg = SimpleNamespace(profile_path=tmp_path / "profile.json",
                          failures_path=tmp_path / "failures.json",
                          forts_path=tmp_path / "nf.json", decisions_path=tmp_path / "nd.json",
                          res_pressure_window_s=3600, ledger_cap=100)
    seen = {}
    svc = BrainService(load_profile("none"), cfg,
                       actions=SimpleNamespace(get_player_armys=list),
                       policy=BrainPolicy(every_ticks=1, max_calls=5),
                       llm_propose=lambda dg, p: seen.update(dg) or {"rationale": "ok"})
    svc.tick(_state())
    assert seen["failures"][0]["counterfactual"]["best_order"] == "tank_first"

def _ledger_cfg(tmp_path):
    return SimpleNamespace(profile_path=tmp_path / "profile.json",
                           failures_path=tmp_path / "failures.json",
                           lessons_path=tmp_path / "lessons.json",
                           forts_path=tmp_path / "nf.json", decisions_path=tmp_path / "nd.json",
                           res_pressure_window_s=3600, ledger_cap=100, lessons_cap=50)


def test_specific_lesson_is_stored_but_not_globally_applied(tmp_path):
    # Inc 3: a lesson tied to a monster (trigger.match) is stored but NOT applied
    # globally — the hands apply it contextually when that monster is faced.
    from nta_agent.brain.lessons import LessonStore
    from nta_agent.execution.ledger import FailureLedger
    led = FailureLedger(tmp_path / "failures.json")
    eid = led.record("battle_loss", {"self_dead": 1})
    prof = load_profile("none")
    svc = BrainService(prof, _ledger_cfg(tmp_path),
                       actions=SimpleNamespace(get_player_armys=list),
                       policy=BrainPolicy(every_ticks=1, max_calls=5),
                       llm_propose=lambda dg, p: {"lessons": [{
                           "trigger": {"kind": "battle_loss", "match": {"monster_id": 4116}},
                           "diagnosis": "AoE spills to archers",
                           "resolution": {"lever_edits": {"occupy": {"policy": {"order": "tank_first"}}}},
                           "evidence": [eid]}], "rationale": "learn"})
    svc.tick(_state())
    assert prof.occupy["policy"]["order"] == "auto"               # NOT applied globally
    stored = LessonStore(tmp_path / "lessons.json").active()
    assert len(stored) == 1 and stored[0].evidence == [eid]       # but it IS stored


def test_broad_lesson_is_applied_globally(tmp_path):
    # A lesson with no match constraint is broad -> applied globally.
    from nta_agent.execution.ledger import FailureLedger
    led = FailureLedger(tmp_path / "failures.json")
    eid = led.record("battle_loss", {"self_dead": 1})
    prof = load_profile("none")
    svc = BrainService(prof, _ledger_cfg(tmp_path),
                       actions=SimpleNamespace(get_player_armys=list),
                       policy=BrainPolicy(every_ticks=1, max_calls=5),
                       llm_propose=lambda dg, p: {"lessons": [{
                           "trigger": {"kind": "battle_loss"},   # no match -> broad
                           "diagnosis": "we out-level rarely; lead tanks",
                           "resolution": {"lever_edits": {"occupy": {"policy": {"order": "tank_first"}}}},
                           "evidence": [eid]}], "rationale": "learn"})
    svc.tick(_state())
    assert prof.occupy["policy"]["order"] == "tank_first"         # broad -> global


def test_hallucinated_lesson_without_evidence_is_dropped(tmp_path):
    from nta_agent.brain.lessons import LessonStore
    from nta_agent.execution.ledger import FailureLedger
    FailureLedger(tmp_path / "failures.json")  # empty ledger
    svc = BrainService(load_profile("none"), _ledger_cfg(tmp_path),
                       actions=SimpleNamespace(get_player_armys=list),
                       policy=BrainPolicy(every_ticks=1, max_calls=5),
                       llm_propose=lambda dg, p: {"lessons": [{
                           "trigger": {"kind": "battle_loss"}, "diagnosis": "made up",
                           "resolution": {"lever_edits": {"revive": {"enabled": False}}},
                           "evidence": ["ghost"]}], "rationale": "x"})
    svc.tick(_state())
    assert LessonStore(tmp_path / "lessons.json").all() == []      # no evidence -> not stored


def test_urgent_fires_on_early_warning_alerts(tmp_path):
    """alerts.json level danger/captured (enemy march on us / city fell) or an
    approach in forts.json wakes the brain promptly — not on the next cadence."""
    ap = tmp_path / "alerts.json"
    cfg = SimpleNamespace(profile_path=tmp_path / "profile.json",
                          failures_path=tmp_path / "nf.json",
                          forts_path=tmp_path / "forts.json",
                          decisions_path=tmp_path / "nd.json", alerts_path=ap,
                          res_pressure_window_s=3600, ledger_cap=100)
    svc = BrainService(load_profile("none"), cfg)
    ap.write_text(json.dumps({"level": "ok"}), encoding="utf-8")
    assert svc._urgent(_state()) is False
    ap.write_text(json.dumps({"level": "danger", "incoming": [{"uid": "m1"}]}), encoding="utf-8")
    assert svc._urgent(_state()) is True
    ap.write_text(json.dumps({"level": "ok"}), encoding="utf-8")
    (tmp_path / "forts.json").write_text(json.dumps(
        {"threat_summary": {"count": 0, "approaching": True}}), encoding="utf-8")
    assert svc._urgent(_state()) is True


def test_autonomous_brain_cannot_set_a_strike_group(tmp_path):
    """A strike group moves/recruits/dismisses troops: only the player's confirmed
    chat request may set it (2026-09-25)."""
    prof = load_profile("none")
    actions = SimpleNamespace(get_player_armys=list)
    svc = BrainService(prof, _cfg(tmp_path), actions=actions,
                       policy=BrainPolicy(every_ticks=1, max_calls=5),
                       llm_propose=lambda dg, p: {"army": {"strike_target": [
                           {"pawn_id": 3305, "armies": 4, "size": 9}]}})
    svc.tick(_state())
    assert not prof.army.get("strike_target")


def test_lesson_levers_drop_strike_target():
    from nta_agent.brain.guard import _safe_lever_edits
    out = _safe_lever_edits({"army": {"strike_target": [{"pawn_id": 3305, "armies": 1}]},
                             "occupy": {"expansion": "spiral"}}, set(), None)
    assert "army" not in out and out["occupy"]["expansion"] == "spiral"
