"""Occupy discovery + OccupyCell rule (fake get_area/actions; no network)."""

from dataclasses import dataclass, field

from nta_agent.execution.heuristics import OccupyCell
from nta_agent.execution.occupy_planner import discover_targets
from nta_agent.execution.predictors.battle import BattlePrediction, BattlePredictor
from nta_agent.execution.predictors.sim_bridge import SimUnavailable
from nta_agent.state.schema import GameState

W = 600


def _cell(owner="", pawns=(), hp=(3, 3), city=0):
    return {"owner": owner, "cityId": city,
            "armys": [{"pawns": [{"hp": h} for h in pawns]}] if pawns else [],
            "hp": list(hp)}


def test_discover_finds_defended_unowned_cells():
    center = 182 * W + 526
    world = {
        center: _cell(owner="me", city=1001),          # my city
        center + 1: _cell(owner="me", city=1001),       # my city tile
        center - 1: _cell(owner="", pawns=[100, 100]),  # occupiable
        center - W: _cell(owner="", pawns=[100]),       # occupiable
        center + W: _cell(owner="enemy", city=2001),    # enemy city -> skip (cityId)
    }
    cands = discover_targets(lambda i: world.get(i, {}), center, 1, my_uid="me")
    idxs = {c.index for c in cands}
    assert (center - 1) in idxs and (center - W) in idxs
    assert center not in idxs and (center + W) not in idxs


@dataclass
class FakeActions:
    areas: dict
    armies: list
    calls: list = field(default_factory=list)
    def get_area(self, index, no_record=True):
        return {"data": self.areas.get(index, {})}
    def select_armies(self, cell_index, type_=0):
        return self.armies
    def occupy_cell(self, target, armies, **kw):
        self.calls.append(("occupy", target, [a["uid"] for a in armies]))
        return {}


def test_occupy_rule_picks_winnable_and_sends_army():
    center = 182 * W + 526
    st = GameState(source="api")
    st.user.uid = "me"
    st.main_city_index = center
    st.resources.stamina = 10
    # my city (owned) + a weak occupiable cell and a strong one, both adjacent
    areas = {
        center: _cell(owner="me", city=1001),                    # owned -> enables adjoin
        center - 1: _cell(owner="", pawns=[50]),                 # weak -> win
        center + 1: _cell(owner="", pawns=[999, 999, 999, 999]), # strong -> lose
    }
    my_army = [{"index": center, "uid": "A", "pawns": [{"hp": 500}, {"hp": 500}], "state": None}]
    act = FakeActions(areas=areas, armies=my_army)
    rule = OccupyCell(radius=1, predictor=BattlePredictor())  # hp-proxy predictor
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls and act.calls[0][0] == "occupy"
    assert act.calls[0][1] == center - 1  # chose the winnable weak cell
    assert act.calls[0][2] == ["A"]


def test_occupy_rule_skips_when_no_stamina():
    st = GameState(source="api"); st.user.uid = "me"; st.main_city_index = 1
    st.resources.stamina = 0
    rule = OccupyCell()
    assert rule.applies(st, FakeActions(areas={}, armies=[])) is False


# ---- sim integration (fake sim; no Node) --------------------------------- #
class FakeSim:
    """Stands in for SimBattlePredictor. win=None -> raise SimUnavailable."""
    def __init__(self, win):
        self._win = win

    def predict_armies(self, state, armies, *, target_index, land_id, distance, **kw):
        if self._win is None:
            raise SimUnavailable("sidecar down")
        return BattlePrediction(
            win=self._win, my_power=1.0, enemy_power=1.0, ratio=1.0,
            loss_percent=0.0 if self._win else 100.0, loss_lv=0 if self._win else 4,
        )


def _occupy_setup():
    center = 182 * W + 526
    st = GameState(source="api"); st.user.uid = "me"; st.main_city_index = center
    st.resources.stamina = 10
    areas = {
        center: _cell(owner="me", city=1001),        # owned -> enables adjoin
        center - 1: _cell(owner="", pawns=[50]),      # weak: stats would WIN
    }
    my_army = [{"index": center, "uid": "A", "pawns": [{"hp": 500}], "state": None}]
    return st, FakeActions(areas=areas, armies=my_army), center


def test_occupy_uses_sim_verdict_over_stats():
    # Stats would win the weak cell, but the sim says lose -> no occupy.
    st, act, _center = _occupy_setup()
    rule = OccupyCell(radius=1, use_sim=True, sim=FakeSim(win=False),
                      predictor=BattlePredictor())
    assert rule.applies(st, act) is False
    assert act.calls == []


def test_occupy_falls_back_to_stats_when_sim_unavailable():
    # Sim raises -> per-candidate fallback to the stats predictor -> occupies.
    st, act, center = _occupy_setup()
    rule = OccupyCell(radius=1, use_sim=True, sim=FakeSim(win=None),
                      predictor=BattlePredictor())
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls and act.calls[0][1] == center - 1


# ---- v2: multi-army selection-order auto-apply --------------------------- #
class OrderSensitiveSim:
    """Sim whose loss depends on which army acts first (cung-first is best)."""
    def predict_armies(self, state, armies, *, target_index, land_id, distance, **kw):
        first = armies[0]["uid"]
        if len(armies) == 2 and first == "cung":
            return BattlePrediction(win=True, my_power=1, enemy_power=1, ratio=1,
                                    loss_percent=0.0, loss_lv=0)
        if len(armies) == 2:
            return BattlePrediction(win=True, my_power=1, enemy_power=1, ratio=1,
                                    loss_percent=30.0, loss_lv=2)
        return BattlePrediction(win=False, my_power=1, enemy_power=1, ratio=1,
                                loss_percent=100.0, loss_lv=4)


def test_occupy_auto_applies_best_selection_order():
    center = 182 * W + 526
    st = GameState(source="api"); st.user.uid = "me"; st.main_city_index = center
    st.resources.stamina = 10
    areas = {center: _cell(owner="me", city=1001),
             center - 1: _cell(owner="", pawns=[50])}
    cung = {"index": center, "uid": "cung", "pawns": [{"id": 3305}, {"id": 3305}]}
    tank = {"index": center, "uid": "tank", "pawns": [{"id": 3101}, {"id": 3101}]}
    act = FakeActions(areas=areas, armies=[tank, cung])  # selected tank-first
    events = []
    rule = OccupyCell(radius=1, use_sim=True, sim=OrderSensitiveSim(),
                      predictor=BattlePredictor(), on_event=lambda k, d: events.append((k, d)))
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls and act.calls[0][1] == center - 1
    assert act.calls[0][2] == ["cung", "tank"]  # reordered to cung-first
    assert any(k == "occupy_plan" and d["label"] == "archers-first" for k, d in events)


# ---- Phase 2: formation optimization before attack ----------------------- #
class FormationSim:
    """predict_armies loss depends on whether 'big' pawn sits at the front slot (x=6)."""
    def predict_armies(self, state, armies, *, target_index, land_id, distance, **kw):
        pawns = [p for a in armies for p in a.get("pawns", [])]
        big = next((p for p in pawns if p["uid"] == "big"), None)
        front = bool(big and big.get("point", {}).get("x") == 6)
        loss = 0.0 if front else 50.0
        pred = BattlePrediction(win=True, my_power=1, enemy_power=1, ratio=1,
                                loss_percent=loss, loss_lv=0)
        pred.pawn_survival = [{"uid": p["uid"], "camp": 2,
                               "alive": front or p["uid"] == "big", "curHp": 100} for p in pawns]
        return pred


def test_occupy_optimizes_formation_before_attack():
    center = 182 * W + 526
    st = GameState(source="api"); st.user.uid = "me"; st.main_city_index = center
    st.resources.stamina = 10
    areas = {center: _cell(owner="me", city=1001),
             center - 1: _cell(owner="", pawns=[50])}
    tank = {"index": center, "uid": "tank",
            "pawns": [{"uid": "big", "id": 3101, "lv": 1, "hp": [200, 200], "point": {"x": 10, "y": 7}},
                      {"uid": "sml", "id": 3101, "lv": 1, "hp": [50, 50], "point": {"x": 6, "y": 7}}]}
    moves = []

    class Acts(FakeActions):
        def move_area_pawns(self, index, army_uid, assignment):
            moves.append((index, army_uid, assignment)); return {}

    act = Acts(areas=areas, armies=[tank])
    events = []
    rule = OccupyCell(radius=1, use_sim=True, sim=FormationSim(),
                      predictor=BattlePredictor(), on_event=lambda k, d: events.append((k, d)))
    assert rule.applies(st, act) is True
    rule.act(act)
    assert moves and moves[0][2]["big"] == {"x": 6, "y": 7}  # big moved to front slot
    assert any(k == "formation_plan" for k, d in events)
    assert act.calls and act.calls[0][0] == "occupy"
