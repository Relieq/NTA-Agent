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
    out = sanitize_lessons({"lessons": [{"trigger": {"kind": "battle_loss"}, "diagnosis": "AoE",
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
