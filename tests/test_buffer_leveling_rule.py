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
    def __init__(self, armies, swap_mutates=False):
        self.armies = armies
        self.calls = []
        self.swap_mutates = swap_mutates

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
        if self.swap_mutates and army_uid2 and army_uid2 != army_uid:
            a1 = next(a for a in self.armies if a["uid"] == army_uid)
            a2 = next(a for a in self.armies if a["uid"] == army_uid2)
            i = next(k for k, p in enumerate(a1["pawns"]) if p["uid"] == uid1)
            j = next(k for k, p in enumerate(a2["pawns"]) if p["uid"] == uid2)
            a1["pawns"][i], a2["pawns"][j] = a2["pawns"][j], a1["pawns"][i]

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


# ---- Task 6: rendezvous next to the main army + same-type swaps ----------------

W = 600
FIELD = MAIN + 20 * W          # the main army's field cell
OWNED = {FIELD - 1, FIELD + 1, FIELD + W, FIELD + 2, MAIN}


def _setup_done(tmp_path):
    buffers.save(tmp_path / "buffers.json", {
        "proposal": {"buffers": [{"name": "Nâng Cấp 1", "base_uid": "B", "types": {"3305": 2},
                                  "merge": [], "recruit": {}}], "dismiss": []},
        "approved": True, "setup_done": True, "buffers": {}})


def _field_world(buf_index=MAIN, main_index=FIELD, main_state=0):
    main = {"uid": "G0", "name": "Đội 0", "index": main_index, "state": main_state,
            "pawns": [_imp("w1", 1), _imp("w2", 2), _imp("ok", 3)]}
    other = {"uid": "G1", "name": "Đội 1", "index": main_index, "state": 0,
             "pawns": [_imp("z", 3)]}
    buf = {"uid": "B", "name": "Nâng Cấp 1", "index": buf_index, "state": 0,
           "pawns": [_imp("r1", 3), _imp("r2", 3)]}
    return [main, other, buf]


def _rule6(tmp_path):
    r = _rule(tmp_path)
    r.territory_source = lambda: (OWNED, [])
    return r


def _phase(tmp_path):
    return buffers.load(tmp_path / "buffers.json")["buffers"]["B"]


def test_ready_buffer_heads_for_a_cell_next_to_its_target(tmp_path):
    _setup_done(tmp_path)
    rule = _rule6(tmp_path)
    acts = FakeActions(_field_world())
    _tick(rule, _state(), acts)
    assert _phase(tmp_path)["phase"] == "travel" and _phase(tmp_path)["target"] == "G0"
    assert acts.calls == [("move", ["B"], FIELD - 1)]        # owned 4-neighbour, lowest index


def test_meeting_cell_follows_the_main_army(tmp_path):
    _setup_done(tmp_path)
    rule = _rule6(tmp_path)
    world = _field_world()
    acts = FakeActions(world)
    _tick(rule, _state(), acts)
    world[2]["index"] = FIELD - 1                            # buffer arrived...
    world[0]["index"] = FIELD + 1                            # ...but the main army moved on
    world[0]["state"] = 1                                    # (still marching)
    acts.calls.clear()
    _tick(rule, _state(), acts)
    assert acts.calls == [("move", ["B"], FIELD + 2)]        # next to its NEW cell


def test_main_army_steps_over_then_swaps_pair_by_pair(tmp_path):
    _setup_done(tmp_path)
    rule = _rule6(tmp_path)
    world = _field_world()
    acts = FakeActions(world, swap_mutates=True)
    _tick(rule, _state(), acts)                              # leveling -> travel, buffer walks
    world[2]["index"] = FIELD - 1                            # buffer arrived next to G0
    _tick(rule, _state(), acts)
    assert ("move", ["G0"], FIELD - 1) in acts.calls
    assert _phase(tmp_path)["phase"] == "swap" and rule.away_uids() == {"G0"}
    world[0]["index"] = FIELD - 1                            # main arrived
    acts.calls.clear()
    _tick(rule, _state(), acts)
    _tick(rule, _state(), acts)
    assert acts.calls == [("exchange", FIELD - 1, "G0", "w1", "r1", "B"),
                          ("exchange", FIELD - 1, "G0", "w2", "r2", "B")]
    acts.calls.clear()
    _tick(rule, _state(), acts)                              # no pairs left -> home
    assert acts.calls == [("move", ["B"], MAIN)] and rule.away_uids() == set()
    world[2]["index"] = MAIN
    _tick(rule, _state(), acts)
    assert _phase(tmp_path)["phase"] == "leveling"


def test_swap_error_is_reported_with_its_ecode(tmp_path):
    _setup_done(tmp_path)
    rule = _rule6(tmp_path)
    events = []
    rule.on_event = lambda k, d=None: events.append((k, d))
    world = _field_world(buf_index=FIELD - 1, main_index=FIELD - 1)
    acts = FakeActions(world)
    st = buffers.load(tmp_path / "buffers.json")
    st["buffers"] = {"B": {"name": "Nâng Cấp 1", "phase": "swap", "target": "G0",
                           "cell": FIELD - 1}}
    buffers.save(tmp_path / "buffers.json", st)

    def boom(*a, **k):
        raise RuntimeError("game/HD_ExchangePawnArmy: ecode.500036")
    acts.exchange_pawn_army = boom
    _tick(rule, _state(), acts)
    assert ("buffer_error", {"stage": "swap", "ecode": "500036",
                             "msg": "game/HD_ExchangePawnArmy: ecode.500036"}) in events


def test_buffer_reshapes_with_a_spare_at_the_city_then_levels_the_new_type(tmp_path):
    hunter = 3401
    rows = dict(ROWS)
    rows[3401001] = {"lv_cost": "1,0,300|7,0,1", "lv_time": 400, "lv_cond": "4,2004,1"}
    _setup_done(tmp_path)
    rule = BufferLeveling(profile=_prof(), state_path=tmp_path / "buffers.json", rows=rows)
    e = {"uid": "G0", "name": "E", "index": MAIN + 5, "state": 0,
         "pawns": [_imp(f"e{k}") for k in range(8)] + [{"uid": "eh", "id": hunter, "lv": 1}]}
    buf = {"uid": "B", "name": "Nâng Cấp 1", "index": MAIN, "state": 0,
           "pawns": [_imp(f"b{k}", 2) for k in range(9)]}
    spare = {"uid": "S", "name": "D7", "index": MAIN, "state": 0,
             "pawns": [{"uid": "sh", "id": hunter, "lv": 1}]}
    acts = FakeActions([e, {"uid": "G1", "name": "x", "index": MAIN + 5, "state": 0, "pawns": []},
                        buf, spare], swap_mutates=True)
    _tick(rule, _state(), acts)
    assert acts.calls == [("exchange", MAIN, "B", "b0", "sh", "S")]
    acts.calls.clear()
    _tick(rule, _state(), acts)
    assert acts.calls == [("level", "B", "sh")]              # the hunter is leveled too


def test_setup_armies_are_reserved_until_setup_is_done(tmp_path):
    # live 2026-09-26: expansion sent D1 + D5 (the approved base/merge source) out
    # right after the first merge, stalling the setup
    rule = _rule(tmp_path)
    acts = FakeActions(_group() + _spares())
    rule.applies(_state(), acts)                              # proposal
    assert rule.buffer_uids() == set()                        # nothing reserved before approval
    buffers.approve(tmp_path / "buffers.json")
    _tick(rule, _state(), acts)
    assert rule.buffer_uids() == {"D5", "D1"}                 # base + merge source held
    for _ in range(6):
        _tick(rule, _state(), acts)
    assert buffers.load(tmp_path / "buffers.json")["setup_done"] is True
    assert rule.buffer_uids() == {"D5"}                       # D5 is the buffer now; D1 freed


def test_does_not_requeue_a_pawn_it_just_sent(tmp_path):
    # live 2026-09-26: the queue in state lags the PawnLving reply -> the same pawn was
    # picked again -> ecode.500079 + a minute's back-off per slot
    rule = _rule(tmp_path)
    buf = {"uid": "B", "name": "Nâng Cấp 1", "index": MAIN, "state": 0,
           "pawns": [_imp(f"b{k}") for k in range(9)]}
    acts = FakeActions(_group() + [buf])
    buffers.save(tmp_path / "buffers.json", {
        "proposal": {"buffers": [{"name": "Nâng Cấp 1", "base_uid": "B", "types": {"3305": 9},
                                  "merge": [], "recruit": {}}], "dismiss": []},
        "approved": True, "setup_done": True, "buffers": {}})
    for _ in range(3):
        _tick(rule, _state(), acts)          # queue in state stays empty (stale)
    assert acts.calls == [("level", "B", "b0"), ("level", "B", "b1"), ("level", "B", "b2")]
