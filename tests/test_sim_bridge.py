"""Python <-> sidecar bridge: JSON-RPC over stdio, with fallback semantics.

Uses a fake sidecar (a tiny Python script speaking the same newline-JSON
protocol) so the test needs no Node.
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from nta_agent.execution.predictors.sim_bridge import SimBridge, SimUnavailable

FAKE_SIDECAR = textwrap.dedent(
    """
    import json, sys
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        mid, method = msg.get("id"), msg.get("method")
        if method == "ping":
            out = {"id": mid, "result": "pong"}
        elif method == "forecast":
            out = {"id": mid, "result": {"isWin": True, "lossLv": 1, "lossPercent": 5.0}}
        else:
            out = {"id": mid, "error": {"message": "unknown"}}
        sys.stdout.write(json.dumps(out) + "\\n")
        sys.stdout.flush()
    """
)


@pytest.fixture
def fake_server(tmp_path):
    script = tmp_path / "fake_sidecar.py"
    script.write_text(FAKE_SIDECAR, encoding="utf-8")
    return str(script)


def test_forecast_roundtrip(fake_server):
    b = SimBridge(node=sys.executable, server_js=fake_server, timeout=10)
    assert b.available() is True
    out = b.forecast({"playerUid": "100", "targetCellIndex": 1})
    assert out["isWin"] is True
    assert out["lossLv"] == 1
    assert out["lossPercent"] == 5.0
    b.close()


def test_available_false_when_binary_missing():
    b = SimBridge(node="definitely-not-a-real-binary-xyz", server_js="nope.js")
    assert b.available() is False
    with pytest.raises(SimUnavailable):
        b.forecast({})


def test_forecast_raises_when_unavailable():
    b = SimBridge(node="definitely-not-a-real-binary-xyz", server_js="nope.js")
    with pytest.raises(SimUnavailable):
        b.forecast({"playerUid": "1"})


def test_sidecar_pipes_are_utf8(monkeypatch):
    # Node writes raw UTF-8 (army names like "Đội 1" in replay summaries); decoding
    # with the Windows locale (cp1258) killed the reader thread on byte 0x90
    import subprocess

    from nta_agent.execution.predictors import sim_bridge
    seen = {}

    class FakeProc:
        stdout = None
        stdin = None

        def poll(self):
            return None

    def fake_popen(*a, **kw):
        seen.update(kw)
        return FakeProc()
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    b = sim_bridge.SimBridge()
    b._spawn()
    assert seen.get("encoding") == "utf-8"
