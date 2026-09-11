"""Rule engine + agent-loop logic, driven by fakes (no network)."""

from dataclasses import dataclass, field

from nta_agent.execution.actions import Actions
from nta_agent.execution.heuristics import CollectCityOutput, RuleEngine
from nta_agent.state.schema import GameState


@dataclass
class FakeSession:
    state: GameState
    calls: list = field(default_factory=list)
    synced: int = 0

    def request(self, route, params=None, timeout=15):
        self.calls.append((route, params or {}))
        return {}

    def sync(self):
        self.synced += 1
        return self.state


def _state(cereal, granary, warehouse, main_city=109726):
    st = GameState(source="api")
    st.resources.cereal = cereal
    st.resources.timber = warehouse  # full
    st.resources.stone = warehouse   # full
    st.raw = {"player": {"mainCityIndex": main_city,
                         "granaryCap": granary, "warehouseCap": warehouse}}
    return st


def test_collect_rule_applies_when_below_cap():
    rule = CollectCityOutput()
    assert rule.applies(_state(cereal=500, granary=1000, warehouse=1000)) is True


def test_collect_rule_skips_when_at_cap():
    rule = CollectCityOutput()
    assert rule.applies(_state(cereal=1000, granary=1000, warehouse=1000)) is False


def test_collect_rule_skips_when_caps_unknown():
    st = GameState(source="api")  # no player caps
    assert CollectCityOutput().applies(st) is False


def test_engine_fires_and_acts():
    s = FakeSession(state=_state(cereal=500, granary=1000, warehouse=1000))
    engine = RuleEngine.default()
    fired = engine.tick(s.state, Actions(s))
    assert fired == ["collect_city_output"]
    assert s.calls == [("game/HD_ClaimCityOutput", {"index": 109726})]


def test_engine_isolates_rule_errors():
    class Boom:
        name = "boom"
        def applies(self, state):
            return True
        def act(self, actions):
            raise RuntimeError("nope")

    fired = RuleEngine(rules=[Boom()]).tick(GameState(), Actions(FakeSession(GameState())))
    assert fired and fired[0].startswith("boom!ERR:")
