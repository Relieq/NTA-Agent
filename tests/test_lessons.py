from nta_agent.brain.lessons import LessonStore


def _lesson(**kw):
    base = {"trigger": {"kind": "battle_loss", "match": {"monster_id": 4116}},
            "diagnosis": "AoE >9",
            "resolution": {"lever_edits": {"occupy": {"policy": {"order": "tank_first"}}}},
            "evidence": ["e1"]}
    base.update(kw)
    return base


def test_upsert_and_active(tmp_path):
    st = LessonStore(tmp_path / "l.json")
    lid = st.upsert(_lesson())
    assert [le.id for le in st.active()] == [lid]
    # persisted + reloadable
    assert [le.id for le in LessonStore(tmp_path / "l.json").active()] == [lid]


def test_dedup_same_trigger_increments_times_seen(tmp_path):
    st = LessonStore(tmp_path / "l.json")
    a = st.upsert(_lesson())
    b = st.upsert(_lesson(evidence=["e2"]))
    assert a == b
    assert st.all()[0].times_seen == 2


def test_retire_hides_from_active(tmp_path):
    st = LessonStore(tmp_path / "l.json")
    lid = st.upsert(_lesson())
    st.retire(lid)
    assert st.active() == []
    assert st.all()[0].status == "retired"


def test_pin_marks_lesson(tmp_path):
    st = LessonStore(tmp_path / "l.json")
    lid = st.upsert(_lesson())
    st.pin(lid)
    assert st.all()[0].pinned is True


def test_cap_evicts_oldest(tmp_path):
    st = LessonStore(tmp_path / "l.json", cap=2)
    for m in (1, 2, 3):
        st.upsert(_lesson(trigger={"kind": "battle_loss", "match": {"monster_id": m}}))
    assert len(st.all()) == 2



def test_null_constraint_does_not_crash_matching():
    from nta_agent.brain.lessons import match_lessons
    le = {"id": "x", "trigger": {"kind": "battle_loss", "match": {"monster_id": None}},
          "resolution": {}, "status": "active"}
    assert [m.id for m in match_lessons([le], {"kind": "battle_loss", "monster_ids": [4201]})] == ["x"]


def test_evidence_dismissed_by_a_retired_lesson_is_not_relearned(tmp_path):
    # the player retired a lesson; the brain re-proposing it from the SAME failures
    # must neither create a new lesson nor revive the retired one
    from nta_agent.brain.lessons import LessonStore
    st = LessonStore(tmp_path / "l.json")
    lid = st.upsert({"trigger": {"kind": "battle_loss"}, "diagnosis": "d",
                     "resolution": {"advice": "a"}, "evidence": ["e1", "e2"]})
    st.retire(lid)
    assert st.upsert({"trigger": {"kind": "battle_loss"}, "diagnosis": "d",
                      "resolution": {"advice": "a"}, "evidence": ["e2", "e1"]}) == ""
    assert st.upsert({"trigger": {"kind": "battle_loss", "match": {"monster_id": 1}},
                      "diagnosis": "d", "resolution": {"advice": "a"}, "evidence": ["e1"]}) == ""
    assert st.active() == []
    # a NEW failure is real new evidence -> may be learned
    assert st.upsert({"trigger": {"kind": "battle_loss"}, "diagnosis": "d",
                      "resolution": {"advice": "a"}, "evidence": ["e3"]}) != ""
