"""Build planner: prereq + main-hall cap + affordability gating (fake config)."""

from dataclasses import dataclass

from nta_agent.data.config import BuildUpgrade
from nta_agent.execution.build_planner import next_upgrade
from nta_agent.state.schema import Building, GameState


@dataclass
class FakeConfig:
    """build_upgrade(id, lv) from a dict {(id,lv): BuildUpgrade}."""
    table: dict

    def build_upgrade(self, build_id, level):
        return self.table.get((build_id, level))


def _bu(bid, lv, cost, prep=""):
    return BuildUpgrade(build_id=bid, level=lv, cost=cost, time=60, effects=[], prep_cond=prep)


def _state(builds, cereal=9999, timber=9999, stone=9999):
    st = GameState(source="api")
    st.builds = [Building(index=i, id=bid, lv=lv, uid=f"u{i}")
                 for i, (bid, lv) in enumerate(builds)]
    st.resources.cereal, st.resources.timber, st.resources.stone = cereal, timber, stone
    return st


def test_picks_first_affordable_in_sequence():
    st = _state([(2001, 2), (2004, 1)])  # main hall lv2, barracks lv1
    cfg = FakeConfig({(2004, 2): _bu(2004, 2, {"timber": 100})})
    b, up = next_upgrade(st, cfg, sequence=[2004])
    assert b.id == 2004 and up.level == 2


def test_blocks_when_exceeding_main_hall_level():
    st = _state([(2001, 1), (2004, 1)])  # main hall lv1; barracks lv1 -> lv2 would exceed
    cfg = FakeConfig({(2004, 2): _bu(2004, 2, {"timber": 1})})
    assert next_upgrade(st, cfg, sequence=[2004]) is None


def test_blocks_on_unmet_prereq():
    # main hall lv9 (so the main-hall cap doesn't block), barracks lv1
    st = _state([(2001, 9), (2004, 1)])
    # barracks lv2 needs smithy (2008) lv3 -> we don't own a smithy -> unmet
    cfg = FakeConfig({(2004, 2): _bu(2004, 2, {"timber": 1}, prep="4,2008,3")})
    assert next_upgrade(st, cfg, sequence=[2004]) is None


def test_blocks_when_unaffordable():
    st = _state([(2001, 9), (2004, 1)], timber=10)
    cfg = FakeConfig({(2004, 2): _bu(2004, 2, {"timber": 100})})
    assert next_upgrade(st, cfg, sequence=[2004]) is None


def test_main_hall_not_self_capped():
    st = _state([(2001, 1)])
    cfg = FakeConfig({(2001, 2): _bu(2001, 2, {"timber": 1})})
    b, up = next_upgrade(st, cfg, sequence=[2001])
    assert b.id == 2001 and up.level == 2


def test_blocks_when_queue_full():
    st = _state([(2001, 1)])
    st.build_queue = [{"uid": "x", "id": 9999}]
    st.build_queue_slots = 1
    cfg = FakeConfig({(2001, 2): _bu(2001, 2, {"timber": 1})})
    assert next_upgrade(st, cfg, sequence=[2001]) is None


def test_skips_build_already_queued():
    st = _state([(2001, 5), (2004, 1)])
    # barracks is the one queued -> skip it, but main hall (lv5->6) is free
    st.builds[1].uid = "busy"
    st.build_queue = [{"uid": "busy", "id": 2004}]
    st.build_queue_slots = 2  # a slot is free
    cfg = FakeConfig({
        (2004, 2): _bu(2004, 2, {"timber": 1}),
        (2001, 6): _bu(2001, 6, {"timber": 1}),
    })
    b, up = next_upgrade(st, cfg, sequence=[2004, 2001])
    assert b.id == 2001  # barracks skipped (queued), main hall chosen
