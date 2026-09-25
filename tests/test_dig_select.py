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
