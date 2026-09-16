from nta_agent.data.config import GameConfig
from nta_agent.execution.heuristics import BuildOrder
from nta_agent.state.schema import Building, GameState


def _state(builds):
    st = GameState(source="api")
    st.builds = builds
    for r in ("cereal", "timber", "stone", "iron"):
        setattr(st.resources, r, 99999)
    st.build_queue = []
    st.build_queue_slots = 2
    st.main_city_index = 109726
    return st


class Acts:
    def __init__(self):
        self.calls = []

    def add_build(self, index, build_id):
        self.calls.append(("add", index, build_id))
        return {}

    def upgrade_build(self, index, uid=""):
        self.calls.append(("up", index, uid))
        return {}


def test_build_order_constructs_missing():
    st = _state([Building(id=2001, lv=10, uid="m", index=109726)])
    act = Acts()
    rule = BuildOrder(sequence=[2016], config=GameConfig.load())
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls == [("add", 109726, 2016)]


def test_build_order_upgrades_existing():
    st = _state([Building(id=2001, lv=5, uid="m", index=109726)])
    act = Acts()
    rule = BuildOrder(sequence=[2001], config=GameConfig.load())
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls == [("up", 109726, "m")]


def test_build_order_skips_when_build_queue_full():
    # single slot already busy -> every build attempt would hit ecode.500014
    st = _state([Building(id=2001, lv=5, uid="m", index=109726)])
    st.build_queue = [{"uid": "m"}]
    st.build_queue_slots = 1
    rule = BuildOrder(sequence=[2001], config=GameConfig.load())
    assert rule.applies(st, Acts()) is False


def test_build_order_runs_when_queue_has_a_free_slot():
    st = _state([Building(id=2001, lv=5, uid="m", index=109726)])
    st.build_queue = [{"uid": "x"}]  # 1 busy of 2 -> a slot is free
    st.build_queue_slots = 2
    rule = BuildOrder(sequence=[2001], config=GameConfig.load())
    assert rule.applies(st, Acts()) is True


from nta_agent.execution.profile import Profile


def _profile(order, skip):
    return Profile(army={"group": [], "roles": {}, "onetile": True, "composition": {},
                         "active": "", "presets": {}},
                   occupy={}, notes=[], build={"order": order, "skip": skip})


def test_build_order_skips_wall_via_profile():
    st = _state([Building(id=2001, lv=10, uid="m", index=109726),
                 Building(id=2000, lv=5, uid="w", index=109726)])
    act = Acts()
    rule = BuildOrder(profile=_profile(order=[], skip=[2000]), config=GameConfig.load())
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls and act.calls[0][0] == "add"      # a construct, not wall upgrade


def test_build_order_prioritizes_profile_order():
    st = _state([Building(id=2001, lv=10, uid="m", index=109726)])
    act = Acts()
    rule = BuildOrder(profile=_profile(order=[2016], skip=[]), config=GameConfig.load())
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls == [("add", 109726, 2016)]
