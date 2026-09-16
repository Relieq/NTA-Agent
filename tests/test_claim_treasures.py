from types import SimpleNamespace

from nta_agent.execution.heuristics import ClaimTreasures
from nta_agent.state.schema import GameState


def _actions(armies, calls):
    return SimpleNamespace(
        get_player_armys=lambda: armies,
        open_armys_treasure=lambda targets: calls.append(("open", targets)),
        claim_armys_treasure=lambda targets: calls.append(("claim", targets)))


def test_opens_and_claims_armies_with_pending_treasures():
    st = GameState(source="api"); st.raw = {"player": {"hasNewTreasure": True}}
    armies = [{"uid": "A", "index": 5, "pawns": [{"id": 3101, "treasures": [{"id": 1}]}]},
              {"uid": "B", "index": 6, "pawns": [{"id": 3101, "treasures": []}]}]
    calls = []
    rule = ClaimTreasures()
    act = _actions(armies, calls)
    assert rule.applies(st, act) is True
    rule.act(act)
    kinds = {k for k, _ in calls}
    assert "open" in kinds and "claim" in kinds
    opened = next(t for k, t in calls if k == "open")
    assert opened == [{"index": 5, "auid": "A"}]     # only army A had pending


def test_no_pending_does_not_apply():
    st = GameState(source="api"); st.raw = {"player": {"hasNewTreasure": True}}
    armies = [{"uid": "A", "index": 5, "pawns": [{"id": 3101, "treasures": []}]}]
    assert ClaimTreasures().applies(st, _actions(armies, [])) is False


def test_gate_skips_when_no_new_treasure_flag():
    st = GameState(source="api"); st.raw = {"player": {}}  # flag absent
    armies = [{"uid": "A", "index": 5, "pawns": [{"id": 3101, "treasures": [{"id": 1}]}]}]
    calls = []
    assert ClaimTreasures().applies(st, _actions(armies, calls)) is False
    assert calls == []  # never fetched armies (cheap gate)


def test_respects_chest_budget():
    st = GameState(source="api")
    st.raw = {"player": {"hasNewTreasure": True, "treasureOpenCount": 1}}
    armies = [{"uid": "A", "index": 5, "pawns": [{"id": 3101, "treasures": [{"id": 1}]}]},
              {"uid": "B", "index": 6, "pawns": [{"id": 3101, "treasures": [{"id": 2}]}]}]
    calls = []
    rule = ClaimTreasures()
    act = _actions(armies, calls)
    assert rule.applies(st, act) is True
    rule.act(act)
    opened = next(t for k, t in calls if k == "open")
    assert len(opened) == 1   # budget = 1 -> only one army opened
