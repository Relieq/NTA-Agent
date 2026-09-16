import json
from pathlib import Path

from nta_agent.dashboard.server import read_forts_view
from nta_agent.runtime.config import RuntimeConfig


def test_read_forts_view_from_file(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    Path(cfg.forts_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.forts_path).write_text(json.dumps({
        "owned_count": 23,
        "owned_cells": [[100, 120], [101, 120]],
        "recommendations": [{"index": 72100, "x": 100, "y": 120, "reason": "biên giới"}],
    }), encoding="utf-8")
    v = read_forts_view(cfg)
    assert v["owned_count"] == 23
    assert v["owned_cells"] == [[100, 120], [101, 120]]
    assert v["recommendations"][0]["index"] == 72100


def test_read_forts_view_missing_returns_empty(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    v = read_forts_view(cfg)
    assert v == {"owned_count": 0, "owned_cells": [], "recommendations": []}
