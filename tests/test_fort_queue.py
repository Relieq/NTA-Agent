from nta_agent.runtime import fort_queue


def test_add_load_remove(tmp_path):
    p = tmp_path / "pending_forts.json"
    assert fort_queue.load(p) == []
    fort_queue.add(p, 331273)
    fort_queue.add(p, 322880)
    assert fort_queue.load(p) == [331273, 322880]
    fort_queue.remove(p, 331273)
    assert fort_queue.load(p) == [322880]


def test_add_dedups(tmp_path):
    p = tmp_path / "q.json"
    fort_queue.add(p, 5)
    fort_queue.add(p, 5)
    assert fort_queue.load(p) == [5]


def test_remove_missing_is_noop(tmp_path):
    p = tmp_path / "q.json"
    fort_queue.add(p, 5)
    fort_queue.remove(p, 999)
    assert fort_queue.load(p) == [5]


def test_load_bad_file_returns_empty(tmp_path):
    p = tmp_path / "q.json"
    p.write_text("not json", encoding="utf-8")
    assert fort_queue.load(p) == []
