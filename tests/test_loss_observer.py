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
    """Battle list that grows over time; full records by uid."""
    def __init__(self, records=None, full=None):
        self.records = list(records or [])
        self.full = full or {}
        self.fetched = []

    def get_battle_records_list(self):
        return list(self.records)

    def get_battle_record(self, uid):
        self.fetched.append(uid)
        return self.full.get(uid, {})


class Bridge:
    def replay(self, record):
        return {"summary": {"self_dead": 1}, "hits": [], "enemy_ids": [4116], "self_ids": [3305]}

    def counterfactual(self, record, orders):
        return {"by_order": {"tank_first": {"self_dead": 0}, "auto": {"self_dead": 1}}}


def _rec(uid, end, dead=0, index=79000):
    r = {"uid": uid, "index": index, "endTime": end}
    if dead:
        r["deadInfo"] = [{}] * dead
    return r


def test_new_lossy_record_is_recorded_with_replay_and_counterfactual(tmp_path):
    led = FailureLedger(tmp_path / "f.json")
    acts = Acts([_rec("old", 1, dead=5)], {"b1": {"frames": [1], "uid": "b1"}})
    obs = LossObserver(acts, led, Bridge(), player_uid="1000000000", poll_every=1)
    obs.tick(St(injured=0))                 # baseline: "old" predates us -> ignored
    acts.records.append(_rec("b1", 2, dead=2, index=73165))
    obs.tick(St(injured=2))
    ev = led.recent(5, kind="battle_loss")
    assert len(ev) == 1
    ctx = ev[0].context
    assert ctx["record_uid"] == "b1" and ctx["cell"] == 73165
    assert ctx["counterfactual"]["best_order"] == "tank_first"
    assert ctx["enemy_ids"] == [4116] and ctx["aoe"] is False


def test_picks_the_lossy_record_not_the_latest(tmp_path):
    """Live 2026-09-25: the old code replayed the newest battle (0 deaths)."""
    led = FailureLedger(tmp_path / "f.json")
    acts = Acts([])
    obs = LossObserver(acts, led, None, player_uid="x", poll_every=1)
    obs.tick(St(injured=0))
    acts.records += [_rec("lossy", 10, dead=8, index=72563), _rec("clean", 20, index=68976)]
    obs.tick(St(injured=8))
    ev = led.recent(5, kind="battle_loss")
    assert [e.context["record_uid"] for e in ev] == ["lossy"]
    assert ev[0].context["self_dead"] == 8          # no bridge -> deadInfo count
    assert acts.fetched == ["lossy"]


def test_each_record_once_and_found_without_injury_signal(tmp_path):
    """Injuries can be cured/revived between ticks -> the poll still catches it."""
    led = FailureLedger(tmp_path / "f.json")
    acts = Acts([])
    obs = LossObserver(acts, led, None, player_uid="x", poll_every=2)
    obs.tick(St(injured=0))                         # tick 0: baseline scan
    acts.records.append(_rec("b1", 5, dead=1))
    obs.tick(St(injured=0))                         # tick 1: not due, no rise
    assert led.all() == []
    obs.tick(St(injured=0))                         # tick 2: due -> found
    obs.tick(St(injured=0))
    obs.tick(St(injured=0))                         # tick 4: due again, already seen
    assert len(led.recent(5, kind="battle_loss")) == 1


def test_clean_battles_and_flat_injuries_record_nothing(tmp_path):
    led = FailureLedger(tmp_path / "f.json")
    acts = Acts([])
    obs = LossObserver(acts, led, None, player_uid="x", poll_every=1)
    obs.tick(St(injured=1))
    acts.records.append(_rec("win", 3))
    obs.tick(St(injured=1))
    assert led.all() == []


def test_unmatched_injury_rise_is_recorded_after_a_few_scans(tmp_path):
    led = FailureLedger(tmp_path / "f.json")
    obs = LossObserver(Acts([]), led, None, player_uid="x", poll_every=100, give_up_after=2)
    obs.tick(St(injured=0))
    obs.tick(St(injured=3))                          # rise, no record explains it
    assert led.all() == []
    obs.tick(St(injured=3))                          # 2nd scan -> give up, record delta
    ev = led.recent(5, kind="battle_loss")
    assert len(ev) == 1 and ev[0].context["self_dead"] == 3 and ev[0].context["unmatched"]
    obs.tick(St(injured=3))
    assert len(led.recent(5, kind="battle_loss")) == 1
