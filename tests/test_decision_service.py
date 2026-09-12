import json

from nta_agent.runtime.commands import append_command
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.decision_service import DecisionService
from nta_agent.state.schema import GameState
from tests.test_decisions import FakeConfig  # reuse the minimal config


class FakeActions:
    def __init__(self):
        self.calls = []

    def study_select(self, lv, ceri_id, tp):
        self.calls.append(("select", lv, ceri_id, tp))
        return {"slots": {}}

    def ceri_reset(self, lv, tp):
        self.calls.append(("reroll", lv, tp))
        return {"selectIds": [1], "resetCount": 1}


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def _state():
    st = GameState(source="api")
    st.raw = {"player": {"pawnSlots": {"s0": {"selectIds": [3101, 3102], "id": 0, "resetCount": 0, "lv": 1}},
                          "policySlots": {}, "equipSlots": {}}}
    return st


def test_tick_writes_decisions(tmp_path):
    cfg = _cfg(tmp_path)
    svc = DecisionService(FakeActions(), FakeConfig(), cfg)
    svc.tick(_state())
    ds = json.loads(cfg.decisions_path.read_text(encoding="utf-8"))
    assert ds[0]["track"] == "pawn" and ds[0]["options"][0]["name"] == "Lính Trường Thương"


def test_tick_executes_select_once(tmp_path):
    cfg = _cfg(tmp_path)
    act = FakeActions()
    svc = DecisionService(act, FakeConfig(), cfg)
    append_command(cfg.commands_path, {"action": "select", "track": "pawn", "lv": 1, "ceri_id": 5})
    svc.tick(_state())
    svc.tick(_state())  # second tick must NOT re-run
    assert act.calls == [("select", 1, 5, 2)]


def test_tick_executes_reroll(tmp_path):
    cfg = _cfg(tmp_path)
    act = FakeActions()
    svc = DecisionService(act, FakeConfig(), cfg)
    append_command(cfg.commands_path, {"action": "reroll", "track": "policy", "lv": 2})
    svc.tick(_state())
    assert act.calls == [("reroll", 2, 1)]
