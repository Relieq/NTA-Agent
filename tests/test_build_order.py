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


def test_build_order_backs_off_on_queue_full_ecode():
    """500014 (queue full) is global — the drill task holds the slot but wasn't in
    our build_queue, so the pre-check passed. Back off quietly, don't spam."""
    from nta_agent.io.api.client import ApiError

    class QueueFullActs(Acts):
        def add_build(self, index, build_id):
            raise ApiError("game/HD_AddAreaBuild: ecode.500014")

    st = _state([Building(id=2001, lv=10, uid="m", index=109726)])
    act = QueueFullActs()
    rule = BuildOrder(sequence=[2016], config=GameConfig.load())
    assert rule.applies(st, act) is True
    rule.act(act)                        # must NOT raise
    assert rule._cooldown == rule.queue_cooldown
    # and it skips next tick while cooling down
    assert rule.applies(st, act) is False


def test_build_order_yields_to_pending_fort():
    # A queued Cứ Điểm has priority: BuildOrder must yield while the queue is non-empty.
    st = _state([Building(id=2001, lv=10, uid="m", index=109726)])
    rule = BuildOrder(sequence=[2016], config=GameConfig.load(),
                      pending_forts_source=lambda: [331273])
    assert rule.applies(st, Acts()) is False
    # queue empty -> resumes normally
    rule2 = BuildOrder(sequence=[2016], config=GameConfig.load(),
                       pending_forts_source=list)
    assert rule2.applies(st, Acts()) is True


def test_rejected_build_is_reported_and_resyncs(tmp_path=None):
    # issue #82: 500013/500014/500034 were swallowed (no event, rule "fired"); state
    # stayed out of sync with the server forever. Report it and resync the builds.
    from nta_agent.io.api.client import ApiError

    class BusyActs(Acts):
        resynced = 0

        def add_build(self, index, build_id):
            raise ApiError("game/HD_AddAreaBuild: ecode.500013")

        def resync_city_builds(self):
            BusyActs.resynced += 1

    events = []
    st = _state([Building(id=2001, lv=10, uid="m", index=109726)])
    act = BusyActs()
    rule = BuildOrder(sequence=[2016], config=GameConfig.load(),
                      on_event=lambda k, d: events.append((k, d)))
    assert rule.applies(st, act) is True
    rule.act(act)
    assert BusyActs.resynced == 1
    assert events == [("build_rejected", {"kind": "construct", "build_id": 2016,
                                          "ecode": "500013"})]


def test_duplicate_not_maxed_error_names_the_build():
    from nta_agent.io.api.client import ApiError

    class DupActs(Acts):
        def add_build(self, index, build_id):
            raise ApiError("game/HD_AddAreaBuild: ecode.500034")

        def resync_city_builds(self):
            pass

    st = _state([Building(id=2001, lv=10, uid="m", index=109726)])
    rule = BuildOrder(sequence=[2016], config=GameConfig.load())
    rule.applies(st, DupActs())
    try:
        rule.act(DupActs())
        raise AssertionError("expected a raise")
    except Exception as e:
        assert "500034" in str(e) and "2016" in str(e)   # errors.jsonl says WHAT was built


def test_dashboard_lists_build_rejections(tmp_path):
    import json

    from nta_agent.dashboard.server import read_build_rejections
    from nta_agent.runtime.config import RuntimeConfig
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    cfg.event_log_path.write_text("\n".join(json.dumps(e) for e in [
        {"ts": 1, "kind": "build_rejected", "detail": {"kind": "construct", "build_id": 2002, "ecode": "500034"}},
        {"ts": 2, "kind": "tick"},
        {"ts": 3, "kind": "build_rejected", "detail": {"kind": "construct", "build_id": 2003, "ecode": "500013"}},
    ]), encoding="utf-8")
    rows = read_build_rejections(cfg)
    assert [r["build_id"] for r in rows] == [2003, 2002]              # newest first
    assert rows[0]["reason"] == "đã có trong hàng đợi xây"
