import json
from pathlib import Path

from nta_agent.dashboard.server import read_territory_view
from nta_agent.runtime.config import RuntimeConfig


def test_read_territory_view_from_snapshot(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    Path(cfg.snapshot_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.snapshot_path).write_text(json.dumps({
        "ok": True, "main_city_index": 60100, "map_width": 600,
        "forts": [{"index": 60110, "auto_support": True}], "garrisons": [60100]}),
        encoding="utf-8")
    v = read_territory_view(cfg)
    assert v["main_city"] == 60100
    assert v["forts"][0]["index"] == 60110 and v["forts"][0]["auto_support"] is True
    assert v["forts"][0]["x"] == 60110 % 600 and v["forts"][0]["y"] == 60110 // 600
    assert v["garrisons"] == [60100]
