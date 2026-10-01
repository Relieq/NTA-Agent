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


# ---- 2026-10-01: chests earned during the session were never claimed -----------------------
def test_the_new_treasure_push_sets_and_clears_the_flag():
    from nta_agent.state.store import apply_player_update
    st = GameState(source="api")
    st.raw = {"player": {"hasNewTreasure": False}}
    apply_player_update(st, {"type": 50, "data_50": True})          # an army earned a chest
    assert st.raw["player"]["hasNewTreasure"] is True
    apply_player_update(st, {"type": 50})                            # protobuf drops false
    assert st.raw["player"]["hasNewTreasure"] is False


def test_a_chest_pushed_mid_session_is_claimed():
    from nta_agent.state.store import apply_player_update
    st = GameState(source="api")
    st.raw = {"player": {}}                                          # nothing pending at login
    armies = [{"uid": "A", "index": 5, "pawns": [{"id": 3101, "treasures": [{"id": 1}]}]}]
    calls = []
    rule = ClaimTreasures()
    act = _actions(armies, calls)
    assert rule.applies(st, act) is False                            # nothing flagged yet
    apply_player_update(st, {"type": 50, "data_50": True})           # ... then the push arrives
    assert rule.applies(st, act) is True
    rule.act(act)
    assert [k for k, _ in calls] == ["open", "claim"]


def test_a_missed_push_is_made_up_by_a_periodic_look():
    t = [1000.0]
    st = GameState(source="api")
    st.raw = {"player": {}}                                          # the flag never turns on
    armies = [{"uid": "A", "index": 5, "pawns": [{"id": 3101, "treasures": [{"id": 1}]}]}]
    fetched = []
    act = SimpleNamespace(get_player_armys=lambda: fetched.append(1) or armies,
                          open_armys_treasure=lambda targets: None,
                          claim_armys_treasure=lambda targets: None)
    rule = ClaimTreasures(clock=lambda: t[0])
    assert rule.applies(st, act) is False and fetched == []         # baseline, still cheap
    t[0] += 300
    assert rule.applies(st, act) is False and fetched == []         # within the interval
    t[0] += 301
    assert rule.applies(st, act) is True and fetched == [1]         # 10 minutes: it looks, finds it
