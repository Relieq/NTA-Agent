"""End-to-end: real Node sidecar + real engine via SimBattlePredictor.

Skipped unless Node and the decrypted engine are present, so CI without them
stays green. This is the client-parity proof for the known matchup.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from nta_agent.execution.predictors.sim_bridge import SimBridge
from nta_agent.execution.predictors.sim_predictor import SimBattlePredictor
from nta_agent.state.schema import GameState, User

_ENGINE = Path(__file__).resolve().parents[1] / "tools" / "re" / "decrypted" / "index.js"
_HAS_NODE = shutil.which("node") is not None

pytestmark = pytest.mark.skipif(
    not (_HAS_NODE and _ENGINE.exists()),
    reason="requires node + decrypted engine (tools/re/decrypted/index.js)",
)

_ENEMY_CONF = {
    "index": 109725,
    "hp": [25, 25],
    "armys": [
        {
            "index": 109725, "uid": "e", "state": 0, "name": "", "owner": "",
            "pawns": [{"uid": "e1", "id": 4101, "lv": 1, "hp": [25, 25], "point": {"x": 7, "y": 7}}],
        }
    ],
}


def test_predict_target_real_engine_known_win():
    bridge = SimBridge(timeout=60)
    try:
        assert bridge.available() is True, "sidecar should ping"
        pred = SimBattlePredictor(bridge=bridge)
        state = GameState(user=User(uid="1000000000"))
        army = {"uid": "a", "name": "D1", "index": 109726,
                "pawns": [{"uid": "p", "id": 3101, "lv": 1, "hp": [135, 135]}]}
        out = pred.predict_target(
            state, army, target_index=109725, land_id=0, distance=1,
            enemy_army_conf=_ENEMY_CONF,
        )
        assert out.win is True
        assert out.loss_lv == 0
    finally:
        bridge.close()
