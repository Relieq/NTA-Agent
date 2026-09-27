from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self):
        self.state = GameState(source="api")
        self.state.raw = {}
        self.sent = []

    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params))
        return {}


def test_add_build_sends_route():
    s = FakeSession()
    Actions(s).add_build(109726, 2016)
    assert s.sent[0] == ("game/HD_AddAreaBuild", {"index": 109726, "id": 2016})


def test_create_city_sends_route():
    s = FakeSession()
    Actions(s).create_city(331273, 2102)   # Cứ Điểm / fort
    assert s.sent[0] == ("game/HD_CreateCity", {"index": 331273, "id": 2102})


def test_add_build_applies_its_reply_to_state():
    # issue #82: the reply {build, queues, output} was ignored -> the planner saw an
    # empty queue and no new building, picked the same id again -> ecode.500013
    from nta_agent.state.schema import Building
    s = FakeSession()
    s.state.main_city_index = 109726
    s.state.builds = [Building(index=109726, id=2002, lv=5, uid="g1")]
    reply = {"build": {"index": 109726, "uid": "g2", "id": 2002, "lv": 0},
             "queues": [{"index": 109726, "uid": "g2", "id": 2002, "lv": 1, "needTime": 1000}]}
    s.request = lambda route, params=None, timeout=15: reply
    Actions(s).add_build(109726, 2002)
    assert s.state.build_queue == reply["queues"]
    by_uid = {b.uid: b for b in s.state.builds}
    assert by_uid["g2"].id == 2002                   # the new (second) granary is known
    assert by_uid["g1"].lv == 5                      # and the first one was NOT overwritten


def test_resync_builds_from_area_info():
    s = FakeSession()
    s.state.main_city_index = 109726
    from nta_agent.state.schema import Building
    s.state.builds = [Building(index=109726, id=2001, lv=1, uid="m"),
                      Building(index=5, id=2102, lv=1, uid="f")]      # another cell kept
    area = {"data": {"index": 109726, "builds": [
        {"index": 109726, "uid": "m", "id": 2001, "lv": 2},
        {"index": 109726, "uid": "g", "id": 2002, "lv": 1}]}}
    s.request = lambda route, params=None, timeout=15: area
    Actions(s).resync_city_builds()
    got = sorted((b.index, b.id, b.lv) for b in s.state.builds)
    assert got == [(5, 2102, 1), (109726, 2001, 2), (109726, 2002, 1)]
