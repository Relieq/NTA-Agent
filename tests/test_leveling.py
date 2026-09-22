from nta_agent.execution.leveling import (
    LEVEL_ARMY_NAME,
    find_leveling_army,
    next_level_action,
)

TARGET = 10
MAIN = 100


def _army(uid, pawns, index=MAIN, name=""):
    return {"uid": uid, "index": index, "name": name,
            "pawns": [{"uid": u, "id": 3101, "lv": lv} for u, lv in pawns]}


def _lvl(pawns, index=MAIN):
    return _army("L", pawns, index=index, name=LEVEL_ARMY_NAME)


def test_find_leveling_army_by_name():
    a = _army("F", [("a", 1)]); b = _lvl([("x", 5)])
    assert find_leveling_army([a, b])["uid"] == "L"
    assert find_leveling_army([a]) is None


def test_inplace_levels_farm_pawn_when_no_buffer():
    """ChangePawnArmy can't create a buffer army (engine requires an existing
    destination -> ecode.500011), so with no leveling army we level the lowest
    under-target farm pawn IN PLACE (PawnLving on the farm army itself)."""
    farm = [_army("F1", [("a", 3), ("b", 12)])]
    act = next_level_action(farm, None, TARGET, farm_home=True, exp_book=5, max_leveling=1)
    assert act.kind == "level" and act.create is False
    assert act.level_uid == "F1" and act.pawn_uid == "a"   # levels in the farm army


def test_inplace_needs_exp_and_skips_queued():
    farm = [_army("F1", [("a", 3), ("c", 4)])]
    # no exp -> nothing to do in place
    assert next_level_action(farm, None, TARGET, farm_home=True, exp_book=0) is None
    # 'a' already queued -> level the next lowest ('c')
    act = next_level_action(farm, None, TARGET, farm_home=True, exp_book=5,
                            queue_uids={"a"})
    assert act.kind == "level" and act.level_uid == "F1" and act.pawn_uid == "c"


def test_no_inplace_when_farm_not_home():
    farm = [_army("F1", [("a", 3)], index=999)]
    assert next_level_action(farm, None, TARGET, farm_home=False, exp_book=5) is None


def test_pull_moves_into_existing_leveling_army():
    farm = [_army("F1", [("a", 3)])]
    lv = _lvl([])  # exists, empty, room for 1
    act = next_level_action(farm, lv, TARGET, farm_home=True, exp_book=0, max_leveling=1)
    assert act.kind == "pull" and act.create is False and act.level_uid == "L"


def test_levels_lowest_in_leveling_army():
    farm = [_army("F1", [("f", 12)])]
    lv = _lvl([("a", 3), ("b", 7)])
    act = next_level_action(farm, lv, TARGET, farm_home=True, exp_book=5, max_leveling=2)
    assert act.kind == "level" and act.pawn_uid == "a" and act.level_uid == "L"


def test_swap_ready_into_farm_when_home_takes_priority():
    farm = [_army("F1", [("f_low", 4)])]
    lv = _lvl([("ready", 10), ("todo", 3)])
    act = next_level_action(farm, lv, TARGET, farm_home=True, exp_book=5, max_leveling=2)
    assert act.kind == "swap" and act.ready_uid == "ready" and act.low_uid == "f_low"
    assert act.farm_uid == "F1" and act.level_uid == "L"


def test_dismiss_empty_leveling_army():
    farm = [_army("F1", [("f", 12)])]  # farm all at/above target
    lv = _lvl([])
    act = next_level_action(farm, lv, TARGET, farm_home=True, exp_book=5, max_leveling=1)
    assert act.kind == "dismiss" and act.level_uid == "L"


def test_no_pull_when_buffer_full():
    farm = [_army("F1", [("a", 3)])]
    lv = _lvl([("x", 3)])           # buffer already has 1 == max_leveling
    act = next_level_action(farm, lv, TARGET, farm_home=True, exp_book=0, max_leveling=1)
    assert act is None             # buffer full, no exp -> nothing (x will level when exp)


def test_no_swap_when_not_home():
    farm = [_army("F1", [("f_low", 4)], index=999)]
    lv = _lvl([("ready", 10)])
    act = next_level_action(farm, lv, TARGET, farm_home=False, exp_book=0)
    assert act is None
