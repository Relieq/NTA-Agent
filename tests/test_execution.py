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
    assert rule.applies(_state(cereal=500, granary=1000, warehouse=1000), None) is True


def test_collect_rule_skips_when_at_cap():
    rule = CollectCityOutput()
    assert rule.applies(_state(cereal=1000, granary=1000, warehouse=1000), None) is False


def test_collect_rule_tries_when_caps_unknown():
    # Caps unknown -> still claim: it's the only thing that refreshes the true
    # stock, and a static stored value goes stale (froze stone/cereal at 0 and
    # stalled builds). The 500171/cap-full backoff bounds the retries.
    st = GameState(source="api")  # no player caps
    assert CollectCityOutput().applies(st, None) is True


class _RaisingActions:
    """collect_city_output raises the given ApiError message; others no-op."""
    def __init__(self, msg):
        self._msg = msg
    def collect_city_output(self, index=None):
        from nta_agent.io.api.client import ApiError
        raise ApiError(self._msg)


def test_collect_unclaimable_500171_swallowed_and_backs_off():
    rule = CollectCityOutput()
    act = _RaisingActions("game/HD_ClaimCityOutput: ecode.500171")
    rule.act(act)  # must NOT raise (expected "nothing to claim")
    assert rule._cooldown == 20      # first back-off = fail_cooldown
    rule._cooldown = 0
    rule.act(act)
    assert rule._cooldown == 40      # escalates: 20 * 2
    rule._cooldown = 0
    rule.act(act)
    assert rule._cooldown == 80      # 20 * 4


def test_collect_unclaimable_backoff_capped():
    rule = CollectCityOutput(max_cooldown=100)
    act = _RaisingActions("x: ecode.500171")
    for _ in range(10):
        rule._cooldown = 0
        rule.act(act)
    assert rule._cooldown == 100     # never exceeds max_cooldown


def test_collect_other_error_still_raises():
    import pytest

    from nta_agent.io.api.client import ApiError
    rule = CollectCityOutput()
    act = _RaisingActions("game/HD_ClaimCityOutput: ecode.500008")
    with pytest.raises(ApiError):
        rule.act(act)
    assert rule._cooldown == 20


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


def test_agent_recovers_from_transient_drop():
    from nta_agent.execution import Agent
    from nta_agent.io.api.client import NotConnected

    @dataclass
    class FlakySession:
        state: GameState
        fail_syncs: int = 1
        recovered: int = 0
        def sync(self):
            if self.fail_syncs > 0:
                self.fail_syncs -= 1
                raise NotConnected("down")
            return self.state
        def recover(self, timeout=15):
            self.recovered += 1
            return True

    s = FlakySession(state=GameState())
    agent = Agent(session=s)
    ticks_seen = []
    agent.run(ticks=1, interval=0, on_tick=lambda i, f, st: ticks_seen.append(i))
    assert s.recovered == 1
    assert ticks_seen == [0]  # tick completed after recovery


def test_agent_run_raises_on_broken_token_chain():
    from nta_agent.execution import Agent
    from nta_agent.io.api.client import NotConnected
    from nta_agent.io.api.session import TokenChainBroken

    @dataclass
    class DeadSession:
        state: GameState
        def sync(self):
            raise NotConnected("down")
        def recover(self, timeout=15):
            raise TokenChainBroken("spent")

    try:
        Agent(session=DeadSession(state=GameState())).run(ticks=1, interval=0)
        assert False, "expected TokenChainBroken"
    except TokenChainBroken:
        pass
