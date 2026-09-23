"""strike_target one-shot + new-game reset of uid/cell-bound profile fields."""
import json

from nta_agent.execution.profile import (
    clear_strike_target,
    load_profile,
    reset_for_new_game,
)


def _write(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_clear_strike_target_on_disk(tmp_path):
    p = tmp_path / "profile.json"
    _write(p, {"army": {"strike_target": [{"pawn_id": 3206, "armies": 1, "size": 9}],
                        "group": ["u1"]}, "occupy": {"max_loss": 5}})
    clear_strike_target(p)
    prof = load_profile(p)
    assert prof.army["strike_target"] == []
    assert prof.army["group"] == ["u1"]          # nothing else touched
    assert prof.occupy["max_loss"] == 5


def test_reset_for_new_game_clears_stale_uids_keeps_settings(tmp_path):
    p = tmp_path / "profile.json"
    _write(p, {
        "army": {"strike_target": [{"pawn_id": 3305, "armies": 4, "size": 9}],
                 "group": ["old1", "old2"], "roles": {"old1": "tank"},
                 "active": "Default Formation", "home_city": 326479,
                 "presets": {"Default Formation": {"group": ["old1"], "roles": {"old1": "t"}},
                             "Archer Squad": {"group": [], "roles": {}}}},
        "occupy": {"max_loss": 0.0, "expansion": "spiral"},
        "logistics": {"enabled": True, "redeploy": {"old1": 331273}, "exclude": ["old2"]},
        "build": {"order": [2004], "skip": [2000]},
    })
    cleared = reset_for_new_game(p, home_city=71372)
    prof = load_profile(p)
    a = prof.army
    assert a["strike_target"] == [] and a["group"] == [] and a["roles"] == {}
    assert a["presets"]["Default Formation"] == {"group": [], "roles": {}}
    assert set(a["presets"]) == {"Default Formation", "Archer Squad"}   # names kept
    assert a["active"] == "Default Formation"
    assert a["home_city"] == 71372
    assert prof.logistics["redeploy"] == {} and prof.logistics["exclude"] == []
    assert prof.logistics["enabled"] is True                  # settings kept
    assert prof.occupy["expansion"] == "spiral" and prof.build["skip"] == [2000]
    assert "strike_target" in cleared and "group" in cleared
