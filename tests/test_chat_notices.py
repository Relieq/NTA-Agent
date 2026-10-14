"""What the confirmed jobs did later (queue / dismissals) reaches the chat: until now a failure
only went to events.jsonl and the player saw nothing (live 2026-10-03: a recruit-and-swap died
13 s after the confirmation, silently)."""
import json
from pathlib import Path

from nta_agent.dashboard.server import chat_notices


def _log(tmp_path, rows):
    p = Path(tmp_path) / "events.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    return p


def test_failures_and_completions_become_chat_lines_newer_than_since(tmp_path):
    p = _log(tmp_path, [
        {"ts": 10, "kind": "pawn_move_failed", "detail": {"op": "swap", "reason": "cũ"}},
        {"ts": 100, "kind": "pawn_move_failed",
         "detail": {"op": "recruit_swap", "reason": "đã đạt giới hạn số đội — giải tán bớt một đội"}},
        {"ts": 101, "kind": "pawn_move_progress", "detail": {"op": "recruit_swap", "note": "đã đặt chiêu mộ"}},
        {"ts": 102, "kind": "pawn_move_progress", "detail": {"op": "swap"}},           # no note: skipped
        {"ts": 103, "kind": "pawn_move_done", "detail": {"op": "swap"}},
        {"ts": 104, "kind": "dismiss_done", "detail": {"name": "Nâng Cấp 1", "scope": "pawns", "count": 5}},
        {"ts": 105, "kind": "dismiss_failed", "detail": {"name": "D1", "error": "boom"}},
        {"ts": 106, "kind": "tick", "fired": []},
    ])
    out = chat_notices(p, since=50)
    texts = [i["text"] for i in out["items"]]
    assert len(texts) == 5 and all(i["ts"] > 50 for i in out["items"])
    assert "giới hạn số đội" in texts[0] and texts[0].startswith("⚠️")
    assert "đã đặt chiêu mộ" in texts[1].lower()
    assert texts[2].startswith("✅") and "Nâng Cấp 1" in texts[3] and "5" in texts[3]
    assert "D1" in texts[4] and texts[4].startswith("⚠️")
    assert out["now"] >= 106 or out["now"] > 0


def test_nothing_new_gives_an_empty_list(tmp_path):
    p = _log(tmp_path, [{"ts": 1, "kind": "pawn_move_done", "detail": {"op": "swap"}}])
    assert chat_notices(p, since=5)["items"] == []
    assert chat_notices(Path(tmp_path) / "missing.jsonl", since=0)["items"] == []


def test_the_group_assembly_progress_reaches_the_chat(tmp_path):
    # 2026-10-14: the player asked for 1 + 4 armies, confirmed, and saw NOTHING for hours — the
    # composer was waiting for cereal (events only), so it looked like the command was ignored
    p = _log(tmp_path, [
        {"ts": 100, "kind": "composition_waiting",
         "detail": {"pawn_id": 3305, "need": 322, "have": 105, "eta_min": 128,
                    "text": "chờ lương để chiêu mộ: cần 322, đang có 105 (~128 phút)"}},
        {"ts": 101, "kind": "composition_named", "detail": {"renamed": [], "failed": [{"uid": "u", "name": "Đội 1"}]}},
        {"ts": 102, "kind": "composition_named",
         "detail": {"renamed": [{"uid": "u", "name": "Đội 1"}, {"uid": "v", "name": "Đội 2"}], "failed": []}},
        {"ts": 103, "kind": "composition_blocked", "detail": {"issues": ["Thợ Săn chưa mở khoá"]}},
        {"ts": 104, "kind": "composition_capped", "detail": {"cap": 5, "message": "Thành Chính lv3: tối đa 5 lính/đội"}},
        {"ts": 105, "kind": "composition_done", "detail": {"strike": ["a", "b", "c", "d", "e"]}},
    ])
    texts = [i["text"] for i in chat_notices(p, since=0)["items"]]
    assert len(texts) == 5                                  # the all-failed rename is not worth a line
    assert "chờ lương" in texts[0] and "322" in texts[0] and texts[0].startswith("⏳")
    assert "Đội 1" in texts[1] and "Đội 2" in texts[1] and texts[1].startswith("✅")
    assert "Thợ Săn chưa mở khoá" in texts[2] and texts[2].startswith("⚠️")
    assert "5 lính/đội" in texts[3]
    assert texts[4].startswith("✅") and "5" in texts[4]
