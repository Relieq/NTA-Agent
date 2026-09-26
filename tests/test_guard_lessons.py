from nta_agent.brain.guard import sanitize_lessons


class Led:
    def __init__(self, ids):
        self._ids = set(ids)

    def has(self, i):
        return i in self._ids


def test_drops_lesson_without_valid_evidence():
    led = Led([])   # no real events
    out = sanitize_lessons({"lessons": [{"trigger": {"kind": "battle_loss"},
        "diagnosis": "x", "resolution": {"lever_edits": {}}, "evidence": ["ghost"]}]},
        led, set())
    assert out == []


def test_keeps_safe_lever_edit_and_filters_evidence():
    led = Led(["e1"])
    out = sanitize_lessons({"lessons": [{"trigger": {"kind": "battle_loss",
        "match": {"monster_id": 4111}}, "diagnosis": "AoE",
        "resolution": {"lever_edits": {"occupy": {"policy": {"order": "tank_first"}}}},
        "evidence": ["e1", "ghost"]}]}, led, set())
    assert out[0]["evidence"] == ["e1"]
    assert out[0]["resolution"]["lever_edits"]["occupy"]["policy"]["order"] == "tank_first"


def test_human_owned_lever_becomes_advice():
    led = Led(["e1"])
    out = sanitize_lessons({"lessons": [{"trigger": {"kind": "res_depletion"},
        "diagnosis": "raise cap",
        "resolution": {"lever_edits": {"occupy": {"max_loss": 50}}}, "evidence": ["e1"]}]},
        led, set())
    assert "advice" in out[0]["resolution"]
    assert "lever_edits" not in out[0]["resolution"]


def test_trigger_match_whitelist():
    led = Led(["e1"])
    out = sanitize_lessons({"lessons": [{"trigger": {"kind": "battle_loss",
        "match": {"monster_id": 4116, "bogus": "x"}},
        "diagnosis": "d", "resolution": {"lever_edits": {"revive": {"enabled": False}}},
        "evidence": ["e1"]}]}, led, set())
    assert out[0]["trigger"]["match"] == {"monster_id": 4116}   # bogus key dropped


def test_ignores_non_list_and_empty():
    assert sanitize_lessons({}, Led([]), set()) == []
    assert sanitize_lessons({"lessons": "nope"}, Led([]), set()) == []


class LedCtx(Led):
    def __init__(self, rows):
        super().__init__([r.id for r in rows])
        self._rows = rows

    def all(self):
        return self._rows


def _loss(i, best):
    from nta_agent.execution.ledger import FailureEvent
    return FailureEvent(id=i, ts=0, kind="battle_loss",
                        context={"self_dead": 1, "counterfactual": {"best_order": best}})


def test_order_lesson_contradicting_its_evidence_is_dropped():
    # live 2026-09-27: "dps_first loses troops -> tank_first" while 4 of the 5 cited
    # losses said dps_first would have been better. Not grounded -> no lesson.
    led = LedCtx([_loss("a", "dps_first"), _loss("b", "dps_first"), _loss("c", "tank_first")])
    out = sanitize_lessons({"lessons": [{"trigger": {"kind": "battle_loss"}, "diagnosis": "x",
        "resolution": {"lever_edits": {"occupy": {"policy": {"order": "tank_first"}}}},
        "evidence": ["a", "b", "c"]}]}, led, set())
    assert out == []


def test_order_lesson_agreeing_with_its_evidence_is_kept():
    led = LedCtx([_loss("a", "tank_first"), _loss("b", "tank_first")])
    out = sanitize_lessons({"lessons": [{"trigger": {"kind": "battle_loss",
        "match": {"monster_id": 4107}}, "diagnosis": "x",
        "resolution": {"lever_edits": {"occupy": {"policy": {"order": "tank_first"}}}},
        "evidence": ["a", "b"]}]}, led, set())
    assert out and out[0]["trigger"]["match"] == {"monster_id": 4107}


def test_null_match_values_are_dropped():
    led = Led(["e1"])
    out = sanitize_lessons({"lessons": [{"trigger": {"kind": "res_depletion",
        "match": {"monster_id": None, "resource": "iron", "goal": None}},
        "diagnosis": "x", "resolution": {"advice": "gather iron"}, "evidence": ["e1"]}]},
        led, set())
    assert out[0]["trigger"] == {"kind": "res_depletion", "match": {"resource": "iron"}}
