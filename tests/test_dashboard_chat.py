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
