"""Build planner: prereq + main-hall cap + affordability gating (fake config)."""

from dataclasses import dataclass

from nta_agent.data.config import BuildUpgrade
from nta_agent.execution.build_planner import (
    _prep_ok,
    next_build_action,
    next_upgrade,
    parse_prep_cond,
)
from nta_agent.state.schema import Building, GameState


def test_parse_prep_cond_multi_and_malformed():
    assert parse_prep_cond("4,2001,7|4,2002,3|4,2003,3") == [
        (4, 2001, 7), (4, 2002, 3), (4, 2003, 3)]
    assert parse_prep_cond("4,2001,3") == [(4, 2001, 3)]
    assert parse_prep_cond("") == []
    assert parse_prep_cond("garbage|4,2001,3") == [(4, 2001, 3)]  # bad part skipped


def test_prep_ok_requires_all_conditions():
    cond = "4,2001,7|4,2002,3|4,2003,3"
    assert _prep_ok(cond, {2001: 7, 2002: 3, 2003: 3}) is True
    assert _prep_ok(cond, {2001: 7, 2002: 2, 2003: 3}) is False  # one short
    assert _prep_ok(cond, {2001: 7}) is False                    # missing two
    assert _prep_ok("", {}) is True                              # no conditions


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
    b, _up = next_upgrade(st, cfg, sequence=[2004, 2001])
    assert b.id == 2001  # barracks skipped (queued), main hall chosen


@dataclass
class FakeBuildCfg:
    """Fuller fake for next_build_action: upgrades + max_count + base + in-city.

    ``max_count`` maps id->cap; ``bases`` maps id->buildBase row; every id is
    treated as an in-city building.
    """
    table: dict
    counts: dict
    bases: dict = None

    def build_upgrade(self, build_id, level):
        return self.table.get((build_id, level))

    def max_count(self, build_id):
        return self.counts.get(build_id, 1)

    def build_base(self, build_id):
        return (self.bases or {}).get(build_id, {})

    def in_city_build_ids(self, room_type=None):
        return sorted({bid for bid, _lv in self.table} | set(self.counts))


def test_no_duplicate_construct_until_existing_maxed():
    # Granary (2002, bt_count -3 -> max_count 3) at lv2 with a lv3 available, so
    # NOT maxed. The engine forbids a 2nd copy until every copy is maxed (500034):
    # the planner must upgrade the existing one, not construct a duplicate.
    st = _state([(2001, 9), (2002, 2)])
    cfg = FakeBuildCfg(
        table={
            (2002, 1): _bu(2002, 1, {"timber": 1}),  # a fresh lv1 construct IS available
            (2002, 3): _bu(2002, 3, {"timber": 1}),  # existing lv2 -> lv3 -> not maxed
        },
        counts={2001: 1, 2002: 3},
    )
    act = next_build_action(st, cfg, sequence=[2002])
    assert act is not None
    assert act.kind == "upgrade" and act.build_id == 2002  # not a construct


def test_duplicate_construct_allowed_when_existing_maxed():
    # Same granary but already maxed (no lv+1 upgrade) -> a 2nd copy is allowed.
    st = _state([(2001, 9), (2002, 2)])
    cfg = FakeBuildCfg(
        table={(2002, 1): _bu(2002, 1, {"timber": 1})},  # only lv1 (fresh) exists
        counts={2001: 1, 2002: 3},
    )
    act = next_build_action(st, cfg, sequence=[2002])
    assert act is not None
    assert act.kind == "construct" and act.build_id == 2002
