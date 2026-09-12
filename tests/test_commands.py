from nta_agent.runtime.commands import append_command, mark_done, read_pending


def test_append_and_read(tmp_path):
    cmds = tmp_path / "commands.jsonl"
    done = tmp_path / "commands.done"
    cid = append_command(cmds, {"action": "select", "track": "pawn", "lv": 1, "ceri_id": 5})
    assert isinstance(cid, str) and cid
    pend = read_pending(cmds, done)
    assert len(pend) == 1 and pend[0]["id"] == cid and pend[0]["action"] == "select"


def test_done_ids_are_skipped(tmp_path):
    cmds = tmp_path / "commands.jsonl"
    done = tmp_path / "commands.done"
    c1 = append_command(cmds, {"action": "reroll", "track": "policy", "lv": 1})
    c2 = append_command(cmds, {"action": "select", "track": "pawn", "lv": 1, "ceri_id": 6})
    mark_done(done, c1)
    pend = read_pending(cmds, done)
    assert [p["id"] for p in pend] == [c2]


def test_missing_and_malformed(tmp_path):
    assert read_pending(tmp_path / "none.jsonl", tmp_path / "d") == []
    cmds = tmp_path / "commands.jsonl"
    cmds.write_text('not json\n{"id":"a","action":"reroll"}\n')
    assert [p["id"] for p in read_pending(cmds, tmp_path / "d")] == ["a"]
