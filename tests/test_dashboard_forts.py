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
        "enemy_cells": [[130, 120]], "enemy_cities": [{"x": 130, "y": 120, "type": 1}],
        "frontier": [[99, 120]],
        "recommendations": [{"index": 72100, "x": 100, "y": 120, "reason": "biên giới"}],
        "fort_zone": [[108, 120], [100, 130]], "fort_count": 1, "fort_cap": 3,
        "forts": [[105, 122]],
    }), encoding="utf-8")
    v = read_forts_view(cfg)
    assert v["owned_count"] == 23
    assert v["owned_cells"] == [[100, 120], [101, 120]]
    assert v["recommendations"][0]["index"] == 72100
    assert v["fort_zone"] == [[108, 120], [100, 130]]
    assert v["fort_count"] == 1 and v["fort_cap"] == 3
    assert v["forts"] == [[105, 122]]           # built forts for the map marker
    assert v["accepted"] == [] and v["rejected"] == []  # default empty
    assert v["enemy_cells"] == [[130, 120]] and v["frontier"] == [[99, 120]]
    assert v["enemy_cities"] == [{"x": 130, "y": 120, "type": 1}]


def test_read_forts_view_missing_returns_empty(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    v = read_forts_view(cfg)
    assert v == {"owned_count": 0, "owned_cells": [], "accepted": [], "rejected": [],
                 "enemy_cells": [], "enemy_cities": [], "frontier": [], "recommendations": [],
                 "fort_zone": [], "fort_count": 0, "forts": [], "fort_cap": 0,
                 "threats": [], "threat_summary": {"count": 0}, "pending": []}
