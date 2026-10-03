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


def _state(exp_book=50, queue=(), cereal=99999):
    st = GameState(source="api")
    st.user = User(uid="me")
    st.main_city_index = MAIN
    st.resources.exp_book = exp_book
    st.resources.cereal = cereal
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


def test_target_on_an_isolated_owned_cell_is_met_on_its_own_cell(tmp_path):
    # live 2026-10-02: the farm army stood on an owned cell none of whose 4 neighbours is
    # ours -> no meeting cell -> the buffer sat there for 22 h and nothing was ever swapped
    _setup_done(tmp_path)
    rule = _rule(tmp_path)
    rule.territory_source = lambda: ({FIELD}, [])
    acts = FakeActions(_field_world())
    _tick(rule, _state(), acts)
    assert _phase(tmp_path)["phase"] == "travel" and _phase(tmp_path)["cell"] == FIELD
    assert acts.calls == [("move", ["B"], FIELD)]


def test_target_standing_on_ally_land_is_met_there(tmp_path):
    # the client lets you move onto an ally's cell (move button for `isOneAlliance` cells), so
    # an army that set out from ally land is met on that cell (user 2026-10-02)
    _setup_done(tmp_path)
    rule = _rule(tmp_path)
    rule.territory_source = lambda: (set(), [])
    rule.ally_source = lambda: {FIELD}
    acts = FakeActions(_field_world())
    _tick(rule, _state(), acts)
    assert acts.calls == [("move", ["B"], FIELD)]


def test_our_own_neighbour_is_preferred_to_ally_land(tmp_path):
    _setup_done(tmp_path)
    rule = _rule(tmp_path)
    rule.territory_source = lambda: ({FIELD + 1}, [])
    rule.ally_source = lambda: {FIELD, FIELD - 1}
    acts = FakeActions(_field_world())
    _tick(rule, _state(), acts)
    assert acts.calls == [("move", ["B"], FIELD + 1)]


def test_unreachable_target_is_replaced_by_another_army_that_can_be_met(tmp_path):
    _setup_done(tmp_path)
    rule = _rule(tmp_path)
    world = _field_world()
    far = FIELD + 40 * 600                                       # not ours, no owned neighbour
    world[0]["index"] = far                                      # G0 (the best target) is out there
    world[1]["index"] = FIELD                                    # G1 sits on our land
    world[1]["pawns"] = [_imp("v1", 1)]
    rule.territory_source = lambda: ({FIELD}, [])
    acts = FakeActions(world)
    _tick(rule, _state(), acts)                                  # G0 can't be met: re-aim
    _tick(rule, _state(), acts)                                  # ...and walk to G1
    assert _phase(tmp_path)["target"] == "G1"
    assert acts.calls == [("move", ["B"], FIELD)]


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


def test_buffer_uids_known_right_after_a_restart(tmp_path):
    # a fresh rule (agent restart) must already report the approved buffer before it
    # has run a tick — OccupyCell runs first in the tick
    _setup_done(tmp_path)
    fresh = BufferLeveling(profile=_prof(), state_path=tmp_path / "buffers.json", rows=ROWS)
    assert "B" in fresh.buffer_uids()


def test_no_swap_when_the_buffer_is_no_longer_in_the_cell(tmp_path):
    # live 2026-09-27: the swap step checked only that the MAIN army was in the
    # meeting cell; the buffer had left, so ExchangePawnArmy failed with 500011 97
    # times over 3.5 h. Re-plan the meeting instead of swapping into an empty cell.
    _setup_done(tmp_path)
    rule = _rule6(tmp_path)
    world = _field_world()
    acts = FakeActions(world, swap_mutates=True)
    _tick(rule, _state(), acts)
    world[2]["index"] = FIELD - 1                            # buffer next to G0
    _tick(rule, _state(), acts)
    world[0]["index"] = FIELD - 1                            # main arrived
    world[2]["index"] = MAIN                                 # ...but the buffer left
    acts.calls.clear()
    _tick(rule, _state(), acts)
    assert not any(c[0] == "exchange" for c in acts.calls)
    assert _phase(tmp_path)["phase"] == "travel"


# ---- a recruit step into a buffer that is already full must not loop forever ----------------
def _recruit_setup(tmp_path, have):
    """An approved plan that recruits 9 IMP into 'Nâng Cấp 1'; the army holds ``have`` already."""
    path = tmp_path / "buffers.json"
    st = buffers.load(path)
    st.update(approved=True, setup_done=False, done=[], proposal={
        "buffers": [{"name": "Nâng Cấp 1", "base_uid": "", "types": {"3305": 9}, "merge": [],
                     "recruit": {"3305": 9}}], "dismiss": []})
    buffers.save(path, st)
    buf = {"uid": "NC1", "name": "Nâng Cấp 1", "index": MAIN, "state": 0,
           "pawns": [_imp(f"n{k}") for k in range(have)]}
    return _group() + [buf]


def test_recruit_steps_are_moot_when_the_buffer_already_holds_the_planned_pawns(tmp_path):
    rule = _rule(tmp_path)
    acts = FakeActions(_recruit_setup(tmp_path, have=9))
    for _ in range(3):
        _tick(rule, _state(), acts)
    assert [c for c in acts.calls if c[0] == "drill"] == []        # nothing is recruited
    assert buffers.load(tmp_path / "buffers.json")["setup_done"] is True


def test_a_full_army_answer_ends_the_recruit_steps_instead_of_retrying(tmp_path):
    class Full(FakeActions):
        def drill_pawn(self, *a, **k):
            self.calls.append(("drill",))
            raise RuntimeError("game/HD_DrillPawn: ecode.500019")
    rule = _rule(tmp_path)
    acts = Full(_recruit_setup(tmp_path, have=5))                 # 5 < 9: it does try once
    for _ in range(4):
        _tick(rule, _state(), acts)
    assert len([c for c in acts.calls if c[0] == "drill"]) == 1    # not every minute for hours
    assert buffers.load(tmp_path / "buffers.json")["setup_done"] is True


def test_recruiting_still_goes_on_while_the_buffer_is_short(tmp_path):
    rule = _rule(tmp_path)
    acts = FakeActions(_recruit_setup(tmp_path, have=3))
    _tick(rule, _state(), acts)
    assert [c[:3] for c in acts.calls if c[0] == "drill"] == [("drill", 3305, "NC1")]


# ---- a level-up costs cereal (346 at lv1): say so, so the generic top-up leaves it ----------
def test_waiting_for_cereal_sets_a_reserve_and_sends_nothing(tmp_path):
    rule = _rule(tmp_path)
    acts = FakeActions(_recruit_setup(tmp_path, have=9))
    for _ in range(3):
        _tick(rule, _state(cereal=16), acts)                     # setup completes
    assert [c for c in acts.calls if c[0] == "level"] == []       # 16 < 346: no useless order
    assert rule.cereal_reserve == 346


def test_enough_cereal_levels_and_keeps_the_next_ones_cereal(tmp_path):
    rule = _rule(tmp_path)
    acts = FakeActions(_recruit_setup(tmp_path, have=9))
    for _ in range(3):
        _tick(rule, _state(cereal=16), acts)
    assert rule.cereal_reserve == 346
    _tick(rule, _state(cereal=400), acts)
    # sent; the cereal of the pawns still to level stays reserved (not 0 any more)
    assert [c[0] for c in acts.calls if c[0] == "level"] == ["level"] and rule.cereal_reserve >= 346


# ---- the cereal of a level-up is PER MATCH: PAWN_COST_LV_LIST[lv] x base price -------------
def test_level_up_cereal_uses_this_matchs_price_not_the_table(tmp_path):
    # table says 346 for a lv1 IMP; this match's base 312 -> 2 x 312 = 624 (live 2026-10-01:
    # 346 passed the check at 400 cereal and the game answered 500012 every minute)
    rule = _rule(tmp_path)
    rule.pawn_cost_source = lambda: {3305: 312}
    acts = FakeActions(_recruit_setup(tmp_path, have=9))
    for _ in range(3):
        _tick(rule, _state(cereal=400), acts)
    assert [c for c in acts.calls if c[0] == "level"] == []      # 400 < 624: nothing is sent
    assert rule.cereal_reserve == 624
    _tick(rule, _state(cereal=700), acts)
    assert [c[0] for c in acts.calls if c[0] == "level"] == ["level"] and rule.cereal_reserve >= 624


def test_cereal_for_the_next_level_ups_stays_reserved_while_one_is_sent(tmp_path):
    # live 2026-10-02: every level-up was affordable, so the reserve was 0 and the generic
    # top-up spent the cereal before the following level-ups (one per tick) could be sent
    rule = _rule(tmp_path)
    acts = FakeActions(_recruit_setup(tmp_path, have=9))
    for _ in range(3):
        _tick(rule, _state(cereal=16), acts)
    _tick(rule, _state(cereal=2000), acts)
    assert [c[0] for c in acts.calls if c[0] == "level"] == ["level"]   # one sent this tick
    assert rule.cereal_reserve >= 346                                   # the next one's cereal kept


def test_a_full_leveling_queue_still_keeps_the_next_level_ups_cereal(tmp_path):
    rule = _rule(tmp_path)
    acts = FakeActions(_recruit_setup(tmp_path, have=9))
    for _ in range(3):
        _tick(rule, _state(cereal=16), acts)
    rule.queue_cap = 0                                                  # nothing can be queued
    _tick(rule, _state(cereal=2000), acts)
    assert [c for c in acts.calls if c[0] == "level"] == []
    assert rule.cereal_reserve >= 346


def test_without_a_price_list_the_table_cost_is_used(tmp_path):
    rule = _rule(tmp_path)
    rule.pawn_cost_source = dict
    acts = FakeActions(_recruit_setup(tmp_path, have=9))
    for _ in range(3):
        _tick(rule, _state(cereal=300), acts)
    assert rule.cereal_reserve == 346


def test_a_broken_price_source_never_blocks_leveling(tmp_path):
    rule = _rule(tmp_path)

    def boom():
        raise RuntimeError("x")
    rule.pawn_cost_source = boom
    acts = FakeActions(_recruit_setup(tmp_path, have=9))
    for _ in range(3):
        _tick(rule, _state(cereal=99999), acts)
    assert [c for c in acts.calls if c[0] == "level"]


# ---- live 2026-10-01: both buffers swapped pawns with a spare back and forth for hours -------
def _pongworld(tmp_path):
    """Group G0 = 9 IMP (3305), G1 = 9 hunters (3201), both weak; buffers designated IMP /
    hunter but MIXED; a spare D1 with hunters at the city."""
    import json as _json

    def army(uid, name, kinds, state=0):
        pawns = [{"uid": f"{uid}-{k}", "id": pid, "lv": 1} for k, pid in enumerate(kinds)]
        return {"uid": uid, "name": name, "index": MAIN, "state": state, "pawns": pawns}
    armies = [army("G0", "Đội 1", [3305] * 9), army("G1", "Đội 2", [3201] * 9),
              army("B1", "Nâng Cấp 1", [3305] * 3 + [3201] * 6),
              army("B2", "Nâng Cấp 2", [3305] * 6 + [3201] * 3),
              army("D1", "D1", [3201] * 6)]
    path = tmp_path / "buffers.json"
    st = buffers.load(path)
    st.update(approved=True, setup_done=True, done=[], proposal={
        "buffers": [{"name": "Nâng Cấp 1", "base_uid": "", "types": {"3305": 9}, "merge": [],
                     "recruit": {}},
                    {"name": "Nâng Cấp 2", "base_uid": "", "types": {"3201": 9}, "merge": [],
                     "recruit": {}}], "dismiss": []})
    buffers.save(path, st)
    del _json
    return armies


def test_buffers_are_made_pure_again_and_stop_trading(tmp_path):
    import random
    armies = _pongworld(tmp_path)
    rule = _rule(tmp_path)
    acts = FakeActions(armies, swap_mutates=True)
    rng = random.Random(7)
    trades = []
    for _ in range(80):
        rng.shuffle(armies)                   # the server lists armies in a different order each time
        before = len([c for c in acts.calls if c[0] == "exchange"])
        _tick(rule, _state(cereal=0), acts)
        trades.append(len([c for c in acts.calls if c[0] == "exchange"]) - before)
    b1 = next(a for a in armies if a["uid"] == "B1")
    b2 = next(a for a in armies if a["uid"] == "B2")
    assert {p["id"] for p in b1["pawns"]} == {3305} and {p["id"] for p in b2["pawns"]} == {3201}
    assert sum(trades) <= 12                      # a handful of trades, not 68
    assert sum(trades[40:]) == 0                  # and it STOPS once the buffers fit


def test_a_reshape_is_never_immediately_undone(tmp_path):
    armies = _pongworld(tmp_path)
    rule = _rule(tmp_path)
    acts = FakeActions(armies, swap_mutates=True)
    for _ in range(40):
        _tick(rule, _state(cereal=0), acts)
    ex = [c for c in acts.calls if c[0] == "exchange"]
    seen = set()
    for c in ex:                                  # (army, out, in, other): never the reverse pair twice
        key = (c[3], c[4])
        assert (c[4], c[3]) not in seen, f"trade {key} undid a previous one"
        seen.add(key)


def test_own_target_is_stable_whatever_order_the_server_lists_armies_in():
    from nta_agent.execution.buffer_plan import own_target

    def a(uid, kinds):
        return {"uid": uid, "pawns": [{"uid": f"{uid}{k}", "id": pid, "lv": 1}
                                      for k, pid in enumerate(kinds)]}
    g0, g1 = a("G0", [3305] * 9), a("G1", [3201] * 9)
    order = {"G0": 0, "G1": 1}
    for armies in ([g0, g1], [g1, g0]):
        assert own_target(armies, {3305}, 2, order)["uid"] == "G0"     # only G0 needs IMP
        assert own_target(armies, {3201}, 2, order)["uid"] == "G1"
        assert own_target(armies, {3305, 3201}, 2, order)["uid"] == "G0"  # tie: the player's order
    assert own_target([g0], {3201}, 2, order) is None                  # nothing to serve


# ---- user 2026-10-01: a main army of 8 archers + 1 hunter must NOT level a whole spare army --
def _only_what_is_needed_world(tmp_path):
    hunter = 3201
    _setup_done(tmp_path)
    main_army = {"uid": "G0", "name": "Đội 1", "index": MAIN, "state": 0,
                 "pawns": [_imp(f"m{k}") for k in range(8)] + [{"uid": "mh", "id": hunter, "lv": 1}]}
    other = {"uid": "G1", "name": "Đội 2", "index": MAIN, "state": 0, "pawns": []}
    # the buffer is a SPARE army of nine hunters
    buf = {"uid": "B", "name": "Nâng Cấp 1", "index": MAIN, "state": 0,
           "pawns": [{"uid": f"h{k}", "id": hunter, "lv": 1} for k in range(9)]}
    return [main_army, other, buf]


def test_only_as_many_buffer_pawns_are_leveled_as_the_group_has_weak_ones(tmp_path):
    from nta_agent.execution.buffer_plan import levelable
    armies = _only_what_is_needed_world(tmp_path)
    types = {"Nâng Cấp 1": {3201}}
    allowed, started = levelable([armies[2]], armies[:2], 3, types)
    assert len(allowed) == 1 and started == set()               # ONE hunter, not nine
    # that one is under way (queued): it continues, and no second hunter is started
    one = next(iter(allowed))
    allowed2, started2 = levelable([armies[2]], armies[:2], 3, types, in_progress={one})
    assert allowed2 == {one} and started2 == {one}
    # mid-way (above the others' level) counts as started too
    armies[2]["pawns"][0]["lv"] = 2
    allowed3, _ = levelable([armies[2]], armies[:2], 3, types)
    assert allowed3 == {"h0"}
    # once it is ready (target level) the weak hunter is covered: nothing else is leveled
    armies[2]["pawns"][0]["lv"] = 3
    assert levelable([armies[2]], armies[:2], 3, types)[0] == set()
    # a type the group has no weak pawn of is never leveled
    assert levelable([armies[2]], [armies[1]], 3, types)[0] == set()


def test_the_rule_levels_one_spare_hunter_and_then_goes_to_swap(tmp_path):
    armies = _only_what_is_needed_world(tmp_path)
    p = tmp_path / "buffers.json"
    st = buffers.load(p)
    st["proposal"] = {"buffers": [{"name": "Nâng Cấp 1", "base_uid": "B", "types": {"3201": 9},
                                   "merge": [], "recruit": {}}], "dismiss": []}
    buffers.save(p, st)
    prof = _prof()
    prof.leveling["target_lv"] = 3
    prof.leveling["groups"][0].update(target_lv=3, armies=["G0", "G1"])
    rows = {**ROWS, 3201001: {"lv_cost": "1,0,242|7,0,1", "lv_time": 360, "lv_cond": "4,2004,1"},
            3201002: {"lv_cost": "1,0,387|7,0,2", "lv_time": 540, "lv_cond": "4,2004,5"}}
    rule = BufferLeveling(profile=prof, state_path=p, rows=rows)
    class Instant(FakeActions):               # a level-up lands at once (no queue to wait for)
        def pawn_lving(self, index, army_uid, pawn_uid):
            super().pawn_lving(index, army_uid, pawn_uid)
            for a in self.armies:
                for pw in a["pawns"]:
                    if pw["uid"] == pawn_uid:
                        pw["lv"] += 1
    acts = Instant(armies)
    leveled = set()
    for _ in range(60):
        _tick(rule, _state(cereal=99999, exp_book=99), acts)
        leveled |= {c[2] for c in acts.calls if c[0] == "level"}
        acts.calls.clear()
        rule._sent = {}
    assert len(leveled) <= 1, f"leveled {sorted(leveled)}"        # not the whole spare army


def test_away_uids_survive_a_restart(tmp_path):
    # the swapping army is read from buffers.json, not only from memory: after a restart the
    # occupy rule runs before this one and must still leave it alone
    _setup_done(tmp_path)
    st = buffers.load(tmp_path / "buffers.json")
    st["buffers"] = {"B": {"name": "Nâng Cấp 1", "phase": "swap", "target": "G0", "cell": FIELD}}
    buffers.save(tmp_path / "buffers.json", st)
    fresh = _rule(tmp_path)
    assert fresh.away_uids() == {"G0"}


def test_a_main_army_another_owner_holds_is_not_a_swap_target(tmp_path):
    _setup_done(tmp_path)
    rule = _rule6(tmp_path)
    rule.excluded_source = lambda: {"G0", "G1"}               # chat / dig / composer hold them
    acts = FakeActions(_field_world())
    _tick(rule, _state(), acts)
    assert acts.calls == [] and "B" not in buffers.load(tmp_path / "buffers.json")["buffers"] or \
        _phase(tmp_path)["phase"] == "leveling"


def test_a_target_taken_over_mid_trip_is_given_up(tmp_path):
    _setup_done(tmp_path)
    rule = _rule6(tmp_path)
    world = _field_world()
    acts = FakeActions(world)
    _tick(rule, _state(), acts)                                # heading to G0
    assert _phase(tmp_path)["target"] == "G0"
    rule.excluded_source = lambda: {"G0"}                      # the player's chat now moves G0
    acts.calls.clear()
    _tick(rule, _state(), acts)
    assert _phase(tmp_path)["phase"] in ("home", "leveling") and rule.away_uids() == set()


def test_the_composers_cereal_comes_before_a_level_up(tmp_path):
    rule = _rule(tmp_path)
    acts = FakeActions(_recruit_setup(tmp_path, have=9))
    for _ in range(3):
        _tick(rule, _state(cereal=16), acts)
    rule.cereal_hold_source = lambda: 1800                     # the composer's next recruit
    _tick(rule, _state(cereal=2000), acts)                     # 2000 - 1800 < one level-up
    assert [c for c in acts.calls if c[0] == "level"] == []
    assert rule.cereal_reserve >= 346
    rule.cereal_hold_source = lambda: 0
    _tick(rule, _state(cereal=2000), acts)
    assert [c[0] for c in acts.calls if c[0] == "level"] == ["level"]


# ---- 2026-10-03: a setup whose FIRST step is a dismissal crashed every check
# ("tuple index out of range": the step table was built eagerly with step[2]) — the
# approved setup never moved.
def test_a_dismiss_step_runs_instead_of_crashing(tmp_path):
    rule = _rule(tmp_path)
    acts = FakeActions(_group() + _spares())
    buffers.save(tmp_path / "buffers.json", {
        "proposal": {"buffers": [{"name": "Nâng Cấp 1", "base_uid": "D5",
                                  "types": {"3305": 9}, "merge": [], "recruit": {}}],
                     "dismiss": ["D1"]},
        "approved": True, "setup_done": False, "buffers": {}})
    _tick(rule, _state(), acts)
    assert ("dismiss", "D1") in acts.calls


def test_dismissing_an_empty_or_vanished_pawn_army_never_loops(tmp_path):
    # the server answers 500017 for an army with nothing to dismiss: mark the step done
    # (say so) instead of failing again at every check
    class Refuse(FakeActions):
        def dismiss_army(self, index, army_uid, pawn_id=0):
            raise RuntimeError("game/HD_DismissArmy: ecode.500017")
    rule = _rule(tmp_path)
    empty = {"uid": "E", "name": "D2", "index": MAIN, "state": 0, "pawns": []}
    acts = Refuse(_group() + _spares() + [empty])
    buffers.save(tmp_path / "buffers.json", {
        "proposal": {"buffers": [{"name": "Nâng Cấp 1", "base_uid": "D5",
                                  "types": {"3305": 9}, "merge": [], "recruit": {}}],
                     "dismiss": ["E"]},
        "approved": True, "setup_done": False, "buffers": {}})
    _tick(rule, _state(), acts)                       # must not raise
    assert "dismiss:E" in buffers.load(tmp_path / "buffers.json")["done"]


# ---- 2026-10-03: at the army cap a NEW buffer army can't be created (500054). An empty army
# (a husk left when its last pawn was dismissed) is a ready-made base: rename it, recruit in.
def test_a_new_buffer_reuses_an_empty_army_instead_of_hitting_the_army_cap(tmp_path):
    rule = _rule(tmp_path)
    husk = {"uid": "E", "name": "D2", "index": MAIN, "state": 0, "pawns": []}
    acts = FakeActions(_recruit_setup(tmp_path, have=0)[:-1] + [husk])   # no 'Nâng Cấp 1' yet
    _tick(rule, _state(), acts)
    assert ("rename", "E", "Nâng Cấp 1") in acts.calls
    assert [c[:3] for c in acts.calls if c[0] == "drill"] == [("drill", 3305, "E")]


def test_the_army_cap_without_a_husk_is_reported_and_backs_off_not_raised(tmp_path):
    class Capped(FakeActions):
        def drill_pawn(self, *a, **k):
            self.calls.append(("drill",))
            raise RuntimeError("game/HD_DrillPawn: ecode.500054")
    events = []
    rule = BufferLeveling(profile=_prof(), state_path=tmp_path / "buffers.json",
                                                 rows=ROWS, on_event=lambda k, d: events.append((k, d)))
    acts = Capped(_recruit_setup(tmp_path, have=0)[:-1])
    _tick(rule, _state(), acts)                                  # must not raise
    assert any(k == "buffer_error" and d.get("ecode") == "500054" for k, d in events)
    assert rule._cooldown >= 30                                  # not every few seconds
    assert buffers.load(tmp_path / "buffers.json")["setup_done"] is False
