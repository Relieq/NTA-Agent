"""Dashboard dig API: request/confirm/cancel go to dig_request.json; GET reads dig.json."""
import json

from nta_agent.dashboard.server import dig_command, read_dig
from nta_agent.runtime.config import RuntimeConfig


def _cfg(tmp_path):
    return RuntimeConfig(distinct_id="x", log_dir=tmp_path)


def test_read_dig_defaults_to_idle(tmp_path):
    v = read_dig(_cfg(tmp_path))
    assert v["state"] == "idle" and v["pending"] is False


def test_request_writes_a_new_seq_and_shows_pending_until_the_agent_answers(tmp_path):
    cfg = _cfg(tmp_path)
    r = dig_command(cfg, "request", {"index": 6016, "buffer": 3})
    assert r["ok"] is True
    req = json.loads(cfg.dig_request_path.read_text(encoding="utf-8"))
    assert req["op"] == "request" and req["index"] == 6016 and req["buffer"] == 3
    v = read_dig(cfg)
    assert v["pending"] is True and v["pending_op"] == "request"
    # the agent picks it up and answers with the same seq
    cfg.dig_state_path.write_text(json.dumps({"seq": req["seq"], "state": "preview",
                                              "path": [[12, 10]]}), encoding="utf-8")
    v = read_dig(cfg)
    assert v["pending"] is False and v["state"] == "preview" and v["path"] == [[12, 10]]


def test_request_validates_index_and_clamps_buffer(tmp_path):
    cfg = _cfg(tmp_path)
    assert dig_command(cfg, "request", {})["ok"] is False
    assert dig_command(cfg, "request", {"index": 600 * 600})["ok"] is False
    dig_command(cfg, "request", {"index": 5, "buffer": 99})
    assert json.loads(cfg.dig_request_path.read_text(encoding="utf-8"))["buffer"] == 6
    assert dig_command(cfg, "bogus", {})["ok"] is False


def test_confirm_and_cancel_are_plain_ops(tmp_path):
    cfg = _cfg(tmp_path)
    for op in ("confirm", "cancel"):
        assert dig_command(cfg, op, {})["ok"] is True
        assert json.loads(cfg.dig_request_path.read_text(encoding="utf-8"))["op"] == op


def test_cancel_shows_at_once_and_replan_is_an_op(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.dig_state_path.write_text(json.dumps({"seq": 1, "state": "active"}), encoding="utf-8")
    dig_command(cfg, "cancel", {})
    v = read_dig(cfg)
    assert v["state"] == "cancelled" and v["cancel_pending"] is True
    assert dig_command(cfg, "replan", {})["ok"] is True
    assert json.loads(cfg.dig_request_path.read_text(encoding="utf-8"))["op"] == "replan"
