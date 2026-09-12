from nta_agent.execution.decisions import Decision, pending_decisions
from nta_agent.state.schema import GameState


class FakeConfig:
    """Minimal GameConfig stand-in: table(name) -> dict[id,row]."""

    def __init__(self):
        self._t = {
            "ceri": {5: {"id": 5, "value": 3101}, 6: {"id": 6, "value": 3102},
                     7: {"id": 7, "value": 1001}},
            "pawnText": {"name_3101": {"vi": "Lính Trường Thương"},
                         "name_3102": {"vi": "Lính Trường Mâu"}},
            "policyText": {"name_1001": {"vi": "Ngũ Cốc Phong Đăng"},
                           "desc_1001": {"vi": "Sản lượng cơ bản mỗi giờ tăng {0}"}},
            "equipText": {"effect_6001": {"vi": "HP +100"}},
        }

    def table(self, name):
        return self._t.get(name, {})


def _state(pawn=None, policy=None):
    st = GameState(source="api")
    st.raw = {"player": {"pawnSlots": pawn or {}, "policySlots": policy or {}, "equipSlots": {}}}
    return st


def test_pending_pawn_decision_with_names():
    st = _state(pawn={"s0": {"selectIds": [5, 6], "id": 0, "resetCount": 0, "lv": 1}})
    ds = pending_decisions(st, FakeConfig())
    assert len(ds) == 1
    d = ds[0]
    assert isinstance(d, Decision) and d.track == "pawn" and d.tp == 2 and d.lv == 1
    assert d.options == [
        {"ceri_id": 5, "value": 3101, "name": "Lính Trường Thương", "desc": ""},
        {"ceri_id": 6, "value": 3102, "name": "Lính Trường Mâu", "desc": ""},
    ]


def test_chosen_or_empty_slots_are_not_pending():
    st = _state(pawn={
        "s0": {"selectIds": [5], "id": 3101, "resetCount": 0, "lv": 1},  # already chosen
        "s1": {"selectIds": [], "id": 0, "resetCount": 0, "lv": 2},       # no options
    })
    assert pending_decisions(st, FakeConfig()) == []


def test_policy_track_and_unknown_value_fallback():
    st = _state(policy={"p0": {"selectIds": [7, 99], "id": 0, "resetCount": 2, "lv": 1}})
    ds = pending_decisions(st, FakeConfig())
    assert ds[0].track == "policy" and ds[0].tp == 1 and ds[0].reset_count == 2
    assert ds[0].options[0]["name"] == "Ngũ Cốc Phong Đăng"
    assert ds[0].options[0]["desc"] == "Sản lượng cơ bản mỗi giờ tăng {0}"
    assert ds[0].options[1]["name"] == "#99"  # ceri id 99 unknown -> fallback
    assert ds[0].options[1]["desc"] == ""     # unknown ceri id -> no desc
