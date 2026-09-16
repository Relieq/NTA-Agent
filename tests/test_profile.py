import json

from nta_agent.execution.profile import DEFAULT_PROFILE, Profile, load_profile, save_profile


def test_defaults_when_file_missing(tmp_path):
    p = load_profile(tmp_path / "nope.json")
    assert isinstance(p, Profile)
    assert p.occupy["max_loss"] == DEFAULT_PROFILE["occupy"]["max_loss"]
    assert p.army["onetile"] == DEFAULT_PROFILE["army"]["onetile"]


def test_file_overrides_merge_over_defaults(tmp_path):
    f = tmp_path / "profile.json"
    f.write_text(json.dumps({"occupy": {"max_loss": 15}}), encoding="utf-8")
    p = load_profile(f)
    assert p.occupy["max_loss"] == 15                 # overridden
    assert "loot" in p.occupy                          # default kept
    assert p.army["group"] == DEFAULT_PROFILE["army"]["group"]


def test_save_then_load_roundtrip(tmp_path):
    f = tmp_path / "profile.json"
    prof = load_profile(f)
    prof.occupy["max_loss"] = 7
    save_profile(prof, f)
    assert load_profile(f).occupy["max_loss"] == 7


# --- B4: presets / active / notes ---
from nta_agent.execution.profile import active_formation, apply_edits


def test_defaults_have_presets_active_notes():
    p = load_profile("none")
    assert p.army["presets"] == {} and p.army["active"] == ""
    assert p.notes == []


def test_active_formation_prefers_active_preset():
    p = load_profile("none")
    p.army["presets"]["turtle"] = {"group": ["A"], "roles": {"A": "tank"},
                                   "onetile": False, "composition": {"A": {"3101": 5}}}
    assert active_formation(p)["group"] == p.army["group"]   # active "" -> flat
    p.army["active"] = "turtle"
    assert active_formation(p)["group"] == ["A"]
    assert active_formation(p)["onetile"] is False


def test_apply_edits_merges_and_activates():
    p = load_profile("none")
    changed = apply_edits(p, {"army": {"presets": {"turtle": {"group": ["A"], "roles": {},
                              "onetile": True, "composition": {}}}, "active": "turtle"},
                              "occupy": {"max_loss": 8}, "notes": ["early: timber"]})
    assert changed is True
    assert p.army["active"] == "turtle"
    assert p.army["group"] == ["A"]           # activated -> flat synced
    assert p.occupy["max_loss"] == 8
    assert p.notes == ["early: timber"]
    assert apply_edits(p, {}) is False        # no-op


def test_notes_edit_replaces_list():
    p = load_profile("none")
    apply_edits(p, {"notes": ["a"]})
    apply_edits(p, {"notes": ["a", "b"]})
    assert p.notes == ["a", "b"]
