import json
from pathlib import Path

from nta_agent.dashboard.server import recompute_forts
from nta_agent.runtime import fort_decisions as fd
from nta_agent.runtime.config import RuntimeConfig


def _setup(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    Path(cfg.snapshot_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.snapshot_path).write_text(json.dumps({
        "ok": True, "main_city_index": 100 * 600 + 100, "map_width": 600,
        "forts": [], "garrisons": []}), encoding="utf-8")
    Path(cfg.forts_path).write_text(json.dumps({
        "owned_count": 2, "owned_cells": [[120, 100], [100, 120]],
        "accepted": [], "rejected": [], "enemy_cells": [[99, 99]],
        "recommendations": []}), encoding="utf-8")
    return cfg


def test_recompute_carries_over_enemy_layer(tmp_path):
    cfg = _setup(tmp_path)
    out = recompute_forts(cfg)
    assert out["enemy_cells"] == [[99, 99]]  # map layer preserved across recompute


def test_recompute_reflects_reject(tmp_path):
    cfg = _setup(tmp_path)
    fd.update(cfg.fort_decisions_path, 100 * 600 + 120, "reject")  # (x=120,y=100)
    out = recompute_forts(cfg)
    assert [120, 100] not in [[r["x"], r["y"]] for r in out["recommendations"]]
    assert [120, 100] in out["rejected"]


def test_recompute_reflects_accept(tmp_path):
    cfg = _setup(tmp_path)
    fd.update(cfg.fort_decisions_path, 100 * 600 + 120, "accept")  # (x=120,y=100)
    out = recompute_forts(cfg)
    assert [120, 100] in out["accepted"]
    assert [120, 100] not in [[r["x"], r["y"]] for r in out["recommendations"]]
