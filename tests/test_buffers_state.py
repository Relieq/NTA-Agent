"""buffers.json state + leveling groups in the profile (+ guard)."""
from __future__ import annotations

import json
from types import SimpleNamespace

from nta_agent.brain.guard import sanitize_edits
from nta_agent.execution.profile import leveling_groups, load_profile
from nta_agent.runtime import buffers


def test_missing_file_gives_defaults(tmp_path):
    d = buffers.load(tmp_path / "buffers.json")
    assert d == {"proposal": None, "approved": False, "setup_done": False, "buffers": {}}


def test_round_trip_and_approve(tmp_path):
    p = tmp_path / "buffers.json"
    buffers.save(p, {"proposal": {"buffers": []}, "approved": False, "setup_done": False,
                     "buffers": {"B1": {"name": "Nâng Cấp 1", "phase": "leveling"}}})
    assert json.loads(p.read_text(encoding="utf-8"))["buffers"]["B1"]["phase"] == "leveling"
    buffers.approve(p)
    assert buffers.load(p)["approved"] is True
    assert not (tmp_path / "buffers.json.tmp").exists()      # atomic replace


def test_new_proposal_resets_approval(tmp_path):
    p = tmp_path / "buffers.json"
    buffers.approve(p)
    buffers.set_proposal(p, {"buffers": [{"name": "Nâng Cấp 1"}]})
    d = buffers.load(p)
    assert d["approved"] is False and d["proposal"]["buffers"][0]["name"] == "Nâng Cấp 1"


def test_legacy_profile_is_one_direct_group(tmp_path):
    prof = load_profile(tmp_path / "none.json")
    assert prof.leveling["groups"] == []
    prof.leveling.update(target_lv=3)
    prof.army.update(group=["A", "B"])
    assert leveling_groups(prof) == [{"armies": ["A", "B"], "mode": "direct", "target_lv": 3}]
    prof.leveling["groups"] = [{"armies": ["X"], "mode": "buffer", "target_lv": 4}]
    assert leveling_groups(prof) == [{"armies": ["X"], "mode": "buffer", "target_lv": 4}]


def test_guard_sanitizes_groups():
    prof = SimpleNamespace(army={"group": []}, occupy={}, leveling={})
    out = sanitize_edits({"leveling": {"groups": [
        {"armies": ["A", "nope"], "mode": "buffer", "target_lv": "3"},
        {"armies": ["B"], "mode": "weird", "target_lv": 2},
        {"armies": [], "mode": "direct"}]}}, prof, {"A", "B"})
    assert out["leveling"]["groups"] == [
        {"armies": ["A"], "mode": "buffer", "target_lv": 3},
        {"armies": ["B"], "mode": "direct", "target_lv": 2}]
