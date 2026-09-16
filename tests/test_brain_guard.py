from nta_agent.brain.guard import sanitize_edits
from nta_agent.execution.profile import load_profile


def _prof():
    return load_profile("nonexistent")  # defaults


def test_clamps_occupy_and_drops_unknown():
    e = {"occupy": {"max_loss": 250, "max_march_ms": -5, "bogus": 1,
                    "loot": {"enabled": "yes", "min_reward_per_chest": -3}},
         "junk": 9}
    out = sanitize_edits(e, _prof(), set())
    assert out["occupy"]["max_loss"] == 100          # clamped to 100
    assert out["occupy"]["max_march_ms"] == 0        # clamped to >=0
    assert out["occupy"]["loot"]["enabled"] is True  # coerced bool
    assert out["occupy"]["loot"]["min_reward_per_chest"] == 0
    assert "bogus" not in out["occupy"] and "junk" not in out


def test_army_only_real_uids_and_nonneg_counts():
    e = {"army": {"group": ["A", "X"], "roles": {"A": "tank", "X": "archer", "A2": "bad"},
                  "onetile": 0, "composition": {"A": {"3101": -2, "3305": 3}, "X": {"3101": 1}}}}
    out = sanitize_edits(e, _prof(), {"A"})
    assert out["army"]["group"] == ["A"]             # X not real
    assert out["army"]["roles"] == {"A": "tank"}     # X not real, A2 not real
    assert out["army"]["onetile"] is False
    assert out["army"]["composition"] == {"A": {"3101": 0, "3305": 3}}  # X dropped, clamp >=0


def test_fully_invalid_is_empty():
    assert sanitize_edits({"nope": 1}, _prof(), set()) == {}


def test_presets_validated_like_formation():
    e = {"army": {"presets": {"turtle": {"group": ["A", "X"], "roles": {"A": "tank", "X": "archer"},
                  "onetile": 1, "composition": {"A": {"3101": -1}, "X": {"3305": 2}}}},
                  "active": "turtle"}}
    out = sanitize_edits(e, _prof(), {"A"})
    t = out["army"]["presets"]["turtle"]
    assert t["group"] == ["A"] and t["roles"] == {"A": "tank"}
    assert t["onetile"] is True and t["composition"] == {"A": {"3101": 0}}
    assert out["army"]["active"] == "turtle"   # names a preset in the edit


def test_active_dropped_when_unknown():
    out = sanitize_edits({"army": {"active": "ghost"}}, _prof(), {"A"})
    assert "active" not in out.get("army", {})


def test_notes_capped_and_stringified():
    e = {"notes": ["ok note", 123, "x" * 500] + ["n"] * 30}
    out = sanitize_edits(e, _prof(), set())
    assert len(out["notes"]) <= 20
    assert all(isinstance(s, str) and len(s) <= 200 for s in out["notes"])


def test_build_edits_filtered_to_valid_ids():
    out = sanitize_edits({"build": {"order": [2002, 999999, "x"], "skip": [2000]}},
                         _prof(), set(), valid_build_ids={2000, 2002})
    assert out["build"]["order"] == [2002]     # 999999/"x" dropped
    assert out["build"]["skip"] == [2000]


def test_build_edits_dropped_without_valid_ids():
    out = sanitize_edits({"build": {"order": [2002]}}, _prof(), set())
    assert "build" not in out
