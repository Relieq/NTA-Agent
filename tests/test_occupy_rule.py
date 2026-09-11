"""Occupy discovery + OccupyCell rule (fake get_area/actions; no network)."""

from dataclasses import dataclass, field

from nta_agent.execution.heuristics import OccupyCell
from nta_agent.execution.occupy_planner import discover_targets
from nta_agent.execution.predictors.battle import BattlePredictor
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
