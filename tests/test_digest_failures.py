import types

from nta_agent.brain.digest import digest
from nta_agent.execution.ledger import FailureEvent


def P():
    return types.SimpleNamespace(army={}, occupy={}, build={}, revive={},
                                 logistics={}, notes=[])


def S():
    res = types.SimpleNamespace(**{k: 0 for k in (
        "cereal", "timber", "stone", "iron", "gold", "stamina",
        "exp_book", "up_scroll", "fixator")})
    return types.SimpleNamespace(resources=res, main_city_index=1, raw={"player": {}})


def test_digest_includes_failures_and_res_pressure():
    fails = [FailureEvent("e1", 1.0, "battle_loss",
             {"cell": 5, "self_dead": 1, "aoe": True, "enemy_ids": [4116],
              "counterfactual": {"best_order": "tank_first", "self_dead": 0}})]
    dg = digest(S(), P(), armies=[], failures=fails, res_pressure={"cereal": 4})
    assert dg["failures"][0]["id"] == "e1"
    assert dg["failures"][0]["kind"] == "battle_loss"
    assert dg["failures"][0]["counterfactual"]["best_order"] == "tank_first"
    assert dg["failures"][0]["aoe"] is True
    assert dg["res_pressure"] == {"cereal": 4}


def test_digest_omits_failure_keys_when_absent():
    dg = digest(S(), P(), armies=[])
    assert "failures" not in dg
    assert "res_pressure" not in dg
