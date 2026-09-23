import pytest

from nta_agent.execution.heuristics import OccupyCell


class Acts:
    def __init__(self, result=None, raise_ecode=None):
        self._result = result or []
        self._raise = raise_ecode

    def select_armies(self, index):
        if self._raise:
            raise RuntimeError(f"game/HD_GetSelectArmys: ecode.{self._raise}")
        return self._result


def test_select_idle_returns_empty_on_area_full():
    # a candidate cell already at the army limit -> [] (skip), never raises
    for ec in ("500037", "500081", "500080"):
        assert OccupyCell()._select_idle(Acts(raise_ecode=ec), 5, set()) == []


def test_select_idle_reraises_real_error():
    with pytest.raises(RuntimeError):
        OccupyCell()._select_idle(Acts(raise_ecode="500000"), 5, set())


def test_select_idle_filters_busy_and_locked():
    armies = [
        {"uid": "idle", "state": 0, "pawns": [{"id": 1}]},
        {"uid": "marching", "state": 1, "pawns": [{"id": 1}]},
        {"uid": "drilling", "state": 0, "pawns": [{"id": 1}], "drillPawns": [1]},
        {"uid": "locked", "state": 0, "pawns": [{"id": 1}]},
    ]
    out = OccupyCell()._select_idle(Acts(result=armies), 5, {"locked"})
    assert [a["uid"] for a in out] == ["idle"]
