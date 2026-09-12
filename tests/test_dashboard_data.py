import json

from nta_agent.dashboard.data import read_state, tail_events


def test_read_state_ok(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"main_city_index": 5, "resources": {"cereal": 9}}))
    d = read_state(p)
    assert d["ok"] is True and d["main_city_index"] == 5 and d["resources"]["cereal"] == 9


def test_read_state_missing(tmp_path):
    assert read_state(tmp_path / "nope.json") == {"ok": False}


def test_read_state_corrupt(tmp_path):
    p = tmp_path / "state.json"
    p.write_text('{"half wri')
    assert read_state(p) == {"ok": False}


def test_tail_events(tmp_path):
    p = tmp_path / "events.jsonl"
    p.write_text("\n".join(json.dumps({"i": i}) for i in range(5)) + "\n")
    rows = tail_events(p, 2)
    assert [r["i"] for r in rows] == [3, 4]


def test_tail_events_skips_corrupt_and_missing(tmp_path):
    p = tmp_path / "events.jsonl"
    p.write_text('{"i":1}\nnot json\n\n{"i":2}\n')
    assert [r["i"] for r in tail_events(p, 50)] == [1, 2]
    assert tail_events(tmp_path / "none.jsonl") == []
