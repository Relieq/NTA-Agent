import json
from types import SimpleNamespace

from nta_agent.execution.heuristics import RuleEngine
from nta_agent.runtime.errorlog import ErrorLog


class _Cfg:
    def table(self, name):
        return {"500019": {"vi": "Lính đội quân đã đầy"}}


def _rows(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_logs_exception_with_ecode_reason_and_traceback(tmp_path):
    el = ErrorLog(tmp_path / "errors.jsonl", _Cfg())
    try:
        raise RuntimeError("game/HD_OccupyCell: ecode.500019")
    except RuntimeError as e:
        el.rule_error("occupy_cell", e, context={"tick": 5})
    row = _rows(tmp_path / "errors.jsonl")[0]
    assert row["source"] == "occupy_cell" and row["kind"] == "rule_error"
    assert row["ecode"] == "500019" and row["reason"] == "Lính đội quân đã đầy"
    assert "traceback" in row and row["context"] == {"tick": 5}


def test_log_plain_string_no_traceback(tmp_path):
    el = ErrorLog(tmp_path / "e.jsonl")
    el.log("agent", "connection_lost", "socket reset")
    row = _rows(tmp_path / "e.jsonl")[0]
    assert row["kind"] == "connection_lost" and "traceback" not in row and "ecode" not in row


def test_summary_aggregates(tmp_path):
    el = ErrorLog(tmp_path / "e.jsonl", _Cfg())
    el.log("occupy_cell", "rule_error", "ecode.500019")
    el.log("occupy_cell", "rule_error", "ecode.500019")
    el.log("build_order", "rule_error", "boom")
    s = el.summary()
    assert s["total"] == 3
    assert s["by_source"]["occupy_cell"] == 2
    assert s["by_ecode"]["500019:Lính đội quân đã đầy"] == 2


def test_summary_missing_file_is_empty(tmp_path):
    assert ErrorLog(tmp_path / "none.jsonl").summary()["total"] == 0


def test_rule_engine_calls_on_error_on_failure():
    errors = []

    class BadRule:
        name = "bad"
        def applies(self, state, actions):
            raise RuntimeError("kaboom")
        def act(self, actions):
            pass

    eng = RuleEngine(rules=[BadRule()], on_error=lambda src, exc: errors.append((src, str(exc))))
    fired = eng.tick(SimpleNamespace(), SimpleNamespace())
    assert any(f.startswith("bad!ERR") for f in fired)
    assert errors and errors[0][0] == "bad"
