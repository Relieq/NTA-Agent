import json
from pathlib import Path

from nta_agent.dashboard.server import handle_chat
from nta_agent.runtime.config import RuntimeConfig


def _cfg(tmp_path):
    return RuntimeConfig(distinct_id="x", log_dir=tmp_path)


def test_handle_chat_applies_edit_and_writes_command(tmp_path):
    cfg = _cfg(tmp_path)
    Path(cfg.profile_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.armies_path).write_text(
        json.dumps([{"uid": "A", "name": "D1", "pawns": []}]), encoding="utf-8")

    def fake_propose(digest, profile, instruction=None, history=None):
        return {"occupy": {"max_loss": 6}, "rationale": "safer"}

    out = handle_chat(cfg, "play safer", history=[], propose=fake_propose)
    assert out["ok"] is True and out["applied"]["occupy"]["max_loss"] == 6
    saved = json.loads(Path(cfg.profile_path).read_text(encoding="utf-8"))
    assert saved["occupy"]["max_loss"] == 6
    cmds = Path(cfg.commands_path).read_text(encoding="utf-8").splitlines()
    assert any(json.loads(c)["action"] == "profile_edit" for c in cmds)


def test_handle_chat_no_key_returns_unavailable(tmp_path):
    from nta_agent.brain.llm import BrainUnavailable
    cfg = _cfg(tmp_path)

    def boom(*a, **k):
        raise BrainUnavailable("no key")

    out = handle_chat(cfg, "hi", history=[], propose=boom)
    assert out["ok"] is False and "unavailable" in out["error"].lower()


def _armies(cfg):
    Path(cfg.profile_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.armies_path).write_text(json.dumps([
        {"uid": "A", "name": "cu1", "index": 79542, "pawns": [{"id": 3206}]},
        {"uid": "B", "name": "cu2", "index": 79542, "pawns": [{"id": 3305}]},
    ], ensure_ascii=False), encoding="utf-8")


def test_handle_chat_proposes_renames_without_executing(tmp_path):
    cfg = _cfg(tmp_path)
    _armies(cfg)

    def fake_propose(digest, profile, instruction=None, history=None):
        return {"army_renames": [{"uid": "A", "name": "Đội 1", "pawn": 3206},
                                 {"uid": "B", "name": "Đội 2", "pawn": 3305}]}

    out = handle_chat(cfg, "đổi tên cu1 thành Đội 1 và cu2 thành Đội 2", history=[],
                      propose=fake_propose)
    assert out["ok"] is True and out["needs_confirm"] is True
    # proposal carries current name + readable troops for the confirm UI
    assert {r["uid"] for r in out["renames"]} == {"A", "B"}
    assert out["renames"][0]["current_name"] == "cu1"
    # NOTHING queued yet — waits for confirmation
    assert not Path(cfg.commands_path).exists() or not any(
        json.loads(c).get("action") == "rename_army"
        for c in Path(cfg.commands_path).read_text(encoding="utf-8").splitlines())


def test_confirm_renames_queues_commands(tmp_path):
    from nta_agent.dashboard.server import confirm_renames
    cfg = _cfg(tmp_path)
    _armies(cfg)
    out = confirm_renames(cfg, [{"uid": "A", "name": "Đội 1"}, {"uid": "B", "name": "Đội 2"}])
    assert out["ok"] is True
    cmds = [json.loads(c) for c in
            Path(cfg.commands_path).read_text(encoding="utf-8").splitlines()]
    rn = [c for c in cmds if c["action"] == "rename_army"]
    assert {c["uid"] for c in rn} == {"A", "B"}
    assert all(c["index"] == 79542 for c in rn)


def test_confirm_renames_drops_unknown_uid(tmp_path):
    from nta_agent.dashboard.server import confirm_renames
    cfg = _cfg(tmp_path)
    _armies(cfg)
    out = confirm_renames(cfg, [{"uid": "ghost", "name": "X"}])
    assert out["queued"] == []


def test_handle_chat_returns_question_without_acting(tmp_path):
    cfg = _cfg(tmp_path)
    Path(cfg.profile_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.armies_path).write_text(json.dumps(
        [{"uid": "A", "name": "x", "index": 1, "pawns": []}]), encoding="utf-8")

    def fake_propose(digest, profile, instruction=None, history=None):
        return {"question": "Đội nào là Đội 1?"}

    out = handle_chat(cfg, "đổi tên nhóm", history=[], propose=fake_propose)
    assert out["ok"] is True and out["question"] == "Đội nào là Đội 1?"
    assert out.get("renames") == []
    # no rename command queued
    cmds = Path(cfg.commands_path)
    if cmds.exists():
        assert not any(json.loads(c).get("action") == "rename_army"
                       for c in cmds.read_text(encoding="utf-8").splitlines())


def test_handle_chat_guard_turns_ambiguous_rename_into_question(tmp_path):
    """The LLM picked ONE crossbow army for 'đội cường nỏ' but two exist -> the
    deterministic guard drops the proposal and asks, listing both candidates."""
    cfg = _cfg(tmp_path)
    Path(cfg.profile_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.armies_path).write_text(json.dumps([
        {"uid": "A", "name": "Team 2", "index": 1, "pawns": [{"id": 3305}] * 9},
        {"uid": "B", "name": "Team 3", "index": 1, "pawns": [{"id": 3305}] * 9},
    ], ensure_ascii=False), encoding="utf-8")

    def fake_propose(digest, profile, instruction=None, history=None):
        return {"army_renames": [{"uid": "A", "name": "IMP", "pawn": 3305}]}

    out = handle_chat(cfg, "đổi tên đội cường nỏ thành IMP", history=[], propose=fake_propose)
    assert out["ok"] is True and out["renames"] == [] and out["needs_confirm"] is False
    assert "Team 2" in out["question"] and "Team 3" in out["question"]


def _live_setup(tmp_path):
    cfg = _cfg(tmp_path)
    Path(cfg.profile_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.snapshot_path).write_text(
        json.dumps({"player": {"pawn_slots": [3304, 3202, 3305, 3201]}}), encoding="utf-8")
    p = lambda i: {"id": i}
    Path(cfg.armies_path).write_text(json.dumps([
        {"uid": "A", "name": "D2", "index": 1, "pawns": [p(3305)] * 8 + [p(3201)]},
        {"uid": "B", "name": "D1", "index": 1, "pawns": [p(3305)] * 7 + [p(3201)] * 2},
    ]), encoding="utf-8")
    return cfg


def test_live_strike_request_is_proposed_not_applied(tmp_path):
    """2026-09-25: 'Tạo nhóm 5 đội gồm 1 đội khiên lớn và 4 đội IMP, đặt tên Đội 1..5'
    -> the LLM chose the LOCKED 3206 with size 1 and it was applied at once."""
    cfg = _live_setup(tmp_path)
    seen = {}

    def fake_propose(digest, profile, instruction=None, history=None):
        seen["unlocked"] = digest.get("unlocked_pawns")
        return {"army": {"strike_target": [{"pawn_id": 3305, "armies": 4, "size": 1},
                                           {"pawn_id": 3206, "armies": 1, "size": 1}]},
                "army_renames": [{"uid": "A", "name": "Đội 2", "pawn": 3305}]}

    msg = ("Tạo giúp tôi nhóm 5 đội gồm 1 đội khiên lớn và 4 đội IMP, "
           "đặt tên lần lượt là Đội 1 đến Đội 5")
    out = handle_chat(cfg, msg, history=[], propose=fake_propose)
    assert {"id": 3202, "name": "Lính Khiên Lớn"} in seen["unlocked"] or \
        any(u["id"] == 3202 for u in seen["unlocked"])
    assert out["ok"] and out["needs_confirm"] and out["renames"] == []
    assert out["question"] == ""
    assert [(t["pawn_id"], t["armies"], t["size"]) for t in out["strike"]["targets"]] == \
        [(3305, 4, 9)]
    assert any("3206" in n and "chưa mở khoá" in n for n in out["notices"])
    saved = json.loads(Path(cfg.profile_path).read_text(encoding="utf-8")) \
        if Path(cfg.profile_path).exists() else {}
    assert not (saved.get("army") or {}).get("strike_target")      # nothing applied yet


def test_confirmed_strike_is_saved_and_sent_to_the_agent(tmp_path):
    from nta_agent.dashboard.server import confirm_strike
    cfg = _live_setup(tmp_path)
    out = confirm_strike(cfg, [{"pawn_id": 3202, "armies": 1, "size": 9, "names": ["Đội 1"]},
                               {"pawn_id": 3305, "armies": 4, "size": 9,
                                "names": ["Đội 2", "Đội 3", "Đội 4", "Đội 5"]}])
    assert out["ok"] and "Đội 1" in out["summary"]
    saved = json.loads(Path(cfg.profile_path).read_text(encoding="utf-8"))
    st = saved["army"]["strike_target"]
    assert [t["pawn_id"] for t in st] == [3202, 3305] and st[1]["names"][-1] == "Đội 5"
    cmd = json.loads(Path(cfg.commands_path).read_text(encoding="utf-8").splitlines()[-1])
    assert cmd["action"] == "profile_edit" and cmd["edits"]["army"]["strike_target"] == st


def test_applied_edits_are_described_in_words(tmp_path):
    from nta_agent.dashboard.server import describe_edits
    lines = describe_edits({"occupy": {"expansion": "spiral", "loot": {"enabled": False}},
                            "revive": {"enabled": True}, "army": {"strike_target": []}})
    assert "Kiểu mở rộng đất → spiral" in lines and "Ưu tiên nhặt rương → tắt" in lines
    assert "Tự hồi sinh lính → bật" in lines and "Huỷ mục tiêu gom quân" in lines
