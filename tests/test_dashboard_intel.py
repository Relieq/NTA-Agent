import json
from pathlib import Path

from nta_agent.dashboard.server import read_intel
from nta_agent.runtime.config import RuntimeConfig


def test_read_intel_from_snapshot_and_forts(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    Path(cfg.snapshot_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.snapshot_path).write_text(json.dumps({
        "main_city_index": 7, "granary_cap": 1000, "warehouse_cap": 1000,
        "resources": {"cereal": 950, "timber": 0, "stone": 0},
        "production": {"cereal": 100}}), encoding="utf-8")
    Path(cfg.forts_path).write_text(json.dumps({
        "threat_summary": {"count": 2, "has_enemy_city": False},
        "threats": [{"x": 1, "y": 2}], "frontier": [[9, 9]],
        "recommendations": [{"x": 5, "y": 6, "reason": "biên giới"}]}), encoding="utf-8")
    r = read_intel(cfg)
    assert r["economy"]["forecasts_hours"]["cereal"] == 0.5
    assert r["threats"]["summary"]["count"] == 2
    assert any(x["type"] == "fort" for x in r["recommendations"])
    assert any(x["type"] == "defense" for x in r["recommendations"])


def test_read_intel_empty_is_safe(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    r = read_intel(cfg)  # no files -> empty but well-formed
    assert r["threats"]["summary"]["count"] == 0
    assert isinstance(r["recommendations"], list)
