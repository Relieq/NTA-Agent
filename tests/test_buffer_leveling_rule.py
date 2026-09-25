"""BufferLeveling rule: proposal -> (approved) setup -> continuous leveling."""
from __future__ import annotations

from types import SimpleNamespace

from nta_agent.execution.heuristics import BufferLeveling
from nta_agent.runtime import buffers
from nta_agent.state.schema import Building, GameState, User

MAIN = 100 * 600 + 100
ROWS = {3305001: {"lv_cost": "1,0,346|7,0,1", "lv_time": 488, "lv_cond": "4,2004,1"},
        3305002: {"lv_cost": "1,0,554|7,0,1", "lv_time": 732, "lv_cond": "4,2004,5"}}


def _imp(u, lv=1):
    return {"uid": u, "id": 3305, "lv": lv}


def _state(exp_book=50, queue=()):
    st = GameState(source="api")
    st.user = User(uid="me")
    st.main_city_index = MAIN
    st.resources.exp_book = exp_book
    st.builds = [Building(index=MAIN, id=2004, lv=13, uid="bar")]
    st.raw = {"player": {"pawnLevelingQueues": [
        {"index": MAIN, "auid": a, "puid": p} for a, p in queue]}}
    return st


def _group():
    return [{"uid": f"G{i}", "name": f"Đội {i}", "index": MAIN + 5, "state": 0,
             "pawns": [_imp(f"g{i}{k}") for k in range(9)]} for i in range(2)]


def _spares(at=MAIN):
    return [{"uid": "D5", "name": "D5", "index": at, "state": 0,
             "pawns": [_imp(f"d5{k}") for k in range(6)] +
             [{"uid": f"d5c{k}", "id": 3201, "lv": 1} for k in range(3)]},
            {"uid": "D1", "name": "D1", "index": at, "state": 0,
             "pawns": [_imp(f"d1{k}") for k in range(4)]}]


class FakeActions:
    def __init__(self, armies):
        self.armies = armies
        self.calls = []

    def get_player_armys(self):
        return self.armies

    def main_city_index(self):
        return MAIN

    def building_uid(self, build_id):
        return "bar" if build_id == 2004 else ""

    def move_cell_army(self, armies, target, **kw):
        self.calls.append(("move", [a["uid"] for a in armies], target))

    def change_pawn_army(self, index, army_uid, pawn_uid, new_army_uid="", **kw):
        self.calls.append(("change", army_uid, pawn_uid, new_army_uid))

    def exchange_pawn_army(self, index, army_uid, uid1, uid2, army_uid2=None):
        self.calls.append(("exchange", index, army_uid, uid1, uid2, army_uid2))

    def rename_army(self, index, army_uid, name):
        self.calls.append(("rename", army_uid, name))
        for a in self.armies:
            if a["uid"] == army_uid:
                a["name"] = name

    def drill_pawn(self, bu, pawn_id, *, index=None, army_uid="", army_name=""):
        self.calls.append(("drill", pawn_id, army_uid, army_name))

    def dismiss_army(self, index, army_uid, pawn_id=0):
        self.calls.append(("dismiss", army_uid))

    def pawn_lving(self, index, army_uid, pawn_uid):
        self.calls.append(("level", army_uid, pawn_uid))


def _prof(mode="buffer"):
    return SimpleNamespace(army={"group": [], "presets": {}, "active": ""}, occupy={},
                           leveling={"enabled": True, "target_lv": 3, "max_leveling": 1,
                                     "groups": [{"armies": ["G0", "G1"], "mode": mode,
                                                 "target_lv": 3}]})


def _rule(tmp_path, mode="buffer"):
    return BufferLeveling(profile=_prof(mode), state_path=tmp_path / "buffers.json", rows=ROWS)


def _tick(rule, state, acts):
    rule._cooldown = 0
    if rule.applies(state, acts):
        rule.act(acts)


def test_inert_without_a_buffer_group(tmp_path):
    acts = FakeActions(_group() + _spares())
    assert _rule(tmp_path, mode="direct").applies(_state(), acts) is False
    assert acts.calls == []


def test_writes_a_proposal_and_waits_for_approval(tmp_path):
    rule = _rule(tmp_path)
    acts = FakeActions(_group() + _spares())
    assert rule.applies(_state(), acts) is False
    d = buffers.load(tmp_path / "buffers.json")
    assert d["approved"] is False and d["proposal"]["buffers"][0]["base_uid"] == "D5"
    assert acts.calls == []                                   # nothing before approval


def test_setup_runs_in_order_after_approval(tmp_path):
    rule = _rule(tmp_path)
    acts = FakeActions(_group() + _spares())
    rule.applies(_state(), acts)                              # proposal
    buffers.approve(tmp_path / "buffers.json")
    for _ in range(6):
        _tick(rule, _state(), acts)
    # D1 is not full -> 3 IMP join D5 by exchanging out D5's 3201 (D5 is full), then rename
    assert acts.calls[:4] == [
        ("exchange", MAIN, "D1", "d10", "d5c0", "D5"),
        ("exchange", MAIN, "D1", "d11", "d5c1", "D5"),
        ("exchange", MAIN, "D1", "d12", "d5c2", "D5"),
        ("rename", "D5", "Nâng Cấp 1")]
    assert buffers.load(tmp_path / "buffers.json")["setup_done"] is True


def test_setup_brings_a_spare_home_first(tmp_path):
    rule = _rule(tmp_path)
    acts = FakeActions(_group() + _spares(at=MAIN + 7))
    rule.applies(_state(), acts)
    buffers.approve(tmp_path / "buffers.json")
    _tick(rule, _state(), acts)
    assert acts.calls == [("move", ["D1", "D5"], MAIN)]         # both needed for the merge


def test_levels_continuously_up_to_six_queued(tmp_path):
    rule = _rule(tmp_path)
    buf = {"uid": "B", "name": "Nâng Cấp 1", "index": MAIN, "state": 0,
           "pawns": [_imp(f"b{k}") for k in range(9)]}
    acts = FakeActions(_group() + [buf])
    buffers.save(tmp_path / "buffers.json", {
        "proposal": {"buffers": [{"name": "Nâng Cấp 1", "base_uid": "B", "types": {"3305": 9},
                                  "merge": [], "recruit": {}}], "dismiss": []},
        "approved": True, "setup_done": True, "buffers": {}})
    queued = [("B", f"b{k}") for k in range(5)]
    _tick(rule, _state(queue=queued), acts)
    assert acts.calls == [("level", "B", "b5")]               # 5 queued -> one more
    acts.calls.clear()
    _tick(rule, _state(queue=queued + [("B", "b5")]), acts)
    assert acts.calls == []                                   # queue full (6)
    _tick(rule, _state(exp_book=0), acts)
    assert acts.calls == []                                   # no books
