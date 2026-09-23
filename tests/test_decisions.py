from nta_agent.execution.decisions import Decision, pending_decisions
from nta_agent.state.schema import GameState


class FakeConfig:
    """Minimal GameConfig stand-in: table(name) -> dict[id,row]."""

    def __init__(self):
        self._t = {
            "pawnText": {"name_3101": {"vi": "Lính Trường Thương"},
                         "name_3102": {"vi": "Lính Trường Mâu"}},
            "policyText": {"name_1001": {"vi": "Ngũ Cốc Phong Đăng"},
                           "desc_1001": {"vi": "Sản lượng cơ bản mỗi giờ tăng {0}"}},
            "equipText": {"effect_3": {"vi": "Có {1} gây {0} ST Bạo"},
                          "name_6001": {"vi": "Rìu Chiến"}, "name_6002": {"vi": "Giáp Xích"}},
            "equipBase": {6001: {"attack": "1,5", "hp": "20,40", "exclusive_pawn": "", "effect": "3"},
                          6002: {"attack": "", "hp": "20,70", "exclusive_pawn": "3101", "effect": "0"}},
            "equipEffect": {3: {"id": 3, "value": "150,180", "suffix": "%", "odds": "20,40"}},
        }

    def table(self, name):
        return self._t.get(name, {})


def _state(pawn=None, policy=None, equip=None):
    st = GameState(source="api")
    st.raw = {"player": {"pawnSlots": pawn or {}, "policySlots": policy or {},
                         "equipSlots": equip or {}}}
    return st


def test_equip_decision_desc_has_stats():
    st = _state(equip={"e0": {"selectIds": [6001, 6002], "id": 0, "resetCount": 0, "lv": 3}})
    ds = pending_decisions(st, FakeConfig())
    assert len(ds) == 1 and ds[0].track == "equip" and ds[0].tp == 3
    opts = {o["ceri_id"]: o for o in ds[0].options}
    # weapon: stat ranges + the EFFECT filled from equipEffect ({1}=odds, {0}=value)
    assert opts[6001]["name"] == "Rìu Chiến"
    assert opts[6001]["desc"] == "ST 1–5 · Máu 20–40 · Có 20–40% gây 150–180% ST Bạo"
    # armor: no attack, no effect text, specialized note
    assert opts[6002]["desc"] == "Máu 20–70 · (chuyên dụng)"


def test_equip_decision_desc_handles_multi_effect():
    """A high-tier equip's ``effect`` is a pipe-joined list of effect ids
    (e.g. "3|7"). Every effect must render — and int() must never choke on the
    whole string (that failure spammed [decisions] write failed every tick)."""
    cfg = FakeConfig()
    cfg._t["equipText"]["effect_7"] = {"vi": "Hồi {0} máu"}
    cfg._t["equipEffect"][7] = {"id": 7, "value": "30,50", "suffix": "", "odds": ""}
    cfg._t["equipBase"][6003] = {"attack": "2,6", "hp": "", "exclusive_pawn": "", "effect": "3|7"}
    cfg._t["equipText"]["name_6003"] = {"vi": "Rìu Thần"}
    st = _state(equip={"e0": {"selectIds": [6003], "id": 0, "resetCount": 0, "lv": 5}})
    ds = pending_decisions(st, cfg)
    desc = ds[0].options[0]["desc"]
    assert desc == "ST 2–6 · Có 20–40% gây 150–180% ST Bạo · Hồi 30–50 máu"


def test_pending_pawn_decision_with_names():
    # selectIds are the pawn ids directly.
    st = _state(pawn={"s0": {"selectIds": [3101, 3102], "id": 0, "resetCount": 0, "lv": 1}})
    ds = pending_decisions(st, FakeConfig())
    assert len(ds) == 1
    d = ds[0]
    assert isinstance(d, Decision) and d.track == "pawn" and d.tp == 2 and d.lv == 1
    assert d.options == [
        {"ceri_id": 3101, "value": 3101, "name": "Lính Trường Thương", "desc": ""},
        {"ceri_id": 3102, "value": 3102, "name": "Lính Trường Mâu", "desc": ""},
    ]


def test_chosen_or_empty_slots_are_not_pending():
    st = _state(pawn={
        "s0": {"selectIds": [3101], "id": 3101, "resetCount": 0, "lv": 1},  # already chosen
        "s1": {"selectIds": [], "id": 0, "resetCount": 0, "lv": 2},         # no options
    })
    assert pending_decisions(st, FakeConfig()) == []


def test_policy_track_name_desc_and_unknown_fallback():
    # selectIds are policy ids directly; 1001 resolves, 99 falls back.
    st = _state(policy={"p0": {"selectIds": [1001, 99], "id": 0, "resetCount": 2, "lv": 1}})
    ds = pending_decisions(st, FakeConfig())
    assert ds[0].track == "policy" and ds[0].tp == 1 and ds[0].reset_count == 2
    assert ds[0].options[0]["name"] == "Ngũ Cốc Phong Đăng"
    assert ds[0].options[0]["desc"] == "Sản lượng cơ bản mỗi giờ tăng {0}"
    assert ds[0].options[1]["name"] == "#99"  # unknown id -> fallback
    assert ds[0].options[1]["desc"] == ""     # unknown id -> no desc
