from nta_agent.data.config import GameConfig
from nta_agent.execution.build_planner import next_build_action
from nta_agent.state.schema import Building, GameState


def _state(builds, cereal=99999, timber=99999, stone=99999, iron=99999):
    st = GameState(source="api")
    st.builds = builds
    st.resources.cereal = cereal
    st.resources.timber = timber
    st.resources.stone = stone
    st.resources.iron = iron
    st.build_queue = []
    st.build_queue_slots = 2
    st.main_city_index = 109726
    return st


def _b(bid, lv, uid=None):
    return Building(id=bid, lv=lv, uid=uid or f"u{bid}", index=109726)


def test_constructs_missing_unlocked_building():
    c = GameConfig.load()
    st = _state([_b(2001, 10)])  # main hall only
    act = next_build_action(st, c, sequence=[2016])  # Y Quán, prep ""
    assert act is not None and act.kind == "construct" and act.build_id == 2016
    assert act.up.level == 1


def test_respects_bt_count_then_upgrades():
    c = GameConfig.load()
    st = _state([_b(2001, 5)])
    act = next_build_action(st, c, sequence=[2001])
    assert act.kind == "upgrade" and act.build_id == 2001 and act.up.level == 6


def test_multi_instance_granary_constructs_until_max():
    c = GameConfig.load()
    st = _state([_b(2001, 10), _b(2002, 1)])
    act = next_build_action(st, c, sequence=[2002])
    assert act.kind == "construct" and act.build_id == 2002


def test_skips_blocked_construct():
    c = GameConfig.load()
    st = _state([_b(2001, 10)])
    act = next_build_action(st, c, sequence=[2016], blocked={("construct", 2016)})
    assert act is None


def test_unaffordable_construct_skipped():
    c = GameConfig.load()
    st = _state([_b(2001, 10)], cereal=0, timber=0, stone=0, iron=0)
    act = next_build_action(st, c, sequence=[2016])
    assert act is None


def test_construct_first_beats_available_upgrade():
    c = GameConfig.load()
    # wall (2000) present & upgradeable, granary (2002) missing -> construct wins.
    st = _state([_b(2001, 10), _b(2000, 5)])
    act = next_build_action(st, c, sequence=[2000, 2002])
    assert act.kind == "construct" and act.build_id == 2002


def test_default_order_includes_unbuilt_in_city_types():
    c = GameConfig.load()
    # sequence=None: an unbuilt type (e.g. 2016 Y Quán) must still be constructable.
    st = _state([_b(2001, 10)])
    act = next_build_action(st, c)  # no sequence
    assert act is not None and act.kind == "construct"
    assert act.build_id in c.in_city_build_ids()


def test_skip_excludes_from_construct_and_upgrade():
    c = GameConfig.load()
    st = _state([_b(2001, 10), _b(2000, 5)])
    # skip both candidates -> nothing
    assert next_build_action(st, c, sequence=[2000, 2002], skip={2000, 2002}) is None
    # skip only 2002 -> falls back to upgrading 2000
    act = next_build_action(st, c, sequence=[2000, 2002], skip={2002})
    assert act.kind == "upgrade" and act.build_id == 2000


def test_room_type_excludes_wrong_mode_market():
    c = GameConfig.load()
    st = _state([_b(2001, 10)])
    # newbie (room_type=1): Chợ Tự Do (2006) is free-only -> never constructed
    assert next_build_action(st, c, sequence=[2006], room_type=1) is None
    # free (room_type=0): 2006 is valid -> constructed
    act = next_build_action(st, c, sequence=[2006], room_type=0)
    assert act is not None and act.kind == "construct" and act.build_id == 2006
