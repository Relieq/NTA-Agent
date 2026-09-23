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
