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
    # the LLM used the locked 3206 for 'khiên lớn'; the sentence says 3202 (unlocked)
    assert [t["pawn_id"] for t in st] == [3202, 3305]
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
    st, notes = sanitize_strike([{"pawn_id": 3206, "armies": 1, "size": 9}], None,
                                "tạo giúp tôi một nhóm quân", NAMES)
    assert [t["pawn_id"] for t in st] == [3206] and notes == []


# --- live 2026-10-03: gpt-4o-mini swapped the counts ("1 đội đao khiên và 4 đội imp" ->
# 4 × Đao Khiên + 1 × Cường Nỏ) and mangled the names ("Đội Đao Khiê"); the same wrong
# answer came back twice. The player's own sentence is the source of truth.
N2 = {3201: "Lính Đao Khiên", 3305: "Lính Cường Nỏ"}
U2 = {3201, 3305}
AL = {3305: ["IMP"]}
ASK2 = ("Tạo 1 đội lính đao khiên và 4 đội lính imp có tên lần lượt từ \"Đội 1\" "
        "đến \"Đội 5\"")
WRONG = [{"pawn_id": 3201, "armies": 4, "size": 9,
          "names": ["Đội 1", "Đội 2", "Đội 3", "Đội 4"]},
         {"pawn_id": 3305, "armies": 1, "size": 9, "names": ["Đội Đao Khiên"]}]


def test_counts_follow_the_players_sentence_not_the_llm():
    st, notes = sanitize_strike(WRONG, U2, ASK2, N2, aliases=AL)
    assert [(t["pawn_id"], t["armies"]) for t in st] == [(3201, 1), (3305, 4)]
    assert any("1 đội Lính Đao Khiên" in n and "4 đội Lính Cường Nỏ" in n for n in notes)


def test_names_come_from_the_players_range_in_entry_order():
    st, _ = sanitize_strike(WRONG, U2, ASK2, N2, aliases=AL)
    assert st[0]["names"] == ["Đội 1"]
    assert st[1]["names"] == ["Đội 2", "Đội 3", "Đội 4", "Đội 5"]


def test_short_range_syntax_and_number_words():
    st, _ = sanitize_strike(WRONG, U2, "tạo một đội đao khiên và bốn đội IMP, đặt tên Đội 1...5",
                            N2, aliases=AL)
    assert [(t["pawn_id"], t["armies"]) for t in st] == [(3201, 1), (3305, 4)]
    assert st[1]["names"] == ["Đội 2", "Đội 3", "Đội 4", "Đội 5"]


def test_entry_order_follows_the_sentence_and_missing_entry_is_added():
    st, _ = sanitize_strike([{"pawn_id": 3305, "armies": 4, "size": 9}], U2,
                            "tạo 1 đội đao khiên và 4 đội IMP", N2, aliases=AL)
    assert [(t["pawn_id"], t["armies"]) for t in st] == [(3201, 1), (3305, 4)]


def test_correct_llm_answer_is_untouched_and_unparsed_sentences_fall_back():
    ok = [{"pawn_id": 3201, "armies": 1, "size": 9, "names": ["Đội 1"]},
          {"pawn_id": 3305, "armies": 4, "size": 9, "names": ["Đội 2", "Đội 3", "Đội 4", "Đội 5"]}]
    st, notes = sanitize_strike(ok, U2, ASK2, N2, aliases=AL)
    assert [t["armies"] for t in st] == [1, 4] and notes == []
    st, _ = sanitize_strike(WRONG, U2, "lập đội hình mạnh giúp tôi", N2, aliases=AL)
    assert [t["armies"] for t in st] == [4, 1]   # nothing to cross-check against


def test_locked_type_named_in_the_sentence_is_not_resurrected():
    st, _ = sanitize_strike([{"pawn_id": 3305, "armies": 4, "size": 9}], {3305},
                            "1 đội đao khiên và 4 đội IMP", N2, aliases=AL)
    assert [t["pawn_id"] for t in st] == [3305]


def test_names_the_llm_garbled_are_dropped_when_counts_do_not_add_up():
    st, _ = sanitize_strike(WRONG, U2, "tạo 1 đội đao khiên và 4 đội IMP", N2, aliases=AL)
    assert all("names" not in t for t in st)
