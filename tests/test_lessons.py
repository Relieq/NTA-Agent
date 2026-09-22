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
