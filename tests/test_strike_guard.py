"""Chat strike_target: only unlocked pawn types, full armies unless the player gives a
soldier count, names attached to the group (live 2026-09-25: 'khiên lớn' became the
locked 3206 with size 1)."""
from nta_agent.brain.guard import sanitize_strike

NAMES = {3202: "Lính Khiên Lớn", 3305: "Lính Cường Nỏ", 3206: "Lính Rìu Khiên"}
UNLOCKED = {3304, 3202, 3305, 3201}
ASK = "Tạo giúp tôi nhóm 5 đội gồm 1 đội khiên lớn và 4 đội IMP, đặt tên lần lượt là Đội 1 đến Đội 5"


def test_locked_pawn_is_dropped_with_a_note():
    st, notes = sanitize_strike([{"pawn_id": 3206, "armies": 1, "size": 9},
                                 {"pawn_id": 3305, "armies": 4, "size": 9}],
                                UNLOCKED, ASK, NAMES)
    assert [t["pawn_id"] for t in st] == [3305]
    assert any("Lính Rìu Khiên" in n and "chưa mở khoá" in n for n in notes)


def test_size_defaults_to_full_army_unless_a_count_is_given():
    st, _ = sanitize_strike([{"pawn_id": 3305, "armies": 4, "size": 1}], UNLOCKED, ASK, NAMES)
    assert st[0]["size"] == 9
    st, _ = sanitize_strike([{"pawn_id": 3305, "armies": 4, "size": 5}], UNLOCKED,
                            "tạo 4 đội IMP mỗi đội 5 lính", NAMES)
    assert st[0]["size"] == 5


def test_names_are_kept_trimmed_and_capped_to_the_army_count():
    st, _ = sanitize_strike(
        [{"pawn_id": 3202, "armies": 1, "size": 9, "names": ["Đội 1"]},
         {"pawn_id": 3305, "armies": 4, "size": 9,
          "names": ["Đội 2", " Đội 3 ", "Đội 4", "Đội 5", "Đội 6"]}],
        UNLOCKED, ASK, NAMES)
    assert st[0]["names"] == ["Đội 1"]
    assert st[1]["names"] == ["Đội 2", "Đội 3", "Đội 4", "Đội 5"]
    assert st[1]["name"] == "Lính Cường Nỏ"   # readable label for the confirm card


def test_unknown_unlocks_keep_everything():
    st, notes = sanitize_strike([{"pawn_id": 3206, "armies": 1, "size": 9}], None, ASK, NAMES)
    assert [t["pawn_id"] for t in st] == [3206] and notes == []
