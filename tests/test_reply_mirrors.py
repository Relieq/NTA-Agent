"""Action replies the game client applies and we used to drop (audit 2026-09-27)."""
from __future__ import annotations

from tests.test_exclusive_api import _acts


def test_pawn_lving_applies_its_cost():
    # reply {cost: UpdateOutPut, queues}: the exp-book spend went unseen
    acts, _s, st = _acts("game/HD_PawnLving", {"cost": {"flag": 0, "expBook": 7}, "queues": []})
    st.resources.exp_book = 9
    acts.pawn_lving(1, "A", "p")
    assert st.resources.exp_book == 7


def test_drill_pawn_keeps_the_drill_queues():
    acts, _s, st = _acts("game/HD_DrillPawn", {"queues": {"bar": {"list": [{"uid": "q1"}] * 6}}})
    acts.drill_pawn("bar", 3305, index=1)
    assert len(st.raw["player"]["pawnDrillQueues"]["bar"]) == 6
    assert st.raw["player"]["_pawnDrillQueuesAt"] > 0


def test_create_city_and_treasure_claims_apply_resources():
    acts, _s, st = _acts("game/HD_CreateCity", {"output": {"flag": 0, "stone": 5}})
    st.resources.stone = 900
    acts.create_city(1, 2102)
    assert st.resources.stone == 5
    acts, _s, st = _acts("game/HD_ClaimArmysTreasure", {"rewards": {"flag": 0, "stone": 950}})
    acts.claim_armys_treasure([{"index": 1, "auid": "A"}])
    assert st.resources.stone == 950
    acts, _s, st = _acts("game/HD_ClaimArmyTreasure", {"rewards": {"flag": 0, "stone": 960}})
    acts.claim_army_treasure(1, "A")
    assert st.resources.stone == 960


def test_dismiss_army_sends_the_schema_field():
    acts, s, _st = _acts("game/HD_DismissArmy", {})
    acts.dismiss_army(1, "A", 0)
    assert s.calls[-1] == ("game/HD_DismissArmy", {"index": 1, "armyUid": "A", "pawnId": 0})


def test_drill_queue_notify_replaces_the_map():
    from nta_agent.state import apply_notify, from_entry_rst
    st = from_entry_rst({"player": {"uid": "1"}})
    apply_notify(st, {"list": [{"type": 18, "data_18": {"bar": {"list": [{"uid": "a"}]}}}]})
    assert st.raw["player"]["pawnDrillQueues"] == {"bar": [{"uid": "a"}]}


def test_recruit_waits_while_the_drill_queue_is_full():
    # 258x ecode.500018 ("Ô chiêu mộ đã đầy"): the rule never looked at the queue
    import time

    from nta_agent.execution.heuristics import Recruit
    from tests.test_recruit import FakeActions, _state
    st = _state([3101])
    st.raw["player"]["pawnDrillQueues"] = {"bar": [{"uid": f"q{i}"} for i in range(6)]}
    st.raw["player"]["_pawnDrillQueuesAt"] = time.time()
    act = FakeActions(st, armys=[{"uid": "A", "pawns": [{}, {}], "state": None}])
    assert Recruit(config=False).applies(st, act) is False
    st.raw["player"]["_pawnDrillQueuesAt"] = time.time() - 3600     # stale view -> try again
    assert Recruit(config=False).applies(st, act) is True
