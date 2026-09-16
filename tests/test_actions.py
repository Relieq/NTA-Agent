"""Actions unit tests with a fake session (no network)."""

from dataclasses import dataclass, field
from typing import Any

from nta_agent.execution import Actions
from nta_agent.state.schema import GameState


@dataclass
class FakeSession:
    """Records requests and returns canned replies."""
    state: GameState
    calls: list[tuple[str, dict]] = field(default_factory=list)
    replies: dict[str, Any] = field(default_factory=dict)

    def request(self, route: str, params: dict | None = None, timeout: float = 15) -> dict:
        self.calls.append((route, params or {}))
        return self.replies.get(route, {})


def _state_with_main_city(idx: int) -> GameState:
    st = GameState(source="api")
    st.raw = {"player": {"mainCityIndex": idx}}
    return st


def test_main_city_index_from_rst():
    s = FakeSession(state=_state_with_main_city(109726))
    assert Actions(s).main_city_index() == 109726


def test_collect_city_output_targets_main_city_and_returns_rewards():
    s = FakeSession(
        state=_state_with_main_city(109726),
        replies={"game/HD_ClaimCityOutput": {"rewards": {"cereal": {"value": 50}}}},
    )
    rewards = Actions(s).collect_city_output()
    assert s.calls == [("game/HD_ClaimCityOutput", {"index": 109726})]
    assert rewards == {"cereal": {"value": 50}}


def test_upgrade_build_passes_index_and_uid():
    s = FakeSession(state=_state_with_main_city(1))
    Actions(s).upgrade_build(870, uid="u1")
    assert s.calls == [("game/HD_UpAreaBuild", {"index": 870, "uid": "u1"})]


def test_get_map_chunk_requests_route_with_chunk_id():
    s = FakeSession(
        state=_state_with_main_city(1),
        replies={"game/HD_GetMapChunk": {"cells": {"57696053": {}}}},
    )
    reply = Actions(s).get_map_chunk(11)
    assert s.calls == [("game/HD_GetMapChunk", {"chunkId": 11})]
    assert reply == {"cells": {"57696053": {}}}


def test_collect_requires_a_city():
    s = FakeSession(state=GameState(source="api"))  # no mainCityIndex, no areas
    try:
        Actions(s).collect_city_output()
        assert False, "expected ValueError"
    except ValueError:
        pass
