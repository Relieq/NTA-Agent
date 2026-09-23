"""Occupy discovery + OccupyCell rule (fake get_area/actions; no network)."""

from dataclasses import dataclass, field

from nta_agent.execution.heuristics import OccupyCell
from nta_agent.execution.occupy_planner import discover_around, discover_targets
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


def test_discover_skips_cells_whose_probe_errors():
    # A get_area that raises on some cells (edge/fog -> ecode.500000) must not
    # crash discovery; those cells are simply skipped.
    center = 182 * W + 526
    world = {
        center: _cell(owner="me", city=1001),           # my city (enables adjoin)
        center - 1: _cell(owner="", pawns=[100, 100]),  # occupiable
    }

    def probe(i):
        if i not in world:
            raise RuntimeError("game/HD_GetAreaInfo: ecode.500000")
        return world[i]

    cands = discover_targets(probe, center, 1, my_uid="me")
    assert {c.index for c in cands} == {center - 1}


def test_discover_around_covers_army_frontier():
    # City far from a frontier army; a defended cell sits next to the ARMY, not the
    # city. discover_around (centers = city + army) must find it; probing only the
    # city (radius 1) would miss it.
    city = 100 * W + 100
    army = 100 * W + 110          # 10 cells east of the city (owned frontier)
    world = {
        city: _cell(owner="me"),
        army: _cell(owner="me"),               # army stands on an owned cell
        army + 1: _cell(owner="", pawns=[100]),  # defended cell next to the army
    }
    # city-only discovery (radius 1) misses it
    assert discover_targets(lambda i: world.get(i, {}), city, 1, "me") == []
    # multi-center discovery finds the army-adjacent target
    cands = discover_around(lambda i: world.get(i, {}), {city, army}, 1, "me")
    assert {c.index for c in cands} == {army + 1}


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


def test_occupy_rule_spiral_prefers_least_exposed():
    from types import SimpleNamespace
    center = 182 * W + 526
    st = GameState(source="api")
    st.user.uid = "me"
    st.main_city_index = center
    st.resources.stamina = 10
    areas = {
        center: _cell(owner="me", city=1001),        # owned city
        center + 2: _cell(owner="me"),               # owned -> gives B a 2nd owned neighbour
        center - 1: _cell(owner="", pawns=[50]),     # A: 1 owned neighbour (center)
        center + 1: _cell(owner="", pawns=[50]),     # B: 2 owned neighbours (center, center+2)
    }
    my_army = [{"index": center, "uid": "A", "pawns": [{"hp": 500}, {"hp": 500}], "state": None}]
    act = FakeActions(areas=areas, armies=my_army)
    prof = SimpleNamespace(occupy={"expansion": "spiral", "max_loss": 100,
                                   "loot": {"enabled": True}},
                           army={"group": [], "presets": {}, "active": ""})
    rule = OccupyCell(radius=2, predictor=BattlePredictor(), profile=prof)
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls[0][1] == center - 1  # spiral chose the least-exposed (1-neighbour) cell


def test_expansion_breaks_ties_toward_nearest_cell():
    """Two winnable cells tie on the spiral key (owned_neighbors=1, loss=0). The
    ranking MUST break the tie toward the NEAREST cell — otherwise it picks by
    arbitrary discovery order and can chase a far cell (which then needs bridging
    and loops), starving near 0-loss cells. Regression for the observed skip bug.
    """
    from types import SimpleNamespace

    from nta_agent.execution.advisor import Plan
    from nta_agent.execution.occupy_planner import Candidate

    center = 182 * W + 526
    near = center - 1          # dist 1 from the army at `center`
    far = center + 15          # dist 15 from the army
    cands = [
        Candidate(index=far, defenders=[{"id": 1}], hp=(3, 3), land_id=0, owned_neighbors=1),
        Candidate(index=near, defenders=[{"id": 1}], hp=(3, 3), land_id=0, owned_neighbors=1),
    ]  # far listed FIRST -> arbitrary discovery order favours it without a distance tiebreak

    def plans_for(i):
        return [Plan(armies=[{"uid": "A", "index": center}], target=i, label="x", prediction=None)]

    def predict(plan):
        return BattlePrediction(win=True, my_power=10, enemy_power=1, ratio=10,
                                loss_percent=0.0, loss_lv=1)

    prof = SimpleNamespace(occupy={"expansion": "spiral", "max_loss": 100},
                           army={"group": [], "presets": {}, "active": ""})
    rule = OccupyCell(profile=prof)
    plan = rule._expansion_select(cands, plans_for, predict, "spiral")
    assert plan is not None
    assert plan.target == near  # nearest of the tied winnable cells, not the far one


def test_occupy_rule_defends_contested_border_first():
    # A weak far cell (high loot) vs a weak cell next to an enemy (contested).
    # With a threat present, defense wins: claim the cell adjacent to the enemy.
    center = 182 * W + 526
    st = GameState(source="api")
    st.user.uid = "me"
    st.main_city_index = center
    st.resources.stamina = 10
    areas = {
        center: _cell(owner="me", city=1001),
        center - 1: _cell(owner="", pawns=[50]),   # contested: enemy sits at center-2
        center + 1: _cell(owner="", pawns=[50]),   # safe expansion cell
    }
    my_army = [{"index": center, "uid": "A", "pawns": [{"hp": 500}, {"hp": 500}], "state": None}]
    act = FakeActions(areas=areas, armies=my_army)
    rule = OccupyCell(radius=1, predictor=BattlePredictor(),
                      threats_source=lambda: {center - 2})  # enemy adjacent to center-1
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls[0][1] == center - 1  # defended the contested border cell


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


# ---- Phase 2 (corrected): order-based formation optimization ------------- #
class OrderFormationSim:
    """predict_armies: win with 0 loss when 'big' is FIRST in the pawn list, else 50%."""
    def predict_armies(self, state, armies, *, target_index, land_id, distance, **kw):
        pawns = armies[0].get("pawns", []) if armies else []
        big_first = bool(pawns and pawns[0].get("uid") == "big")
        loss = 0.0 if big_first else 50.0
        pred = BattlePrediction(win=True, my_power=1, enemy_power=1, ratio=1,
                                loss_percent=loss, loss_lv=0)
        pred.pawn_survival = [{"uid": p["uid"], "camp": 2,
                               "alive": big_first or p["uid"] == "big", "curHp": 100} for p in pawns]
        return pred


def test_occupy_optimizes_troop_order_before_attack():
    center = 182 * W + 526
    st = GameState(source="api"); st.user.uid = "me"; st.main_city_index = center
    st.resources.stamina = 10
    # formation source: get_area(city) returns the tank army with pawns in list
    # order [sml, big] (squishy first) -> beefy-first should reorder to [big, sml]
    tank_area = {"index": center, "uid": "tank", "owner": "me",
                 "pawns": [{"uid": "sml", "id": 3101, "lv": 1, "hp": [50, 50]},
                           {"uid": "big", "id": 3101, "lv": 1, "hp": [200, 200]}]}
    areas = {center: {"owner": "me", "cityId": 1001, "armys": [tank_area], "hp": [3, 3]},
             center - 1: _cell(owner="", pawns=[50])}
    tank = {"index": center, "uid": "tank",
            "pawns": [{"uid": "sml", "id": 3101}, {"uid": "big", "id": 3101}]}
    swaps = []

    class Acts(FakeActions):
        def exchange_pawn_army(self, index, army_uid, uid1, uid2, army_uid2=None):
            swaps.append((index, army_uid, uid1, uid2)); return {}

    act = Acts(areas=areas, armies=[tank])
    events = []
    rule = OccupyCell(radius=1, use_sim=True, sim=OrderFormationSim(),
                      predictor=BattlePredictor(), on_event=lambda k, d: events.append((k, d)))
    assert rule.applies(st, act) is True
    rule.act(act)
    # one swap of sml<->big to make big first (the tanking slot)
    assert swaps and {swaps[0][2], swaps[0][3]} == {"sml", "big"}
    assert swaps[0][0] == center and swaps[0][1] == "tank"
    assert any(k == "formation_plan" and d["label"] == "beefy-first" for k, d in events)
    assert act.calls and act.calls[0][0] == "occupy"


# ---- B1: profile-driven chest-budget farming ----------------------------- #
def test_occupy_uses_profile_farming_within_budget(monkeypatch):
    from nta_agent.execution import treasure_model as tm
    from nta_agent.execution.profile import Profile
    from nta_agent.execution.treasure_model import CellLoot
    center = 182 * W + 526
    st = GameState(source="api"); st.user.uid = "me"; st.main_city_index = center
    st.resources.stamina = 10
    st.raw = {"player": {"treasureOpenCount": 1}}  # budget = 1 chest

    def cell(owner="", pawns=(), city=0, landId=0):
        return {"owner": owner, "cityId": city, "landId": landId,
                "armys": [{"pawns": [{"hp": h} for h in pawns]}] if pawns else [], "hp": [3, 3]}

    areas = {center: cell(owner="me", city=1001),
             center - 1: cell(pawns=[50], landId=11),   # high reward/chest
             center + 1: cell(pawns=[50], landId=22)}    # low reward/chest
    army = [{"index": center, "uid": "A", "pawns": [{"hp": 500}, {"hp": 500}]}]
    act = FakeActions(areas=areas, armies=army)
    # max_loss=10 accommodates the stats-fallback predictor (reports ~5% even on
    # crushing wins); with the real sim, 0-loss cells report 0. Tests the farming
    # ranking, not the loss threshold.
    prof = Profile(army={"group": ["A"], "roles": {}, "onetile": True, "composition": {},
                         "active": "", "presets": {}},
                   occupy={"max_loss": 10, "max_march_ms": 0,
                           "loot": {"enabled": True, "min_reward_per_chest": 0}}, notes=[],
                   build={"order": [], "skip": []})
    monkeypatch.setattr(tm, "cell_loot",
                        lambda land, cfg: CellLoot(1, 100.0) if land == 11 else CellLoot(1, 10.0))
    events = []
    rule = OccupyCell(radius=1, use_sim=False, predictor=BattlePredictor(),
                      profile=prof, config=object(), on_event=lambda k, d: events.append((k, d)))
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls and act.calls[0][1] == center - 1   # higher reward/chest cell chosen
    assert any(k == "farm_plan" for k, d in events)


def test_occupy_uses_active_preset_group():
    from nta_agent.execution.profile import Profile
    center = 182 * W + 526
    st = GameState(source="api"); st.user.uid = "me"; st.main_city_index = center
    st.resources.stamina = 10
    areas = {center: _cell(owner="me", city=1001), center - 1: _cell(owner="", pawns=[50])}
    cung = {"index": center, "uid": "cung", "pawns": [{"id": 3305}, {"id": 3305}]}
    tank = {"index": center, "uid": "tank", "pawns": [{"id": 3101}, {"id": 3101}]}
    other = {"index": center, "uid": "extra", "pawns": [{"id": 3101}]}  # NOT in preset
    act = FakeActions(areas=areas, armies=[cung, tank, other])
    prof = Profile(army={"group": [], "roles": {}, "onetile": True, "composition": {},
                         "active": "duo", "presets": {"duo": {"group": ["cung", "tank"],
                         "roles": {}, "onetile": True, "composition": {}}}},
                   occupy={"max_loss": 100, "max_march_ms": 0,
                           "loot": {"enabled": False, "min_reward_per_chest": 0}}, notes=[],
                   build={"order": [], "skip": []})

    class Sim:
        def predict_armies(self, state, armies, **kw):
            from nta_agent.execution.predictors.battle import BattlePrediction
            return BattlePrediction(win=True, my_power=1, enemy_power=1, ratio=1,
                                    loss_percent=0, loss_lv=0)

    rule = OccupyCell(radius=1, use_sim=True, sim=Sim(), predictor=BattlePredictor(), profile=prof)
    assert rule.applies(st, act) is True
    rule.act(act)
    # only preset armies used; "extra" excluded even though select_armies returned it
    assert act.calls
    used = set(act.calls[0][2])
    assert used <= {"cung", "tank"} and "extra" not in used and used


def test_occupy_skips_discovery_when_stamina_below_min():
    """Pacing: no get_area probes when stamina can't afford an occupy."""
    from nta_agent.state.schema import User

    st = GameState(source="api")
    st.user = User(uid="me")
    st.main_city_index = 100 * W + 100
    st.resources.stamina = 0

    calls = []

    class Acts:
        def get_area(self, i, **kw):
            calls.append(i)
            return {"data": {}}

    rule = OccupyCell(min_stamina=1)
    assert rule.applies(st, Acts()) is False
    assert calls == []          # no discovery probes when stamina is short


def test_min_occupy_stamina_from_config():
    from nta_agent.data.config import GameConfig
    from nta_agent.execution.occupy_planner import min_occupy_stamina

    assert min_occupy_stamina(GameConfig.load()) >= 1


def test_occupy_skips_busy_army():
    # The only reachable army is FIGHTING (state=2) -> can't be sent -> no plan.
    center = 182 * W + 526
    st = GameState(source="api"); st.user.uid = "me"; st.main_city_index = center
    st.resources.stamina = 10
    areas = {center: _cell(owner="me", city=1001), center - 1: _cell(owner="", pawns=[50])}
    busy = [{"index": center, "uid": "A", "pawns": [{"hp": 500}], "state": 2}]
    act = FakeActions(areas=areas, armies=busy)
    rule = OccupyCell(radius=1, predictor=BattlePredictor())
    assert rule.applies(st, act) is False


def test_discover_frontier_keeps_defended_unowned_cells():
    from nta_agent.execution.occupy_planner import discover_frontier
    world = {
        10: _cell(owner="", pawns=[100, 100]),   # defended wild -> candidate
        11: _cell(owner="", pawns=[]),            # empty frontier -> skip
        12: _cell(owner="me", pawns=[100]),       # mine -> skip
        13: _cell(owner="enemy", city=2001),      # enemy city -> skip
        14: _cell(owner="", pawns=[50]),          # defended wild -> candidate
    }
    cands = discover_frontier(lambda i: world.get(i, {}), {10, 11, 12, 13, 14}, my_uid="me")
    assert {c.index for c in cands} == {10, 14}
    assert all(c.owned_neighbors == 1 for c in cands)


def test_occupy_quiets_benign_500080():
    """A 500080 (duplicate/race: army already at/marching to target) is benign —
    expansion still happens. It must NOT raise or log an occupy_error."""
    center = 182 * W + 526
    st = GameState(source="api")
    st.user.uid = "me"
    st.main_city_index = center
    st.resources.stamina = 10
    areas = {
        center: _cell(owner="me", city=1001),
        center - 1: _cell(owner="", pawns=[50]),
    }
    my_army = [{"index": center, "uid": "A", "pawns": [{"hp": 500}, {"hp": 500}], "state": None}]

    class Acts(FakeActions):
        def occupy_cell(self, target, armies, **kw):
            raise RuntimeError("game/HD_OccupyCell: ecode.500080")

    act = Acts(areas=areas, armies=my_army)
    events = []
    rule = OccupyCell(radius=1, predictor=BattlePredictor(), on_event=lambda k, d: events.append(k))
    assert rule.applies(st, act) is True
    rule.act(act)   # must NOT raise
    assert "occupy_error" not in events   # benign -> quiet


def test_occupy_bridges_to_forward_cell_for_far_target():
    """For a FAR target, act() stages the army at the in-zone owned cell nearest
    the target (MoveCellArmy) instead of attacking directly this tick."""
    from types import SimpleNamespace
    city = 100 * W + 100
    target = 100 * W + 112          # 12 east — outside the radius-6 zone
    fwd = 100 * W + 106             # owned, in-zone, near target
    rule = OccupyCell(radius=1)
    rule._pending = ([{"uid": "A", "index": city}], target)
    rule._state_ref = SimpleNamespace(main_city_index=city)
    rule.territory_source = lambda: ({city + 1, city + 600, fwd, 100 * W + 103}, [city])
    calls = []

    class Acts:
        def get_player_armys(self):
            return [{"uid": "A", "index": city, "state": 0, "pawns": [{"id": 3101}]}]
        def move_cell_army(self, armies, tgt):
            calls.append(("move", tgt, [a["uid"] for a in armies]))
        def occupy_cell(self, tgt, armies):
            calls.append(("occupy", tgt))

    rule.act(Acts())
    assert calls == [("move", fwd, ["A"])]   # bridged (staged), did not attack yet


def test_occupy_no_bridge_for_near_target():
    from types import SimpleNamespace
    city = 100 * W + 100
    target = 100 * W + 103          # within the zone -> attack directly
    rule = OccupyCell(radius=1)
    rule._pending = ([{"uid": "A", "index": city}], target)
    rule._state_ref = SimpleNamespace(main_city_index=city)
    rule.territory_source = lambda: ({city + 1, 100 * W + 102}, [city])
    calls = []

    class Acts:
        def get_player_armys(self):
            return [{"uid": "A", "index": city, "state": 0, "pawns": [{"id": 3101}]}]
        def move_cell_army(self, armies, tgt):
            calls.append(("move", tgt))
        def occupy_cell(self, tgt, armies):
            calls.append(("occupy", tgt))

    rule.act(Acts())
    assert calls == [("occupy", target)]     # near -> direct attack, no bridge


def test_occupy_bridge_failure_falls_back_to_direct_attack():
    """If the relay cell can't take the armies (ecode.500037 — staging area full),
    bridging must NOT get stuck: fall through to a direct occupy so expansion still
    advances (bridging is only a speed optimization)."""
    from types import SimpleNamespace
    city = 100 * W + 100
    target = 100 * W + 112          # far -> would bridge
    fwd = 100 * W + 106             # owned, in-zone relay (but full)
    rule = OccupyCell(radius=1)
    rule._pending = ([{"uid": "A", "index": city}], target)
    rule._state_ref = SimpleNamespace(main_city_index=city)
    rule.territory_source = lambda: ({city + 1, city + 600, fwd, 100 * W + 103}, [city])
    events = []
    rule.on_event = lambda k, d: events.append((k, d))
    calls = []

    class Acts:
        def get_player_armys(self):
            return [{"uid": "A", "index": city, "state": 0, "pawns": [{"id": 3101}]}]
        def move_cell_army(self, armies, tgt):
            raise RuntimeError("game/HD_MoveCellArmy: ecode.500037")  # area full
        def occupy_cell(self, tgt, armies):
            calls.append(("occupy", tgt))

    rule.act(Acts())
    assert calls == [("occupy", target)]                 # fell back to a direct attack
    assert any(k == "bridge_skip" for k, _ in events)     # surfaced the skipped relay
