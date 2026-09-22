import types

from nta_agent.execution.heuristics import _record_res_block
from nta_agent.execution.ledger import FailureLedger
from nta_agent.execution.loss_observer import LossObserver


def test_record_res_block_writes_to_ledger(tmp_path):
    led = FailureLedger(tmp_path / "f.json")
    rule = types.SimpleNamespace(name="forge", ledger=led)
    _record_res_block(rule, "iron")
    assert led.aggregate_res(3600) == {"iron": 1}


def test_record_res_block_noop_without_ledger():
    _record_res_block(types.SimpleNamespace(name="forge"), "iron")  # no ledger attr set
    # no exception = pass


class St:
    def __init__(self, injured, main=79542):
        self.raw = {"player": {"injuryPawns": [{}] * injured}}
        self.main_city_index = main


class Acts:
    def __init__(self, records, record):
        self._records, self._record = records, record

    def get_battle_records_list(self):
        return self._records

    def get_battle_record(self, uid):
        return self._record


class Bridge:
    def replay(self, record):
        return {"summary": {"self_dead": 1}, "hits": [], "enemy_ids": [4116], "self_ids": [3305]}

    def counterfactual(self, record, orders):
        return {"by_order": {"tank_first": {"self_dead": 0}, "auto": {"self_dead": 1}}}


def test_injury_rise_records_battle_loss_with_counterfactual(tmp_path):
    led = FailureLedger(tmp_path / "f.json")
    acts = Acts([{"uid": "b1", "index": 79000, "endTime": 2}, {"uid": "b0", "endTime": 1}],
                {"frames": [1], "uid": "b1", "index": 79000})
    obs = LossObserver(acts, led, Bridge(), player_uid="1000000000")
    obs.tick(St(injured=0))    # baseline
    obs.tick(St(injured=2))    # +2 dead -> record a loss
    ev = led.recent(1, kind="battle_loss")
    assert ev
    assert ev[0].context["counterfactual"]["best_order"] == "tank_first"
    assert ev[0].context["enemy_ids"] == [4116]
    assert ev[0].context["aoe"] is False


def test_no_loss_when_injury_flat(tmp_path):
    led = FailureLedger(tmp_path / "f.json")
    obs = LossObserver(Acts([], {}), led, None, player_uid="x")
    obs.tick(St(injured=1))
    obs.tick(St(injured=1))
    assert led.all() == []


def test_records_loss_even_without_bridge(tmp_path):
    led = FailureLedger(tmp_path / "f.json")
    obs = LossObserver(Acts([{"uid": "b1", "index": 5, "endTime": 1}], {"frames": [1]}),
                       led, None, player_uid="x")  # no bridge -> injury-delta only
    obs.tick(St(injured=0))
    obs.tick(St(injured=3))
    ev = led.recent(1, kind="battle_loss")
    assert ev and ev[0].context["self_dead"] == 3
