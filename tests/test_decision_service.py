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


class _EcodeConfig(FakeConfig):
    def table(self, name):
        if name == "ecode":
            return {500053: {"vi": "Vàng không đủ"}}
        return super().table(name)


def test_ecode_reason_maps_code():
    from nta_agent.runtime.decision_service import ecode_reason
    assert ecode_reason(_EcodeConfig(), "game/HD_CeriResetSelect: ecode.500053") == "Vàng không đủ"
    assert ecode_reason(_EcodeConfig(), "no code here") == ""
    assert ecode_reason(None, "ecode.500053") == ""


def test_decision_error_is_enriched(tmp_path):
    cfg = _cfg(tmp_path)
    events = []

    class BadActions(FakeActions):
        def study_select(self, lv, ceri_id, tp):
            raise RuntimeError("game/HD_StudySelect: ecode.500053")

    svc = DecisionService(BadActions(), _EcodeConfig(), cfg,
                          on_event=lambda k, d=None: events.append((k, d)))
    append_command(cfg.commands_path, {"action": "select", "track": "equip", "lv": 1, "ceri_id": 6015})
    svc.tick(_state())
    err = next(d for k, d in events if k == "decision_error")
    assert err["reason"] == "Vàng không đủ"
    assert err["action"] == "select" and err["track"] == "equip" and err["ceri_id"] == 6015
    assert "ecode.500053" in err["error"]


def test_profile_edit_command_applies_to_live_profile(tmp_path):
    from types import SimpleNamespace

    from nta_agent.execution.profile import load_profile
    from nta_agent.runtime.decision_service import DecisionService
    prof = load_profile("none")
    cfg = SimpleNamespace(
        decisions_path=tmp_path / "d.json", equipment_path=tmp_path / "e.json",
        armies_path=tmp_path / "a.json", commands_path=tmp_path / "c.jsonl",
        commands_done_path=tmp_path / "c.done")
    svc = DecisionService(actions=SimpleNamespace(get_player_armys=list),
                          config=None, cfg=cfg, profile=prof)
    svc._execute({"action": "profile_edit", "edits": {"occupy": {"max_loss": 9}}})
    assert prof.occupy["max_loss"] == 9


def test_build_fort_command_calls_add_build(tmp_path):
    acts = FakeActions()
    acts.add_build = lambda index, build_id: acts.calls.append(("add_build", index, build_id))
    svc = DecisionService(acts, FakeConfig(), _cfg(tmp_path))
    svc._execute({"action": "build_fort", "index": 123456})
    assert acts.calls == [("add_build", 123456, 2102)]  # FORT_BUILD_ID
