"""New main city (re-created after capture) -> reset stale uid/cell-bound state."""
import json
from types import SimpleNamespace

from nta_agent.execution.profile import load_profile
from nta_agent.runtime.new_game import check_new_game


def _cfg(tmp_path):
    return SimpleNamespace(profile_path=tmp_path / "profile.json",
                           pending_forts_path=tmp_path / "pending_forts.json",
                           fort_decisions_path=tmp_path / "fort_decisions.json")


def test_first_run_records_home_without_reset(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.profile_path.write_text(json.dumps({"army": {"group": ["u1"]}}), encoding="utf-8")
    prof = load_profile(cfg.profile_path)
    assert check_new_game(prof, cfg, SimpleNamespace(main_city_index=71372)) is False
    assert prof.army["home_city"] == 71372 and prof.army["group"] == ["u1"]
    assert load_profile(cfg.profile_path).army["home_city"] == 71372   # persisted


def test_changed_main_city_resets(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.profile_path.write_text(json.dumps({"army": {
        "home_city": 326479, "group": ["old"],
        "strike_target": [{"pawn_id": 3206, "armies": 1, "size": 9}]}}), encoding="utf-8")
    cfg.pending_forts_path.write_text("[331273]", encoding="utf-8")
    cfg.fort_decisions_path.write_text(json.dumps({"331273": "rejected"}), encoding="utf-8")
    prof = load_profile(cfg.profile_path)
    events = []
    assert check_new_game(prof, cfg, SimpleNamespace(main_city_index=71372),
                          on_event=lambda k, d: events.append((k, d))) is True
    assert prof.army["strike_target"] == [] and prof.army["group"] == []   # in-memory too
    assert prof.army["home_city"] == 71372
    assert json.loads(cfg.pending_forts_path.read_text(encoding="utf-8")) == []
    assert json.loads(cfg.fort_decisions_path.read_text(encoding="utf-8")) == {}
    assert events[0][0] == "new_game_reset"
    assert events[0][1]["from"] == 326479 and events[0][1]["to"] == 71372
    # idempotent: same city next tick -> nothing
    assert check_new_game(prof, cfg, SimpleNamespace(main_city_index=71372)) is False


def test_no_main_city_is_noop(tmp_path):
    cfg = _cfg(tmp_path)
    prof = load_profile(cfg.profile_path)
    assert check_new_game(prof, cfg, SimpleNamespace(main_city_index=0)) is False


# ---- 2026-09-30: a new match kept the old match's leveling / forge / dig / buffers -----
def test_new_match_resets_everything_bound_to_the_old_one(tmp_path):
    from nta_agent.runtime.config import RuntimeConfig
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    cfg.profile_path.write_text(json.dumps({
        "army": {"home_city": 326479, "group": ["old"], "composition": {"3305": 9},
                 "onetile": False, "active": "Tank Formation",
                 "presets": {"Tank Formation": {"group": ["o"], "roles": {}}}},
        "leveling": {"enabled": True, "target_lv": 3, "max_leveling": 9,
                     "groups": [{"armies": ["old"], "mode": "buffer", "target_lv": 3}]},
        "logistics": {"enabled": True, "target": 3, "exclude": ["x"], "redeploy": {"a": 1}},
        "revive": {"enabled": False}, "notes": ["old advice"],
        "occupy": {"expansion": "octopus", "max_loss": 0.0},
        "build": {"order": [2001, 2008], "skip": [2002]}}), encoding="utf-8")
    stale = {cfg.forge_targets_path: '{"6117_10": {"budget": 120}}',
             cfg.dig_state_path: '{"state": "done", "target": 64173}',
             cfg.dig_request_path: '{"op": "confirm"}',
             cfg.buffers_path: '{"proposal": {"buffers": [1]}}',
             cfg.spare_advice_path: '{"status": "stuck"}',
             cfg.brain_advice_path: '[{"text": "old"}]',
             cfg.composition_status_path: '{"active": true, "blocked": true}',
             cfg.pending_renames_path: '{"old": {"name": "x"}}',
             cfg.commands_path.with_name("pending_dismissals.json"): '{"old": {}}',
             cfg.commands_path.with_name("equip_sync.json"): '{"3305": "6117_10"}'}
    for p, txt in stale.items():
        p.write_text(txt, encoding="utf-8")
    prof = load_profile(cfg.profile_path)
    reset_calls = []

    class Svc:
        def reset_for_new_game(self):
            reset_calls.append(1)
    assert check_new_game(prof, cfg, SimpleNamespace(main_city_index=183080),
                          services=[Svc()]) is True
    assert reset_calls == [1]
    # match-bound config back to defaults, in memory and on disk
    disk = load_profile(cfg.profile_path)
    for p in (prof, disk):
        assert p.leveling == {"enabled": False, "target_lv": 0, "max_leveling": 1, "groups": []}
        assert p.logistics["enabled"] is False and p.logistics["redeploy"] == {}
        assert p.revive == {"enabled": True} and p.notes == []
        assert p.army["composition"] == {} and p.army["group"] == []
    # the player's own strategy stays (build order, occupy policy, formation names)
    assert disk.build["order"] == [2001, 2008] and disk.occupy["expansion"] == "octopus"
    assert disk.army["onetile"] is False and disk.army["active"] == "Tank Formation"
    # files bound to the old match's equips / armies / cells are gone or empty
    assert json.loads(cfg.forge_targets_path.read_text(encoding="utf-8")) == {}
    assert json.loads(cfg.commands_path.with_name("equip_sync.json").read_text(encoding="utf-8")) == {}
    for p in (cfg.dig_state_path, cfg.dig_request_path, cfg.buffers_path, cfg.spare_advice_path,
              cfg.pending_renames_path, cfg.commands_path.with_name("pending_dismissals.json")):
        assert not p.exists(), p
    assert json.loads(cfg.brain_advice_path.read_text(encoding="utf-8")) == []
    assert json.loads(cfg.composition_status_path.read_text(encoding="utf-8")) == {"active": False}


def test_dig_service_forgets_its_old_dig(tmp_path):
    from nta_agent.runtime.dig_service import DigService
    d = DigService.__new__(DigService)
    d.dig = {"state": "done", "target": 64173}
    d.reset_for_new_game()
    assert d.dig == {}
