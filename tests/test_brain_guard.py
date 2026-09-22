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


def test_army_strike_target_validated_and_kept():
    # the brain may set army.strike_target (composition goal); shape is validated.
    e = {"army": {"strike_target": [
        {"pawn_id": 3206, "armies": 1, "size": 9},
        {"pawn_id": 3305, "armies": 4, "size": 12},   # size clamped to <=9
        {"armies": 2}]}}                               # no pawn_id -> dropped
    out = sanitize_edits(e, _prof(), set())
    st = out["army"]["strike_target"]
    assert {"pawn_id": 3206, "armies": 1, "size": 9} in st
    assert {"pawn_id": 3305, "armies": 4, "size": 9} in st   # size clamped
    assert len(st) == 2                                       # entry w/o pawn_id dropped


def test_occupy_policy_order_accepted_and_validated():
    # A valid order policy passes through; an invalid one is dropped.
    out = sanitize_edits({"occupy": {"policy": {"order": "tank_first"}}}, _prof(), set())
    assert out["occupy"]["policy"] == {"order": "tank_first"}
    out2 = sanitize_edits({"occupy": {"policy": {"order": "bogus"}}}, _prof(), set())
    assert "policy" not in out2.get("occupy", {})


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


def test_expansion_whitelist_and_revive():
    ok = sanitize_edits({"occupy": {"expansion": "spiral"},
                         "revive": {"enabled": "no"}}, _prof(), set())
    assert ok["occupy"]["expansion"] == "spiral"
    assert ok["revive"]["enabled"] is False
    # invalid expansion is dropped
    bad = sanitize_edits({"occupy": {"expansion": "zigzag"}}, _prof(), set())
    assert "occupy" not in bad or "expansion" not in bad.get("occupy", {})


def test_advice_sanitized():
    out = sanitize_edits({"advice": [{"text": "Nâng Kho Lương", "why": "sắp tràn"},
                                     {"text": ""}, {"nope": 1}]}, _prof(), set())
    assert out["advice"] == [{"text": "Nâng Kho Lương", "why": "sắp tràn"}]


def test_leveling_sanitized():
    out = sanitize_edits({"leveling": {"enabled": "yes", "target_lv": "8",
                                       "max_leveling": "2", "bogus": 1}}, _prof(), set())
    assert out["leveling"] == {"enabled": True, "target_lv": 8, "max_leveling": 2}
