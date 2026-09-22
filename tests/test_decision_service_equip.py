import json

from nta_agent.runtime.commands import append_command
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.decision_service import DecisionService
from nta_agent.state.schema import GameState
from tests.test_equipment import FakeConfig


class FakeActions:
    def __init__(self, armies=None):
        self.calls = []
        self.attr_calls = []
        self._armies = armies or []

    def change_pawn_equip(self, pawn_id, equip_uid, skin_id=0, attack_speed=0):
        self.calls.append((pawn_id, equip_uid, skin_id, attack_speed))
        return {}

    def get_player_armys(self):
        return self._armies

    def change_pawn_attr(self, index, army_uid, pawn_uid, equip_uid, *,
                         sync_equip=1, skin_id=0, attack_speed=0):
        self.attr_calls.append((index, army_uid, pawn_uid, equip_uid, sync_equip))
        return {}


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def _state():
    st = GameState(source="api")
    st.raw = {"player": {
        "configPawnMap": {"3101": {"equipUid": "e1", "skinId": 0, "attackSpeed": 6}},
        "equips": [{"uid": "e1", "id": 6001}],
    }}
    return st


def test_tick_writes_equipment_json(tmp_path):
    cfg = _cfg(tmp_path)
    DecisionService(FakeActions(), FakeConfig(), cfg).tick(_state())
    rows = json.loads(cfg.equipment_path.read_text(encoding="utf-8"))
    assert rows[0]["pawn_id"] == 3101 and rows[0]["current_equip_name"] == "Kiếm Sắt"


def test_equip_command_calls_change_pawn_equip(tmp_path):
    cfg = _cfg(tmp_path)
    act = FakeActions()
    svc = DecisionService(act, FakeConfig(), cfg)
    append_command(cfg.commands_path, {"action": "equip", "pawn_id": 3101,
                                       "equip_uid": "e1", "skin_id": 0, "attack_speed": 6})
    svc.tick(_state())
    svc.tick(_state())  # once-only
    assert act.calls == [(3101, "e1", 0, 6)]


def test_equip_command_also_equips_existing_pawns(tmp_path):
    cfg = _cfg(tmp_path)
    armies = [{"uid": "A", "index": 5, "state": 0,
               "pawns": [{"uid": "p1", "id": 3101}, {"uid": "p2", "id": 3101}]}]
    act = FakeActions(armies)
    svc = DecisionService(act, FakeConfig(), cfg)
    append_command(cfg.commands_path, {"action": "equip", "pawn_id": 3101,
                                       "equip_uid": "e1", "skin_id": 0, "attack_speed": 6})
    svc.tick(_state())
    assert act.calls == [(3101, "e1", 0, 6)]            # config set
    # existing pawns equipped via one sync_equip=1 call (applies to all of the type)
    assert act.attr_calls == [(5, "A", "p1", "e1", 1)]
