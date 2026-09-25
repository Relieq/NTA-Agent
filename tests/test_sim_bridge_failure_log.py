"""SimBridge records every failed call with its input (sim_errors.jsonl)."""
import json
import shutil

import pytest

from nta_agent.execution.predictors.sim_bridge import SimBridge, SimUnavailable

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

FAKE = r"""
const rl = require("readline").createInterface({ input: process.stdin });
rl.on("line", (l) => {
  const m = JSON.parse(l);
  if (m.method === "hang") return;                       // never answers -> timeout
  process.stdout.write(JSON.stringify({ id: m.id, error: {
    message: "Cannot read properties of undefined (reading 'map')",
    stack: ["at enemyArmysFor (area-factory.js:122:10)", "at forecast (forecast.js:50:3)"] } }) + "\n");
});
"""


def _bridge(tmp_path, timeout=5.0):
    js = tmp_path / "fake.js"
    js.write_text(FAKE, encoding="utf-8")
    return SimBridge(server_js=js, timeout=timeout, failure_log=tmp_path / "sim_errors.jsonl")


def _rows(tmp_path):
    return [json.loads(x) for x in (tmp_path / "sim_errors.jsonl").read_text(
        encoding="utf-8").splitlines()]


def test_error_is_logged_with_stack_and_input(tmp_path):
    b = _bridge(tmp_path)
    inp = {"targetCellIndex": 73165, "armies": [{"uid": "a"}], "enemyArmyConf": None}
    with pytest.raises(SimUnavailable, match="reading 'map'"):
        b.forecast(inp)
    b.close()
    row = _rows(tmp_path)[0]
    assert row["method"] == "forecast" and row["params"] == inp
    assert row["stack"][0].startswith("at enemyArmysFor")


def test_timeout_is_logged(tmp_path):
    b = _bridge(tmp_path, timeout=0.5)
    with pytest.raises(SimUnavailable, match="timed out"):
        b._send("hang", {"x": 1})
    row = _rows(tmp_path)[0]
    assert row["error"] == "sidecar timed out" and row["elapsed_s"] >= 0.5


def test_records_are_summarised_not_dumped(tmp_path):
    b = _bridge(tmp_path)
    with pytest.raises(SimUnavailable):
        b.counterfactual({"uid": "r1", "index": 5, "frames": [1] * 1000}, ["auto"])
    b.close()
    assert _rows(tmp_path)[0]["params"] == {"record_uid": "r1", "index": 5, "orders": ["auto"]}
