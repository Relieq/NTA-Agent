from nta_agent.runtime import fort_decisions as fd


def test_load_missing_is_empty(tmp_path):
    assert fd.load(tmp_path / "none.json") == {}


def test_update_accept_reject_clear(tmp_path):
    p = tmp_path / "d.json"
    assert fd.update(p, 5, "accept") == {5: "accepted"}
    assert fd.update(p, 6, "reject") == {5: "accepted", 6: "rejected"}
    assert fd.update(p, 5, "clear") == {6: "rejected"}
    assert fd.load(p) == {6: "rejected"}
