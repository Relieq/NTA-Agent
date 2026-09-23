from nta_agent.brain.guard import sanitize_renames

VALID = {"a1", "a2", "a3"}


def test_keeps_valid_renames():
    out = sanitize_renames({"army_renames": [{"uid": "a1", "name": "Đội 1"},
                                             {"uid": "a2", "name": "Đội 2"}]}, VALID)
    assert out == [{"uid": "a1", "name": "Đội 1"}, {"uid": "a2", "name": "Đội 2"}]


def test_drops_unknown_uid():
    out = sanitize_renames({"army_renames": [{"uid": "ghost", "name": "X"},
                                             {"uid": "a1", "name": "OK"}]}, VALID)
    assert out == [{"uid": "a1", "name": "OK"}]


def test_drops_bad_names():
    out = sanitize_renames({"army_renames": [
        {"uid": "a1", "name": "x" * 13},   # too long
        {"uid": "a2", "name": "  "},       # empty
        {"uid": "a3", "name": "a\nb"},     # newline
    ]}, VALID)
    assert out == []


def test_non_list_returns_empty():
    assert sanitize_renames({}, VALID) == []
    assert sanitize_renames({"army_renames": "nope"}, VALID) == []


def test_trims_name_and_dedups_uid_last_wins():
    out = sanitize_renames({"army_renames": [{"uid": "a1", "name": " D1 "},
                                             {"uid": "a1", "name": "D1b"}]}, VALID)
    assert out == [{"uid": "a1", "name": "D1b"}]   # last wins, trimmed
