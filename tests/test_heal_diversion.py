from types import SimpleNamespace

from nta_agent.execution.heuristics import OccupyCell
from nta_agent.execution.occupy_planner import Candidate
from nta_agent.execution.predictors.battle import BattlePrediction

W = 600
def idx(x, y): return y * W + x
CITY = idx(100, 100)


def _pred_by_hp(plan):
    # clean win (0 loss) only if EVERY pawn is at full hp; wounded -> lossy
    pawns = [p for a in plan.armies for p in (a.get("pawns") or [])]
    def full(p):
        hp = p.get("hp"); 
        if isinstance(hp, dict): return int(hp.get(1, hp.get("1", 0)) or 0) == int(hp.get(0, hp.get("0", 0)) or 0)
        if isinstance(hp, (list, tuple)) and len(hp) > 1: return hp[0] == hp[-1]
        return True
    clean = all(full(p) for p in pawns)
    return BattlePrediction(win=True, my_power=1, enemy_power=1, ratio=1,
                            loss_percent=0.0 if clean else 40.0, loss_lv=0 if clean else 2)


def _rule():
    r = OccupyCell()
    # heal nodes = city + a fort at (108,100); owned irrelevant here
    r.territory_source = lambda: ({CITY}, [CITY, CITY + 1, CITY + 600, CITY + 601, idx(108, 100)])
    return r


def test_heal_diversion_routes_wounded_convenient_army():
    r = _rule()
    st = SimpleNamespace(main_city_index=CITY)
    # wounded army 2 cells from the city (<4 -> convenient), pawns at half hp
    army = {"uid": "A", "index": idx(100, 102),
            "pawns": [{"uid": "p1", "id": 3101, "hp": [5, 10]}]}
    cands = [Candidate(index=idx(100, 108), defenders=[{"id": 4112, "lv": 5}], hp=(10, 10))]
    out = r._heal_diversion(cands, _pred_by_hp, [army], st)
    assert out is not None
    move, node, _n = out
    assert move["uid"] == "A" and node == CITY and _n   # nearest heal node = the city


def test_no_heal_when_full_hp():
    r = _rule()
    st = SimpleNamespace(main_city_index=CITY)
    army = {"uid": "A", "index": idx(100, 102),
            "pawns": [{"uid": "p1", "id": 3101, "hp": [10, 10]}]}  # full hp
    cands = [Candidate(index=idx(100, 108), defenders=[{"id": 4112, "lv": 5}], hp=(10, 10))]
    assert r._heal_diversion(cands, _pred_by_hp, [army], st) is None


def test_no_heal_when_not_convenient():
    r = _rule()
    st = SimpleNamespace(main_city_index=CITY)
    # wounded but far from any node and route bypasses them
    army = {"uid": "A", "index": idx(100, 130),
            "pawns": [{"uid": "p1", "id": 3101, "hp": [5, 10]}]}
    cands = [Candidate(index=idx(140, 130), defenders=[{"id": 4112, "lv": 5}], hp=(10, 10))]
    assert r._heal_diversion(cands, _pred_by_hp, [army], st) is None
