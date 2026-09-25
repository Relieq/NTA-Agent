"""OccupyCell._dig_select: dig only the planned next cell, only with the dig
(farm) group, within occupy.max_loss; an unwinnable cell is reported hard."""
from types import SimpleNamespace

from nta_agent.execution.advisor import Plan
from nta_agent.execution.heuristics import OccupyCell

W = 600
CELL = 100 * W + 104
OTHER = 100 * W + 90


def _rule(max_loss=0, group=("g1",)):
    prof = SimpleNamespace(occupy={"max_loss": max_loss},
                           army={"group": list(group), "presets": {}, "active": ""})
    r = OccupyCell(profile=prof)
    r.hard = []
    r.dig_hard_sink = r.hard.append
    return r


def _plans_for(uids):
    return lambda i: [Plan(armies=[{"uid": u, "index": i - 1}], target=i, label=u,
                           prediction=None) for u in uids]


def _predict(loss=0.0, win=True):
    return lambda plan: SimpleNamespace(win=win, loss_percent=loss)


CANDS = [SimpleNamespace(index=OTHER), SimpleNamespace(index=CELL)]


def test_digs_only_the_planned_cell_with_the_group():
    plan = _rule()._dig_select(CANDS, _plans_for(["x9", "g1"]), _predict(), CELL)
    assert plan is not None and plan.target == CELL
    assert [a["uid"] for a in plan.armies] == ["g1"]


def test_group_busy_means_no_dig_and_no_hard_report():
    r = _rule()
    assert r._dig_select(CANDS, _plans_for(["x9"]), _predict(), CELL) is None
    assert r.hard == []


def test_unwinnable_or_lossy_next_cell_is_reported_hard():
    r = _rule(max_loss=0)
    assert r._dig_select(CANDS, _plans_for(["g1"]), _predict(loss=12.0), CELL) is None
    assert r.hard == [CELL]
    r2 = _rule()
    assert r2._dig_select(CANDS, _plans_for(["g1"]), _predict(win=False), CELL) is None
    assert r2.hard == [CELL]


def test_cell_not_among_candidates_is_skipped():
    r = _rule()
    assert r._dig_select([SimpleNamespace(index=OTHER)], _plans_for(["g1"]), _predict(), CELL) is None
    assert r.hard == []


def test_no_group_configured_uses_any_idle_army():
    plan = _rule(group=())._dig_select(CANDS, _plans_for(["x9"]), _predict(), CELL)
    assert plan is not None


def test_a_wounded_group_waits_to_heal_instead_of_marking_the_cell_hard():
    # wounded now -> the win costs pawns; at full hp it's clean: that's a heal
    # case (HealRouting sends the group home), NOT a hard cell to route around
    def plans_for(i):
        return [Plan(armies=[{"uid": "g1", "index": i - 1,
                              "pawns": [{"id": 3305, "hp": {0: 40, 1: 100}}]}],
                     target=i, label="g1", prediction=None)]

    def predict(plan):
        hurt = any(p["hp"][0] < p["hp"][1] if isinstance(p["hp"], list) else
                   p["hp"].get(0, 0) < p["hp"].get(1, 0)
                   for a in plan.armies for p in a["pawns"])
        return SimpleNamespace(win=True, loss_percent=11.0 if hurt else 0.0)

    r = _rule()
    events = []
    r.on_event = lambda k, d=None: events.append(k)
    assert r._dig_select(CANDS, plans_for, predict, CELL) is None
    assert r.hard == []
    assert "dig_heal_wait" in events


# --- the whole group must be there: live 2026-09-25 a split group made every cell
#     look 'hard' (a lone army loses) and the dig re-routed every minute ---

def _army(uid, idx, state=0):
    return {"uid": uid, "index": idx, "state": state, "pawns": [{"id": 3305}]}


GROUP = ("g1", "g2", "g3")


def _group_plans(idxs):
    def plans_for(i):
        out = [Plan(armies=[{"uid": u, "index": idxs[u]}], target=i, label=u, prediction=None)
               for u in GROUP if u in idxs]
        full = [{"uid": u, "index": idxs[u]} for u in GROUP if u in idxs]
        if len(full) > 1 and len({a["index"] for a in full}) == 1:
            out.append(Plan(armies=full, target=i, label="all", prediction=None))
        return out
    return plans_for


def _needs_all(plan):  # only the whole group wins cleanly; any subset loses
    return SimpleNamespace(win=len(plan.armies) == 3, loss_percent=0.0 if len(plan.armies) == 3 else 100.0)


def test_busy_group_member_means_wait_not_hard():
    r = _rule(group=GROUP)
    armies = [_army("g1", CELL - 1), _army("g2", CELL - 1), _army("g3", 7, state=1)]  # g3 marching
    got = r._dig_select(CANDS, _group_plans({"g1": CELL - 1, "g2": CELL - 1}), _needs_all, CELL,
                        all_armies=armies)
    assert got is None and r.hard == []


def test_idle_but_split_group_is_gathered_next_to_the_cell():
    r = _rule(group=GROUP)
    r.territory_source = lambda: ({CELL - 1, CELL - 600}, [])
    armies = [_army("g1", CELL - 1), _army("g2", 5), _army("g3", 9)]
    got = r._dig_select(CANDS, _group_plans({"g1": CELL - 1, "g2": 5, "g3": 9}), _needs_all,
                        CELL, all_armies=armies)
    assert got == "gather" and r.hard == []
    moved, stage, tgt = r._rally
    assert stage in (CELL - 1, CELL - 600) and tgt == CELL
    assert sorted(a["uid"] for a in moved) == ["g2", "g3"]   # g1 is already there


def test_assembled_group_attacks_and_only_it_can_call_a_cell_hard():
    r = _rule(group=GROUP)
    here = {u: CELL - 1 for u in GROUP}
    armies = [_army(u, CELL - 1) for u in GROUP]
    plan = r._dig_select(CANDS, _group_plans(here), _needs_all, CELL, all_armies=armies)
    assert plan is not None and len(plan.armies) == 3
    lossy = lambda p: SimpleNamespace(win=True, loss_percent=5.0)
    assert r._dig_select(CANDS, _group_plans(here), lossy, CELL, all_armies=armies) is None
    assert r.hard == [CELL]


def test_dig_group_is_reserved_while_the_dig_waits():
    # dig waiting (no next cell): expansion must still leave the group alone
    from nta_agent.execution.heuristics import OccupyCell as OC
    r = OC(profile=SimpleNamespace(occupy={"max_loss": 0},
                                   army={"group": ["g1"], "presets": {}, "active": ""}))
    r.dig_source = lambda: None
    r.dig_live_source = lambda: True
    assert r._dig_reserved() == {"g1"}
    r.dig_live_source = lambda: False
    assert r._dig_reserved() == set()


def test_member_in_the_drill_ground_counts_as_busy():
    # live 2026-09-25: Đội 1 had a pawn leveling (state still 0) -> MoveCellArmy
    # ecode.500080 "Đang ở Thao Trường" and the gather looped every minute
    r = _rule(group=GROUP)
    r.territory_source = lambda: ({CELL - 1}, [])
    g3 = {"uid": "g3", "index": 9, "state": 0, "pawns": [{"uid": "p9", "id": 3202}]}
    armies = [_army("g1", CELL - 1), _army("g2", CELL - 1), g3]
    got = r._dig_select(CANDS, _group_plans({"g1": CELL - 1, "g2": CELL - 1, "g3": 9}),
                        _needs_all, CELL, all_armies=armies, busy_pawns={"p9"})
    assert got is None and r._rally is None and r.hard == []


def test_leveling_pawn_uids_reads_the_queue():
    from nta_agent.execution.army_health import leveling_pawn_uids
    st = SimpleNamespace(raw={"player": {"pawnLvingQueues": {
        "pawnUIDMap": {"p1": 1}, "map": {"x": {"puid": "p2", "auid": "a"}}}}})
    assert leveling_pawn_uids(st) == {"p1", "p2"}
    assert leveling_pawn_uids(SimpleNamespace(raw={})) == set()


def test_leveling_pawn_uids_reads_the_live_list_shape():
    # live 2026-09-25: player.pawnLevelingQueues = [{uid, index, auid, puid, id, lv, ...}]
    from nta_agent.execution.army_health import leveling_pawn_uids
    st = SimpleNamespace(raw={"player": {"pawnLevelingQueues": [
        {"uid": "q1", "index": 71372, "auid": "1790258465519001",
         "puid": "1790312511107001", "id": 3202, "lv": 3}]}})
    assert leveling_pawn_uids(st) == {"1790312511107001"}


# --- a member away swapping with a buffer (buffer leveling) ---

def test_member_away_swapping_the_rest_attack_when_clean():
    r = _rule(group=GROUP)
    r.away_source = lambda: {"g3"}
    here = {"g1": CELL - 1, "g2": CELL - 1}
    armies = [_army("g1", CELL - 1), _army("g2", CELL - 1), _army("g3", 42)]

    def plans_for(i):  # the two present members together
        return [Plan(armies=[{"uid": "g1", "index": CELL - 1}, {"uid": "g2", "index": CELL - 1}],
                     target=i, label="two", prediction=None)]
    clean = lambda p: SimpleNamespace(win=True, loss_percent=0.0)
    plan = r._dig_select(CANDS, plans_for, clean, CELL, all_armies=armies)
    assert plan is not None and {a["uid"] for a in plan.armies} == set(here)


def test_member_away_and_the_rest_would_lose_pawns_waits_without_hard():
    r = _rule(group=GROUP)
    r.away_source = lambda: {"g3"}
    armies = [_army("g1", CELL - 1), _army("g2", CELL - 1), _army("g3", 42)]

    def plans_for(i):
        return [Plan(armies=[{"uid": "g1", "index": CELL - 1}, {"uid": "g2", "index": CELL - 1}],
                     target=i, label="two", prediction=None)]
    lossy = lambda p: SimpleNamespace(win=True, loss_percent=4.0)
    assert r._dig_select(CANDS, plans_for, lossy, CELL, all_armies=armies) is None
    assert r.hard == []
