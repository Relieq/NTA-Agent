"""Marshal GameState + a target into the sidecar's Forecast Input schema."""
from __future__ import annotations

from nta_agent.execution.predictors.sim_input import build_forecast_input
from nta_agent.state.schema import GameState, User


def _state(uid: str = "100") -> GameState:
    return GameState(user=User(uid=uid))


def test_build_forecast_input_minimal():
    state = _state("100")
    army = {
        "uid": "a1",
        "name": "D1",
        "index": 109726,
        "pawns": [{"uid": "p1", "id": 3101, "lv": 1, "hp": [135, 135]}],
    }
    inp = build_forecast_input(state, [army], target_index=109725, land_id=0, distance=1)

    assert inp["playerUid"] == "100"
    assert inp["targetCellIndex"] == 109725
    assert inp["landId"] == 0
    assert inp["selfToCellDistance"] == 1
    assert inp["areaSize"] is None
    assert inp["enemyArmyConf"] is None
    assert inp["armies"][0]["uid"] == "a1"
    assert inp["armies"][0]["name"] == "D1"
    assert inp["armies"][0]["index"] == 109726
    assert inp["armies"][0]["marchTime"] == 0
    assert inp["armies"][0]["pawns"][0] == {
        "uid": "p1",
        "id": 3101,
        "lv": 1,
        "hp": [135, 135],
        "buffs": [],
        "skills": [],
        "treasures": [],
        "hero": None,
    }


def test_build_forecast_input_passes_optional_fields():
    state = _state("42")
    army = {
        "uid": "a2",
        "index": 5,
        "pawns": [
            {
                "uid": "p2",
                "id": 3205,
                "lv": 3,
                "hp": [200, 220],
                "buffs": [{"type": 1}],
                "skills": [7],
                "treasures": [{"id": 9}],
                "hero": {"id": 100},
            }
        ],
    }
    inp = build_forecast_input(
        state, [army], target_index=5, land_id=101, distance=2, area_size=15
    )
    assert inp["areaSize"] == 15
    assert inp["armies"][0]["name"] == "D1"  # default name when absent
    p = inp["armies"][0]["pawns"][0]
    assert p["buffs"] == [{"type": 1}]
    assert p["skills"] == [7]
    assert p["treasures"] == [{"id": 9}]
    assert p["hero"] == {"id": 100}
