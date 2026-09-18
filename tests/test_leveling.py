from nta_agent.execution.leveling import (
    next_level_action,
    pawns_needing_level,
    ready_pawns,
)

TARGET = 10


def _army(uid, index, pawns):
    return {"uid": uid, "index": index, "pawns": [{"uid": u, "id": 3101, "lv": lv} for u, lv in pawns]}


def test_needing_and_ready():
    la = _army("L", 100, [("a", 5), ("b", 10), ("c", 12)])
    assert {p["uid"] for p in pawns_needing_level(la, TARGET, [])} == {"a"}
    assert {p["uid"] for p in ready_pawns(la, TARGET)} == {"b", "c"}
    assert pawns_needing_level(la, TARGET, ["a"]) == []  # a already queued


def test_levels_lowest_pawn_when_exp_available():
    farm = _army("F", 100, [("f1", 10)])
    lv = _army("L", 100, [("a", 3), ("b", 7)])
    act = next_level_action(farm, lv, TARGET, farm_home=False, queue_uids=[], exp_book=5)
    assert act.kind == "level" and act.pawn_uid == "a" and act.army_uid == "L"


def test_no_level_without_exp_book():
    lv = _army("L", 100, [("a", 3)])
    assert next_level_action(_army("F", 100, []), lv, TARGET, exp_book=0) is None


def test_swaps_ready_into_farm_when_home():
    farm = _army("F", 100, [("f_low", 4), ("f_ok", 12)])
    lv = _army("L", 100, [("ready", 10), ("still", 6)])
    act = next_level_action(farm, lv, TARGET, farm_home=True, exp_book=5)
    assert act.kind == "swap" and act.ready_uid == "ready" and act.low_uid == "f_low"
    assert act.farm_uid == "F" and act.army_uid == "L"


def test_no_swap_when_farm_not_home():
    farm = _army("F", 100, [("f_low", 4)])
    lv = _army("L", 100, [("ready", 10)])
    act = next_level_action(farm, lv, TARGET, farm_home=False, exp_book=0)
    assert act is None  # not home -> no swap; no exp -> no level


def test_swap_takes_priority_over_level_when_home():
    farm = _army("F", 100, [("f_low", 4)])
    lv = _army("L", 100, [("ready", 10), ("todo", 3)])
    act = next_level_action(farm, lv, TARGET, farm_home=True, exp_book=5)
    assert act.kind == "swap"  # finishing a cycle beats starting a new level
