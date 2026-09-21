"""Pure reconciliation planner for the army-composition strike group.

plan_composition_step returns the NEXT batch of actions (rally / move_pawn /
recruit / dismiss_pawn) to move current armies toward the target, plus the stable
strike-army assignment, a done flag, and a blocked flag (infeasible -> brain responds).
"""

from nta_agent.execution.composition_plan import plan_composition_step


def _army(uid, ids, index=100, state=0, name=None):
    pawns = []
    for i, x in enumerate(ids):
        d = {"id": x, "lv": 1} if not isinstance(x, dict) else dict(x)
        d.setdefault("uid", f"{uid}p{i}")
        pawns.append(d)
    return {"uid": uid, "index": index, "state": state,
            "name": name or uid, "pawns": pawns}


CITY = 100
TARGET = [{"pawn_id": 3206, "armies": 1, "size": 3},   # small sizes for readable tests
          {"pawn_id": 3305, "armies": 2, "size": 3}]    # 3 strike armies total


def test_blocked_when_locked_type_short():
    armies = [_army("a", [3305])]
    r = plan_composition_step(TARGET, armies, CITY, strike_uids=[], reserved_uids=set(),
                              unlocked_ids=set(), army_cap=9)
    assert r["blocked"] is True
    assert r["done"] is False
    assert r["report"].feasible is False


def test_assigns_stable_strike_armies_by_type_affinity():
    # 3 idle armies at city; assign 1 to 3206, 2 to 3305. Prefer armies already
    # holding the most of their assigned type.
    armies = [_army("tank", [3206, 3206, 3101]),
              _army("imp1", [3305, 3305, 3101]),
              _army("imp2", [3305, 3101, 3101]),
              _army("junk", [3101, 3101])]
    r = plan_composition_step(TARGET, armies, CITY, strike_uids=[], reserved_uids=set(),
                              unlocked_ids={3206, 3305}, army_cap=9)
    assign = {a["uid"]: a["pawn_id"] for a in r["assign"]}
    assert assign.get("tank") == 3206
    assert assign.get("imp1") == 3305 and assign.get("imp2") == 3305
    assert "junk" not in assign            # not a strike army (donor/pool)


def test_rally_when_a_strike_or_donor_army_is_scattered():
    # a donor holding target pawns sits at another cell -> must rally to city first.
    armies = [_army("tank", [3206, 3206, 3206]),
              _army("imp1", [3305, 3305, 3305]),
              _army("imp2", [3305, 3305, 3305]),
              _army("donor", [3305, 3305, 3305], index=250)]   # far
    r = plan_composition_step(TARGET, armies, CITY, strike_uids=["tank", "imp1", "imp2"],
                              reserved_uids=set(), unlocked_ids={3206, 3305}, army_cap=9)
    rallies = [a for a in r["actions"] if a["op"] == "rally"]
    assert rallies and 250 not in (CITY,) and "donor" in rallies[0]["uids"]


def test_moves_consolidate_target_type_into_strike_army():
    # imp1 has 1 IMP + room; a co-located donor has spare IMP -> move into imp1.
    armies = [_army("tank", [3206, 3206, 3206]),
              _army("imp1", [3305]),
              _army("imp2", [3305, 3305, 3305]),
              _army("donor", [3305, 3305, 3101])]
    r = plan_composition_step(TARGET, armies, CITY, strike_uids=["tank", "imp1", "imp2"],
                              reserved_uids=set(), unlocked_ids={3206, 3305}, army_cap=9)
    moves = [a for a in r["actions"] if a["op"] == "move_pawn"]
    # at least one IMP pawn moved from donor into imp1 (the short strike army)
    assert any(m["to"] == "imp1" for m in moves)
    assert all(m["from"] == "donor" for m in moves)   # pulled from the pool, not imp2


def test_recruit_when_owned_short_and_unlocked():
    # only 1 IMP total but 2x3=6 needed -> recruit the deficit into the IMP strike armies.
    armies = [_army("tank", [3206, 3206, 3206]),
              _army("imp1", [3305]),
              _army("imp2", [])]
    r = plan_composition_step(TARGET, armies, CITY, strike_uids=["tank", "imp1", "imp2"],
                              reserved_uids=set(), unlocked_ids={3206, 3305}, army_cap=9)
    recruits = [a for a in r["actions"] if a["op"] == "recruit"]
    assert recruits and all(x["pawn_id"] == 3305 for x in recruits)


def test_done_when_all_strike_armies_match_target():
    armies = [_army("tank", [3206, 3206, 3206]),
              _army("imp1", [3305, 3305, 3305]),
              _army("imp2", [3305, 3305, 3305])]
    r = plan_composition_step(TARGET, armies, CITY, strike_uids=["tank", "imp1", "imp2"],
                              reserved_uids=set(), unlocked_ids={3206, 3305}, army_cap=9)
    assert r["done"] is True
    assert r["actions"] == []


def test_reserved_armies_are_never_strike_or_donor():
    # 'farm' is reserved -> not chosen as strike, and its pawns are never pulled.
    armies = [_army("farm", [3305, 3305, 3305]),
              _army("tank", [3206, 3206, 3206]),
              _army("imp1", [3305, 3305, 3305]),
              _army("imp2", [3305])]
    r = plan_composition_step(TARGET, armies, CITY, strike_uids=["tank", "imp1", "imp2"],
                              reserved_uids={"farm"}, unlocked_ids={3206, 3305}, army_cap=9)
    assert all(a["uid"] != "farm" for a in r["assign"])
    moves = [a for a in r["actions"] if a["op"] == "move_pawn"]
    assert all(m["from"] != "farm" for m in moves)   # never pull from a reserved army
