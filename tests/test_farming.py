from types import SimpleNamespace

from nta_agent.execution.farming import FarmPick, plan_farm
from nta_agent.execution.treasure_model import CellLoot


def _cell(i, land):
    return SimpleNamespace(index=i, land_id=land)


def _plan(cell, win, loss):
    return SimpleNamespace(armies=[{"uid": "a"}], target=cell.index, label="x",
                           prediction=SimpleNamespace(win=win, loss_percent=loss))


def test_picks_highest_reward_per_chest_within_budget():
    cells = [_cell(1, 11), _cell(2, 22), _cell(3, 33)]
    loot = {1: CellLoot(2, 100.0), 2: CellLoot(1, 90.0), 3: CellLoot(3, 30.0)}
    picks = plan_farm(cells, lambda c: _plan(c, True, 0), lambda c: loot[c.index],
                      budget=3, max_loss=0)
    # reward/chest: cell2=90, cell1=50, cell3=10 -> cell2(1) + cell1(2) fills budget 3
    assert [p.cell.index for p in picks] == [2, 1]


def test_filters_by_max_loss_and_min_reward():
    cells = [_cell(1, 11), _cell(2, 22)]
    loot = {1: CellLoot(1, 5.0), 2: CellLoot(1, 100.0)}
    picks = plan_farm(cells,
                      lambda c: _plan(c, c.index == 1, 0 if c.index == 1 else 80),
                      lambda c: loot[c.index], budget=5, max_loss=0,
                      min_reward_per_chest=10)
    assert picks == []  # cell1 below min_reward_per_chest; cell2 not winnable


def test_farmpick_carries_plan_and_loot():
    cells = [_cell(1, 11)]
    picks = plan_farm(cells, lambda c: _plan(c, True, 0),
                      lambda c: CellLoot(1, 50.0), budget=5, max_loss=0)
    assert isinstance(picks[0], FarmPick)
    assert picks[0].plan.target == 1 and picks[0].loot.reward_value == 50.0
