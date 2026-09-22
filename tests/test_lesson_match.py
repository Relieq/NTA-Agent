from nta_agent.brain.lessons import Lesson, LessonStore, match_lessons


def _mk(**kw):
    base = {"id": "x", "trigger": {"kind": "battle_loss", "match": {"monster_id": 4116}},
            "diagnosis": "d",
            "resolution": {"lever_edits": {"occupy": {"policy": {"order": "tank_first"}}}},
            "evidence": ["e1"]}
    base.update(kw)
    return Lesson.from_dict(base)


def test_matches_when_monster_id_present():
    lz = _mk()
    out = match_lessons([lz], {"kind": "battle_loss", "monster_ids": [4116, 4110]})
    assert [x.id for x in out] == ["x"]


def test_no_match_when_monster_absent():
    lz = _mk()
    assert match_lessons([lz], {"kind": "battle_loss", "monster_ids": [9999]}) == []


def test_kind_must_match():
    lz = _mk()
    assert match_lessons([lz], {"kind": "res_depletion", "monster_ids": [4116]}) == []


def test_broad_lesson_without_match_matches_kind():
    lz = _mk(trigger={"kind": "battle_loss"})
    out = match_lessons([lz], {"kind": "battle_loss", "monster_ids": [1]})
    assert [x.id for x in out] == ["x"]


def test_resource_constraint():
    lz = _mk(trigger={"kind": "res_depletion", "match": {"resource": "cereal"}})
    assert match_lessons([lz], {"kind": "res_depletion", "resource": "cereal"})
    assert match_lessons([lz], {"kind": "res_depletion", "resource": "iron"}) == []


def test_retired_lessons_never_match():
    lz = _mk(status="retired")
    assert match_lessons([lz], {"kind": "battle_loss", "monster_ids": [4116]}) == []


def test_accepts_lesson_dicts_too():
    out = match_lessons([{"id": "d", "status": "active", "trigger": {"kind": "battle_loss"}}],
                        {"kind": "battle_loss", "monster_ids": []})
    assert out and getattr(out[0], "id", None) == "d"


def test_store_active_feeds_matcher(tmp_path):
    st = LessonStore(tmp_path / "l.json")
    st.upsert({"trigger": {"kind": "battle_loss", "match": {"monster_id": 4116}},
               "diagnosis": "d", "resolution": {"advice": "x"}, "evidence": ["e1"]})
    out = match_lessons(st.active(), {"kind": "battle_loss", "monster_ids": [4116]})
    assert len(out) == 1
