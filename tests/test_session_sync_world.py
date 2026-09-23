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
