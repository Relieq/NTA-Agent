from types import SimpleNamespace

from nta_agent.execution.occupy_planner import plan_rally


def _pred(win, loss):
    return SimpleNamespace(win=win, loss_percent=loss)


def _army(uid, index):
    return {"uid": uid, "index": index, "pawns": [{"id": 3101}]}


def test_rally_consolidates_when_combined_force_wins():
    city = 1000
    grp = [_army("a", 1000), _army("b", 1200), _army("c", 1500)]  # b,c scattered

    def evaluate(armies, tgt):
        # combined (all re-based to city) wins target 1001 at 0 loss
        assert all(int(x["index"]) == city for x in armies)  # re-based to city
        return _pred(True, 0.0) if tgt == 1001 else _pred(False, 100.0)

    out = plan_rally(grp, city, [1001, 1002], evaluate, max_loss=0.0)
    assert out is not None
    moved, tgt = out
    assert tgt == 1001
    assert {a["uid"] for a in moved} == {"b", "c"}  # only the not-home armies move


def test_rally_none_when_already_all_home():
    city = 1000
    grp = [_army("a", 1000), _army("b", 1000)]
    out = plan_rally(grp, city, [1001], lambda a, t: _pred(True, 0.0), max_loss=0.0)
    assert out is None  # nothing scattered -> co-located plan should handle it


def test_rally_none_when_combined_still_loses():
    city = 1000
    grp = [_army("a", 1000), _army("b", 1200)]
    out = plan_rally(grp, city, [1001, 1002], lambda a, t: _pred(True, 8.0), max_loss=0.0)
    assert out is None  # 8% > max_loss 0 -> not worth rallying


def test_rally_none_for_single_army():
    out = plan_rally([_army("a", 1200)], 1000, [1001], lambda a, t: _pred(True, 0.0))
    assert out is None
