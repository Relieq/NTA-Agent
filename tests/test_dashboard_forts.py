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
                 "threats": [], "threat_summary": {"count": 0}, "pending": [], "building": []}


def test_read_alerts_default_and_file(tmp_path):
    from nta_agent.dashboard.server import read_alerts
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    assert read_alerts(cfg)["level"] == "ok"
    Path(cfg.alerts_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.alerts_path).write_text(json.dumps(
        {"level": "captured", "captured": {"uid": "36781907"}}), encoding="utf-8")
    assert read_alerts(cfg)["captured"]["uid"] == "36781907"


def test_forge_view_and_target_update(tmp_path):
    from nta_agent.dashboard.server import read_forge_view, set_forge_target
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    assert read_forge_view(cfg) == {"equips": [], "busy": None, "iron": 0}
    Path(cfg.forge_view_path).write_text(json.dumps({"equips": [
        {"uid": "6001_1", "quality": 0.5, "target": None}], "busy": None, "iron": 7}),
        encoding="utf-8")
    # set a target (threshold given in %, budget in iron) -> reflected immediately
    r = set_forge_target(cfg, {"uid": "6001_1", "threshold_pct": 80, "budget": 30})
    assert r["ok"] is True
    v = read_forge_view(cfg)
    assert v["equips"][0]["target"] == {"threshold": 0.8, "budget": 30}
    # validation + removal
    assert set_forge_target(cfg, {"uid": "", "threshold_pct": 80, "budget": 1})["ok"] is False
    assert set_forge_target(cfg, {"uid": "6001_1", "threshold_pct": 150, "budget": 1})["ok"] is False
    assert set_forge_target(cfg, {"uid": "6001_1", "remove": True})["ok"] is True
    assert read_forge_view(cfg)["equips"][0]["target"] is None


def test_set_forge_target_per_stat_mins(tmp_path):
    from nta_agent.dashboard.server import read_forge_view, set_forge_target
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    Path(cfg.forge_view_path).write_text(json.dumps({"equips": [{"uid": "6101_1"}]}),
                                         encoding="utf-8")
    r = set_forge_target(cfg, {"uid": "6101_1", "budget": 20,
                               "mins": {"3.value": 170, "3.odds": 35, "7.value": ""}})
    assert r["ok"] is True
    t = read_forge_view(cfg)["equips"][0]["target"]
    assert t["mins"] == {"3.value": 170.0, "3.odds": 35.0} and t["budget"] == 20   # blank dropped
    # malformed stat key / negative / nothing set -> rejected
    assert set_forge_target(cfg, {"uid": "6101_1", "budget": 1, "mins": {"x.y": 1}})["ok"] is False
    assert set_forge_target(cfg, {"uid": "6101_1", "budget": 1, "mins": {"3.value": -1}})["ok"] is False
    assert set_forge_target(cfg, {"uid": "6101_1", "budget": 1, "mins": {}})["ok"] is False


def test_forge_mins_must_lie_within_the_rollable_range(tmp_path):
    """A minimum above the best possible roll can never be met (the agent would burn
    the whole iron budget); below the worst roll it means nothing. Bound both."""
    from nta_agent.dashboard.server import set_forge_target
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    Path(cfg.forge_view_path).write_text(json.dumps({"equips": [
        {"uid": "6005_1", "name": "Đao Bạo Kích", "possible": [
            {"type": 3, "label": "ST Bạo", "suffix": "%",
             "value_range": [150, 180], "odds_range": [20, 40]}]},
        {"uid": "6019_3", "name": "Rìu Chiến Vàng", "possible": [
            {"type": 19, "label": "Khiên", "suffix": "", "value_range": [], "odds_range": [50, 80]}]},
    ]}), encoding="utf-8")
    ok = set_forge_target(cfg, {"uid": "6005_1", "budget": 5,
                                "mins": {"3.value": 180, "3.odds": 20}})
    assert ok["ok"] is True                                         # edges are allowed
    hi = set_forge_target(cfg, {"uid": "6005_1", "budget": 5, "mins": {"3.value": 181}})
    assert hi["ok"] is False and "150" in hi["error"] and "180" in hi["error"]
    lo = set_forge_target(cfg, {"uid": "6005_1", "budget": 5, "mins": {"3.odds": 10}})
    assert lo["ok"] is False and "20" in lo["error"] and "40" in lo["error"]
    none = set_forge_target(cfg, {"uid": "6019_3", "budget": 5, "mins": {"19.value": 5}})
    assert none["ok"] is False                                      # this stat has no value
    assert set_forge_target(cfg, {"uid": "6019_3", "budget": 5, "mins": {"19.odds": 80}})["ok"]


def test_read_forts_view_passes_forts_under_construction(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    Path(cfg.forts_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.forts_path).write_text(json.dumps({
        "building": [{"x": 572, "y": 132, "index": 79772, "id": 2102, "surplus_s": 600,
                      "need_s": 1800}], "scanned_at": 100}), encoding="utf-8")
    v = read_forts_view(cfg)
    assert v["building"][0]["index"] == 79772 and v["scanned_at"] == 100
