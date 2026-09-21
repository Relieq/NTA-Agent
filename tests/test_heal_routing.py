from nta_agent.execution.heuristics import HealRouting
from nta_agent.state.schema import GameState, User


def _state(main, forts):
    st = GameState(source="api")
    st.user = User(uid="me")
    st.main_city_index = main
    st.raw = {"player": {"mainCityIndex": main, "fortAutoSupports": forts}}
    return st


class FakeActions:
    def __init__(self, armies):
        self._armies = armies
        self.moved = []

    def get_player_armys(self):
        return self._armies

    def move_cell_army(self, armies, target, **kw):
        self.moved.append(([a["uid"] for a in armies], target))
        return {}


def test_routes_wounded_army_to_main():
    main = 100 * 600 + 100
    st = _state(main, forts=[])
    armies = [
        {"index": 105 * 600 + 100, "uid": "hurt", "pawns": [{"hp": [10, 100]}]},
        {"index": main, "uid": "ok", "pawns": [{"hp": [100, 100]}]},
    ]
    acts = FakeActions(armies)
    rule = HealRouting(check_every=0, fort_capacity=5)
    assert rule.applies(st, acts) is True
    rule.act(acts)
    assert acts.moved == [(["hurt"], main)]


def test_skips_locked_army():
    # a wounded army the ArmyComposer owns must not be routed away to heal.
    main = 100 * 600 + 100
    st = _state(main, forts=[])
    armies = [{"index": 105 * 600 + 100, "uid": "hurt", "pawns": [{"hp": [10, 100]}]}]
    acts = FakeActions(armies)
    rule = HealRouting(check_every=0)
    rule.locked_source = lambda: {"hurt"}
    assert rule.applies(st, acts) is False
    assert acts.moved == []


def test_no_action_when_all_healthy():
    main = 100 * 600 + 100
    st = _state(main, forts=[])
    armies = [{"index": main, "uid": "ok", "pawns": [{"hp": [100, 100]}]}]
    acts = FakeActions(armies)
    rule = HealRouting(check_every=0)
    assert rule.applies(st, acts) is False


def test_skips_army_already_at_heal_node():
    main = 100 * 600 + 100
    st = _state(main, forts=[])
    # wounded but already sitting at the main city -> already healing, don't move
    armies = [{"index": main, "uid": "healing", "pawns": [{"hp": [10, 100]}]}]
    acts = FakeActions(armies)
    rule = HealRouting(check_every=0)
    assert rule.applies(st, acts) is False


def test_skips_wounded_army_that_is_busy():
    main = 100 * 600 + 100
    st = _state(main, forts=[])
    # wounded but MARCHING (state=1) -> cannot be moved -> not routed
    armies = [{"index": 105 * 600 + 100, "uid": "hurt", "state": 1,
               "pawns": [{"hp": [10, 100]}]}]
    acts = FakeActions(armies)
    assert HealRouting(check_every=0).applies(st, acts) is False
