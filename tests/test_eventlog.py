import json

from nta_agent.runtime.eventlog import EventLog
from nta_agent.state.schema import GameState


def _lines(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_append_writes_jsonl(tmp_path):
    p = tmp_path / "d" / "events.jsonl"
    log = EventLog(p)
    log.append("recovered")
    log.append("recover_retry", "boom")
    rows = _lines(p)
    assert rows[0]["kind"] == "recovered" and "detail" not in rows[0]
    assert rows[1] == {"ts": rows[1]["ts"], "kind": "recover_retry", "detail": "boom"}


def test_append_coerces_non_serializable(tmp_path):
    p = tmp_path / "events.jsonl"
    EventLog(p).append("connection_lost", ValueError("x"))
    assert _lines(p)[0]["detail"] == "x"


def test_tick_summary(tmp_path):
    p = tmp_path / "events.jsonl"
    st = GameState(); st.resources.cereal = 12
    EventLog(p).tick(3, ["collect_city_output"], st)
    row = _lines(p)[0]
    assert row["kind"] == "tick" and row["i"] == 3
    assert row["fired"] == ["collect_city_output"] and row["cereal"] == 12
