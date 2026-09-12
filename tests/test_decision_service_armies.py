import json

from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.decision_service import DecisionService
from nta_agent.state.schema import GameState
from tests.test_armies import FakeConfig


class FakeActions:
    def __init__(self):
        self.armys_calls = 0

    def get_player_armys(self):
        self.armys_calls += 1
        return [{"uid": "a1", "name": "Đội 1", "index": 5, "state": 0, "marchSpeed": 100,
                 "pawns": [{"uid": "p1", "id": 3101, "lv": 1, "attackSpeed": 6, "equip": {"id": 6001}}]}]


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def _state():
    st = GameState(source="api")
    st.raw = {"player": {"configPawnMap": {}, "equips": [], "pawnSlots": {}, "policySlots": {}, "equipSlots": {}}}
    return st


def test_armies_fetched_on_throttle(tmp_path):
    cfg = _cfg(tmp_path)
    act = FakeActions()
    svc = DecisionService(act, FakeConfig(), cfg, armies_every=2)
    svc.tick(_state())   # first tick -> fetch
    rows = json.loads(cfg.armies_path.read_text(encoding="utf-8"))
    assert rows[0]["name"] == "Đội 1" and rows[0]["pawns"][0]["name"] == "Lính Trường Thương"
    assert act.armys_calls == 1
    svc.tick(_state())   # throttled: no fetch
    assert act.armys_calls == 1


def test_army_fetch_failure_is_swallowed(tmp_path):
    cfg = _cfg(tmp_path)

    class Boom:
        def get_player_armys(self):
            raise RuntimeError("net down")

    DecisionService(Boom(), FakeConfig(), cfg, armies_every=1).tick(_state())  # must not raise
