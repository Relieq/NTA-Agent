"""session.sync routes world notifies (marches/capture) separately from player ones."""
from types import SimpleNamespace

from nta_agent.io.api.session import GameSession, PushRecord
from nta_agent.state import from_entry_rst


def _fake(pushes):
    st = from_entry_rst({"player": {"uid": "me", "mainCityIndex": 5,
        "btQueues": [{"index": 5, "uid": "b1", "id": 2001, "lv": 6, "surplusTime": 999999}]}})
    st.user.uid = "me"
    return SimpleNamespace(state=st, _bt_deadlines={}, drain_pushes=lambda: pushes)


def test_sync_routes_world_notify():
    world = PushRecord(ts=0, route="game/OnUpdateWorldInfo",
                       msg_type="GAME_ONUPDATEWORLDINFO_NOTIFY",
                       data={"list": [
                           {"type": 13, "data_13": {"uid": "m1", "owner": "enemy",
                                                    "targetIndex": 5, "surplusTime": 1000}},
                           {"type": 6},        # a world type-6 must NOT wipe the build queue
                           {"type": 29, "data_29": {"uid": "me", "attacker": "enemy", "time": 3}},
                       ]})
    fake = _fake([world])
    GameSession.sync(fake)
    st = fake.state
    assert "m1" in st.world_marches
    assert st.raw["player"]["captureInfo"]["uid"] == "enemy"
    assert len(st.build_queue) == 1


def test_sync_still_applies_player_notify():
    player = PushRecord(ts=0, route="game/OnUpdatePlayerInfo",
                        msg_type="GAME_ONUPDATEPLAYERINFO_NOTIFY",
                        data={"list": [{"type": 6, "data_6": []}]})
    fake = _fake([player])
    GameSession.sync(fake)
    assert fake.state.build_queue == []


def test_sync_applies_area_build_notify():
    """GAME_ONUPDATEAREAINFO_NOTIFY is NOT list-wrapped ({type, index, data_<type>}).
    It carries building level-ups (BUILD_UP=5), new buildings (ADD_BUILD=8) and
    removals (REMOVE_BUILD=9); ignoring it froze the agent's building levels (the
    main hall reached lv7 on the server while the dashboard still showed lv1)."""
    fake = _fake([])
    st = fake.state
    st.main_city_index = 5
    st.builds = []
    from nta_agent.state.store import _building
    st.builds.append(_building({"index": 5, "uid": "h", "id": 2001, "lv": 1}))
    pushes = [
        PushRecord(ts=0, route="game/OnUpdateAreaInfo", msg_type="GAME_ONUPDATEAREAINFO_NOTIFY",
                   data={"type": 5, "index": 5, "data_5": {"index": 5, "uid": "h", "id": 2001, "lv": 7}}),
        PushRecord(ts=0, route="game/OnUpdateAreaInfo", msg_type="GAME_ONUPDATEAREAINFO_NOTIFY",
                   data={"type": 8, "index": 5, "data_8": {"index": 5, "uid": "f", "id": 2008, "lv": 1}}),
        PushRecord(ts=0, route="game/OnUpdateAreaInfo", msg_type="GAME_ONUPDATEAREAINFO_NOTIFY",
                   data={"type": 5, "index": 999, "data_5": {"index": 999, "uid": "x", "id": 2001, "lv": 9}}),
    ]
    fake.drain_pushes = lambda: pushes
    GameSession.sync(fake)
    lv = {b.id: b.lv for b in st.builds}
    assert lv[2001] == 7          # level-up applied
    assert lv.get(2008) == 1      # new building added
    assert len(st.builds) == 2    # another area's build ignored
    fake.drain_pushes = lambda: [PushRecord(
        ts=0, route="game/OnUpdateAreaInfo", msg_type="GAME_ONUPDATEAREAINFO_NOTIFY",
        data={"type": 9, "index": 5, "data_9": "f"})]
    GameSession.sync(fake)
    assert {b.id for b in st.builds} == {2001}   # REMOVE_BUILD


def test_expired_build_queue_item_bumps_building_level():
    """No build-complete push reaches us reliably; when a queue item's time is up we
    drop it (existing) AND apply its target level to the building, like the client."""
    fake = _fake([])
    st = fake.state
    st.main_city_index = 5
    from nta_agent.state.store import _building
    st.builds = [_building({"index": 5, "uid": "k", "id": 2002, "lv": 1})]
    st.build_queue = [{"index": 5, "uid": "k", "id": 2002, "lv": 2, "surplusTime": 0}]
    fake._bt_deadlines = {"k": 0.0}             # already due
    GameSession.sync(fake)
    assert st.build_queue == []
    assert {b.id: b.lv for b in st.builds}[2002] == 2


def test_expired_queue_item_without_a_building_adds_nothing():
    """A finished BT-queue item whose uid matches no building (e.g. a pawn-type upgrade
    like 3202 Lv2) must not appear as a building."""
    st = from_entry_rst({"player": {"uid": "me", "mainCityIndex": 5,
        "builds": [{"index": 5, "uid": "h", "id": 2001, "lv": 6}],
        "btQueues": [{"index": 5, "uid": "p9", "id": 3202, "lv": 2, "surplusTime": 0}]}})
    fake = SimpleNamespace(state=st, _bt_deadlines={"p9": 0.0}, drain_pushes=list)
    GameSession.sync(fake)
    assert [(b.id, b.lv) for b in st.builds] == [(2001, 6)]
