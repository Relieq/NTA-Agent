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


# ---- rename ambiguity guards (post-LLM, deterministic) --------------------------
def _armies():
    return [{"uid": "t1", "name": "Team 1", "dominant": "3206", "troops": "9× Lính Rìu Khiên"},
            {"uid": "t2", "name": "Team 2", "dominant": "3305", "troops": "9× Lính Cường Nỏ"},
            {"uid": "t3", "name": "Team 3", "dominant": "3305", "troops": "9× Lính Cường Nỏ"},
            {"uid": "cu", "name": "Cứu Hộ", "dominant": "3201", "troops": "2× Lính Đao Khiên"}]


def test_guard_asks_when_type_matches_several_armies():
    from nta_agent.brain.guard import rename_ambiguity
    q = rename_ambiguity("đổi tên đội cường nỏ thành IMP", [{"uid": "t2", "name": "IMP"}], _armies())
    assert q and "Team 2" in q and "Team 3" in q            # lists both candidates


def test_guard_passes_unique_type_named_army_and_whole_group():
    from nta_agent.brain.guard import rename_ambiguity
    A = _armies()
    assert rename_ambiguity("đổi tên đội rìu khiên thành Tank", [{"uid": "t1", "name": "Tank"}], A) is None
    # the army is named explicitly -> other crossbow armies don't matter
    assert rename_ambiguity("đổi tên Team 3 thành IMP B", [{"uid": "t3", "name": "IMP B"}], A) is None
    assert rename_ambiguity("doi ten team3 thanh IMP B", [{"uid": "t3", "name": "IMP B"}], A) is None
    # both crossbow armies renamed together -> no leftover peer -> fine
    assert rename_ambiguity("đổi tên 2 đội nỏ thành A, B",
                            [{"uid": "t2", "name": "A"}, {"uid": "t3", "name": "B"}], A) is None


def test_guard_asks_on_positional_reference():
    from nta_agent.brain.guard import rename_ambiguity
    A = _armies()
    q = rename_ambiguity("đổi tên đội nỏ đầu tiên thành IMP 1", [{"uid": "t2", "name": "IMP 1"}], A)
    assert q and "vị trí" in q
    assert rename_ambiguity("doi ten doi tank thu hai thanh X", [{"uid": "t1", "name": "X"}], A)
    # a positional word is irrelevant when the army is named explicitly
    assert rename_ambiguity("đổi tên Team 2 (đội đầu tiên) thành A", [{"uid": "t2", "name": "A"}],
                            A) is None


def test_guard_no_renames_no_question():
    from nta_agent.brain.guard import rename_ambiguity
    assert rename_ambiguity("đổi tên đội cường nỏ thành IMP", [], _armies()) is None


def test_guard_asks_when_several_armies_get_the_same_new_name():
    """Evidence: the LLM answered a SINGULAR request ('đổi tên đội cường nỏ thành IMP')
    by giving every crossbow army the same name — 5/9 of its remaining wrong renames."""
    from nta_agent.brain.guard import rename_ambiguity
    A = _armies()
    q = rename_ambiguity("đổi tên đội cường nỏ thành IMP",
                         [{"uid": "t2", "name": "IMP"}, {"uid": "t3", "name": "IMP"}], A)
    assert q and "IMP" in q and "Team 2" in q and "Team 3" in q
    # distinct names for the same armies are fine
    assert rename_ambiguity("đổi tên 2 đội nỏ thành IMP 1, IMP 2",
                            [{"uid": "t2", "name": "IMP 1"}, {"uid": "t3", "name": "IMP 2"}], A) is None


def _mixed():
    return [{"uid": "m1", "name": "Đội 1", "dominant": "3206", "share": 5 / 9,
             "troops": "5× Lính Rìu Khiên, 4× Lính Cường Nỏ"},
            {"uid": "m2", "name": "Đội 2", "dominant": "3305", "share": 7 / 9,
             "troops": "7× Lính Cường Nỏ, 2× Lính Rìu Khiên"},
            {"uid": "h2", "name": "Nỏ A", "dominant": "3305", "share": 1.0,
             "troops": "9× Lính Cường Nỏ"}]


def test_guard_asks_when_type_barely_dominates_a_mixed_army():
    """'A team of X' must be (mostly) X — the prompt says so but the LLM ignores it."""
    from nta_agent.brain.guard import rename_ambiguity
    A = [a for a in _mixed() if a["uid"] != "h2"]
    q = rename_ambiguity("đổi tên đội rìu khiên thành Tank", [{"uid": "m1", "name": "Tank"}], A)
    assert q and "Đội 1" in q
    # 7/9 dominant is a fair "crossbow team" -> fine, unless the player said PURE
    assert rename_ambiguity("đổi tên đội cường nỏ thành IMP", [{"uid": "m2", "name": "IMP"}], A) is None
    assert rename_ambiguity("đổi tên đội toàn cường nỏ thành IMP", [{"uid": "m2", "name": "IMP"}], A)


def test_guard_pure_request_ignores_mixed_peers():
    from nta_agent.brain.guard import rename_ambiguity
    A = _mixed()   # m2 (7/9 crossbow) + h2 (pure crossbow)
    assert rename_ambiguity("đổi tên đội nỏ thuần thành IMP", [{"uid": "h2", "name": "IMP"}], A) is None
    assert rename_ambiguity("đổi tên đội nỏ thành IMP", [{"uid": "h2", "name": "IMP"}], A)  # still ambiguous
    # 'toàn bộ' (= all) is not a purity request
    assert rename_ambiguity("đổi tên toàn bộ đội nỏ thành IMP", [{"uid": "h2", "name": "IMP"}], A)


def test_guard_asks_when_fewer_armies_than_new_names():
    """Evidence (fresh HOLD2): 'đổi tên đội tank với đội farm thành A và B' -> the LLM
    renamed only one army. More new names than armies proposed = partial -> ask."""
    from nta_agent.brain.guard import rename_ambiguity
    A = _armies()
    assert rename_ambiguity("đổi tên đội rìu khiên với Cứu Hộ thành A và B",
                            [{"uid": "t1", "name": "A"}], A)
    assert rename_ambiguity("đổi tên cả 3 đội thành Một, Hai, Ba",
                            [{"uid": "t1", "name": "Một"}], A)
    # as many armies as names -> fine; a single new name -> not this guard
    assert rename_ambiguity("đổi tên Team 2 và Team 3 thành A và B",
                            [{"uid": "t2", "name": "A"}, {"uid": "t3", "name": "B"}], A) is None
    assert rename_ambiguity("rename Team 1 to Tank", [{"uid": "t1", "name": "Tank"}], A) is None
