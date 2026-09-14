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
