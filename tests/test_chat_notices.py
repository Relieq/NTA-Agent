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
