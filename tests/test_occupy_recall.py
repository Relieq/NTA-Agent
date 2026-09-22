import types

from nta_agent.brain.lessons import Lesson
from nta_agent.execution.heuristics import OccupyCell


def _lesson(order="tank_first", match=None):
    return Lesson.from_dict({
        "id": "L", "trigger": {"kind": "battle_loss",
                               "match": {"monster_id": 4116} if match is None else match},
        "diagnosis": "d",
        "resolution": {"lever_edits": {"occupy": {"policy": {"order": order}}}},
        "evidence": ["e1"]})


def _cand(index=79542, ids=(4116, 4116)):
    return types.SimpleNamespace(index=index, defenders=[{"id": i} for i in ids])


def test_recall_overrides_order_for_matching_monster():
    events = []
    rule = OccupyCell(lessons_source=lambda: [_lesson()],
                      on_event=lambda k, d: events.append((k, d)))
    assert rule._recall_order(_cand(), "auto") == "tank_first"
    assert any(k == "lesson_recall" for k, d in events)


def test_recall_keeps_default_when_monster_absent():
    rule = OccupyCell(lessons_source=lambda: [_lesson()])
    assert rule._recall_order(_cand(ids=(9999,)), "auto") == "auto"


def test_recall_default_without_source():
    assert OccupyCell()._recall_order(_cand(), "dps_first") == "dps_first"


def test_recall_default_when_no_defenders():
    rule = OccupyCell(lessons_source=lambda: [_lesson()])
    assert rule._recall_order(_cand(ids=()), "auto") == "auto"


def test_recall_broad_lesson_applies_to_any_guardian():
    rule = OccupyCell(lessons_source=lambda: [_lesson(match={})])  # no monster constraint
    assert rule._recall_order(_cand(ids=(1234,)), "auto") == "tank_first"


def test_recall_survives_bad_source():
    def boom():
        raise RuntimeError("x")
    assert OccupyCell(lessons_source=boom)._recall_order(_cand(), "auto") == "auto"
