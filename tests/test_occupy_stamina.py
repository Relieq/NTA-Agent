"""Stamina-aware target choice: a winnable level>=3 wild land whose chest we can pay for is
taken before richer-looking land we cannot get a chest from; without stamina the old order
stays. Candidate cells get their LAND id from the world map (get_area never sends it, so
every candidate used to carry land_id 0 and the 'richest land first' ranking was a no-op)."""
from types import SimpleNamespace

from nta_agent.data.config import GameConfig
from nta_agent.execution.advisor import Plan
from nta_agent.execution.heuristics import OccupyCell
from nta_agent.execution.occupy_planner import Candidate
from nta_agent.execution.predictors.battle import BattlePrediction

W = 600
MAIN = 100 * W + 100


def _rule(stamina, mode="octopus"):
    prof = SimpleNamespace(occupy={"expansion": mode, "max_loss": 100},
                           army={"group": [], "presets": {}, "active": ""})
    r = OccupyCell(profile=prof, config=GameConfig.load())
    r._stamina, r._main = stamina, MAIN
    return r


def _pick(rule, cands, mode="octopus"):
    def plans_for(i):
        return [Plan(armies=[{"uid": "A", "index": MAIN}], target=i, label="x", prediction=None)]

    def predict(plan):
        return BattlePrediction(win=True, my_power=10, enemy_power=1, ratio=10, loss_percent=0.0, loss_lv=1)
    return rule._expansion_select(cands, plans_for, predict, mode).target


def _cand(idx, land):
    return Candidate(index=idx, defenders=[{"id": 1}], hp=(3, 3), land_id=land, owned_neighbors=1)


LV5, LV3, LV1 = 305, 303, 301
C5, C3, C1 = MAIN + 6, MAIN + 5, MAIN + 4      # distances 5..7 from the city block


def test_enough_stamina_for_every_chest_keeps_the_richest_land_first():
    assert _pick(_rule(10), [_cand(C1, LV1), _cand(C3, LV3), _cand(C5, LV5)]) == C5


def test_stamina_for_a_lv3_chest_but_not_a_lv5_one_takes_the_lv3_cell():
    # lv5 needs 3 stamina, lv3 needs 1: with 1 on hand only the lv3 chest can drop
    assert _pick(_rule(1), [_cand(C1, LV1), _cand(C3, LV3), _cand(C5, LV5)]) == C3


def test_no_stamina_at_all_keeps_the_old_order():
    assert _pick(_rule(0), [_cand(C1, LV1), _cand(C3, LV3), _cand(C5, LV5)]) == C5


def test_level_1_and_2_chests_do_not_pull_the_choice():
    # only lv>=3 earns the stamina preference: lv1 affordable, lv5 not -> still the richer lv5
    assert _pick(_rule(1), [_cand(C1, LV1), _cand(C5, LV5)]) == C5


def test_spiral_mode_ignores_stamina():
    near, far = MAIN + 4, MAIN + 5
    cands = [_cand(far, LV3), _cand(near, LV1)]
    assert _pick(_rule(5, "spiral"), cands, "spiral") == near


def test_candidates_get_their_land_id_from_the_world_map():
    class World:
        def __init__(self):
            self.cells = [1]

        def detect(self, owned):
            return "maps_x"
        def land_id(self, idx):
            return {5: 305, 6: 303, 7: -1}[idx]
    r = _rule(5)
    c = [_cand(5, 0), _cand(6, 0), _cand(7, 0), _cand(8, 304)]
    r._label_lands(c, {1, 2}, world=World())
    assert [x.land_id for x in c] == [305, 303, 0, 304]   # unknown cell stays 0, a known id is kept
