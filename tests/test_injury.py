from nta_agent.execution.injury import NEW_ARMY_NAME, best_injured, revive_target


def test_best_injured_picks_highest_lv_then_id():
    pawns = [{"uid": "a", "id": 3101, "lv": 1}, {"uid": "b", "id": 3305, "lv": 3},
             {"uid": "c", "id": 3400, "lv": 3}]
    assert best_injured(pawns)["uid"] == "c"   # lv 3 tie -> higher id
    assert best_injured([]) is None


def test_revive_target_prefers_the_origin_army_with_room():
    main = 100 * 600 + 100
    armies = [
        {"uid": "full", "name": "D1", "index": main, "pawns": [{}] * 9},
        {"uid": "room", "name": "Đội 2", "index": main, "pawns": [{}] * 5, "curingPawns": [{}]},
    ]
    assert revive_target(armies, main, capacity_hint=9, origin="room") == ("room", "Đội 2")
    # an army with room that is NOT the origin is never used (it was a spare / buffer)
    assert revive_target(armies, main, capacity_hint=9)[0] == ""


def test_revive_target_new_army_when_all_full():
    main = 100 * 600 + 100
    armies = [
        {"uid": "full", "name": "D1", "index": main, "pawns": [{}] * 9},
        {"uid": "away", "name": "D2", "index": main + 1, "pawns": [{}]},  # not at main
    ]
    assert revive_target(armies, main, capacity_hint=9) == ("", NEW_ARMY_NAME)
