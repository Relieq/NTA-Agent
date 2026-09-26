"""Smelting tab: read view, server-side preview, validated smelt/restore commands."""
from __future__ import annotations

import json
from pathlib import Path

from nta_agent.runtime.commands import read_pending
from nta_agent.runtime.config import RuntimeConfig


def _cfg(tmp_path, **over):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    view = {"smithy_lv": 14, "need_lv": [14, 20], "slots": 1, "fixator": 3,
            "smelting": None, "forging": None,
            "mains": [{"uid": "6101_10", "id": 6101, "name": "M", "pawn_name": "P",
                       "effects": [{"type": 21, "value": 5, "odds": 0, "text": "e21",
                                    "smelted": False, "from": 0}],
                       "smelted_from": [], "pool": [21, 8],
                       "candidates": [{"uid": "6005_1", "id": 6005, "name": "V",
                                       "in_pool": True,
                                       "effects": [{"type": 8, "value": 40, "odds": 0,
                                                    "text": "e8"}]}]}],
            "raw": {"6101_10": {"uid": "6101_10", "attrs": [{"attr": [2, 21, 5, 0]}]},
                    "6005_1": {"uid": "6005_1", "attrs": [{"attr": [0, 1, 41]},
                                                          {"attr": [2, 8, 40, 0]}]}}}
    view.update(over)
    Path(cfg.smelt_view_path).write_text(json.dumps(view), encoding="utf-8")
    Path(cfg.world_random_path).write_text(json.dumps({"exclusive": {"6101": [21, 8]}}),
                                           encoding="utf-8")
    return cfg


def test_read_smelt_view_hides_raw(tmp_path):
    from nta_agent.dashboard.server import read_smelt_view
    v = read_smelt_view(_cfg(tmp_path))
    assert "raw" not in v and v["mains"][0]["uid"] == "6101_10" and v["slots"] == 1


def test_preview_uses_the_match_pool_and_vice_texts(tmp_path):
    from nta_agent.dashboard.server import smelt_preview_for
    r = smelt_preview_for(_cfg(tmp_path), {"main_uid": "6101_10", "vice_ids": [6005]})
    assert r["ok"] is True
    assert r["fixator_cost"] == 1 and r["fixator_per_recast"] == 1   # 8 is in the pool
    assert r["added"][0]["text"] == "e8" and r["stats"]["hp"] == 21


def test_smelt_command_is_validated_then_queued(tmp_path):
    from nta_agent.dashboard.server import queue_smelt
    cfg = _cfg(tmp_path)
    assert queue_smelt(cfg, {"action": "smelt", "main_uid": "6101_10",
                             "vice_ids": [6005, 6006]})["ok"] is False      # 2 > 1 slot
    assert queue_smelt(cfg, {"action": "smelt", "main_uid": "6101_10",
                             "vice_ids": [9999]})["ok"] is False            # not a candidate
    assert queue_smelt(cfg, {"action": "restore_smelt",
                             "main_uid": "6101_10"})["ok"] is False         # nothing smelted
    r = queue_smelt(cfg, {"action": "smelt", "main_uid": "6101_10", "vice_ids": [6005]})
    assert r["ok"] is True
    (cmd,) = read_pending(cfg.commands_path, cfg.commands_done_path)
    assert cmd["action"] == "smelt" and cmd["main_uid"] == "6101_10" and cmd["vice_ids"] == [6005]


def test_smelt_refused_while_busy_or_short_of_fixators(tmp_path):
    from nta_agent.dashboard.server import queue_smelt
    body = {"action": "smelt", "main_uid": "6101_10", "vice_ids": [6005]}
    assert queue_smelt(_cfg(tmp_path, smelting={"uid": "x"}), body)["ok"] is False
    assert queue_smelt(_cfg(tmp_path, forging={"uid": "x"}), body)["ok"] is False
    assert queue_smelt(_cfg(tmp_path, fixator=0), body)["ok"] is False


def test_decision_service_runs_smelt_and_restore():
    from nta_agent.runtime.decision_service import DecisionService

    class A:
        def __init__(self):
            self.calls = []

        def smelting_equip(self, m, v):
            self.calls.append(("smelt", m, v))

        def restore_smelt_equip(self, m):
            self.calls.append(("restore", m))
    a = A()
    svc = DecisionService.__new__(DecisionService)
    svc.actions, svc.profile = a, None
    svc._execute({"action": "smelt", "main_uid": "6101_10", "vice_ids": [6005]})
    svc._execute({"action": "restore_smelt", "main_uid": "6101_10"})
    assert a.calls == [("smelt", "6101_10", [6005]), ("restore", "6101_10")]
