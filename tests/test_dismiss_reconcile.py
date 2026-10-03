"""Chat dismissals are checked against the player's own sentence (live 2026-10-03: 'Loại tất
cả lính đao khiên trong đội "Nâng cấp 1"' came back as 6 Đao Khiên of "Nâng Cấp 2")."""
from nta_agent.brain.guard import reconcile_dismissals, sanitize_dismissals


def _army(uid, name, ids):
    return {"uid": uid, "name": name, "index": 1,
            "pawns": [{"uid": f"{uid}{i}", "id": p, "lv": 1 + i} for i, p in enumerate(ids)]}


ARMIES = [_army("N1", "Nâng Cấp 1", [3201] * 4 + [3305] * 2),
          _army("N2", "Nâng Cấp 2", [3201] * 9),
          _army("T1", "Đội 1", [3201] * 9)]
MSG = 'Loại tất cả lính đao khiên trong đội "Nâng cấp 1"'
WRONG = [{"uid": "N2", "scope": "pawns", "pawn_id": 3201, "count": 6}]


def test_wrong_army_is_redirected_to_the_one_the_player_named():
    raw, notes = reconcile_dismissals(WRONG, MSG, ARMIES)
    clean, _ = sanitize_dismissals(raw, ARMIES)
    assert [(d["uid"], d["count"], d["pawn_id"]) for d in clean] == [("N1", 4, 3201)]
    assert any("Nâng Cấp 1" in n for n in notes)


def test_all_means_every_pawn_of_that_type_even_when_the_count_was_short():
    raw, _ = reconcile_dismissals([{"uid": "N1", "scope": "pawns", "pawn_id": 3201, "count": 2}],
                                  MSG, ARMIES)
    clean, _ = sanitize_dismissals(raw, ARMIES)
    assert clean[0]["count"] == 4


def test_a_given_count_is_kept_when_the_player_did_not_say_all():
    raw, _ = reconcile_dismissals([{"uid": "N2", "scope": "pawns", "pawn_id": 3201, "count": 2}],
                                  'giải tán 2 lính đao khiên của "Nâng cấp 1"', ARMIES)
    clean, _ = sanitize_dismissals(raw, ARMIES)
    assert [(d["uid"], d["count"]) for d in clean] == [("N1", 2)]


def test_a_whole_army_dismissal_of_the_wrong_army_is_dropped_not_redirected():
    raw, notes = reconcile_dismissals([{"uid": "N2", "scope": "army"}],
                                      'giải tán đội "Nâng cấp 1"', ARMIES)
    assert raw == [] and notes


def test_untouched_when_no_single_army_is_named():
    raw, notes = reconcile_dismissals(WRONG, "giải tán 6 lính đao khiên", ARMIES)
    assert raw == WRONG and notes == []
    both = 'đổi lính giữa "Nâng cấp 1" và "Nâng cấp 2"'
    assert reconcile_dismissals(WRONG, both, ARMIES)[0] == WRONG
