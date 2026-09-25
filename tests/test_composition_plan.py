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


def test_recruit_targets_a_non_full_strike_army():
    # imp1 is already FULL (3 of 3305); imp2 is short. The recruit must target imp2,
    # not the full imp1 (else it loops on 500019 and imp2 never fills).
    armies = [_army("tank", [3206, 3206, 3206]),
              _army("imp1", [3305, 3305, 3305]),   # full for size 3
              _army("imp2", [3305])]                # short
    r = plan_composition_step(TARGET, armies, CITY, strike_uids=["tank", "imp1", "imp2"],
                              reserved_uids=set(), unlocked_ids={3206, 3305}, army_cap=9)
    rec = [a for a in r["actions"] if a["op"] == "recruit" and a["pawn_id"] == 3305]
    assert rec and rec[0]["army"] == "imp2"      # not the full imp1


def test_done_when_all_strike_armies_match_target():
    armies = [_army("tank", [3206, 3206, 3206]),
              _army("imp1", [3305, 3305, 3305]),
              _army("imp2", [3305, 3305, 3305])]
    r = plan_composition_step(TARGET, armies, CITY, strike_uids=["tank", "imp1", "imp2"],
                              reserved_uids=set(), unlocked_ids={3206, 3305}, army_cap=9)
    assert r["done"] is True
    assert r["actions"] == []


def test_purge_dismisses_lowest_level_non_target_when_no_donor_room():
    # imp1 (strike for 3305) is clogged with two 3101; no donor -> dismiss them,
    # lowest level first. It keeps its 3305 (target) so it never empties.
    armies = [_army("tank", [3206, 3206, 3206]),
              _army("imp1", [3305, {"id": 3101, "lv": 5}, {"id": 3101, "lv": 2}]),
              _army("imp2", [3305, 3305, 3305])]
    r = plan_composition_step(TARGET, armies, CITY, strike_uids=["tank", "imp1", "imp2"],
                              reserved_uids=set(), unlocked_ids={3206, 3305}, army_cap=9)
    dis = [a for a in r["actions"] if a["op"] == "dismiss_pawn" and a["army"] == "imp1"]
    assert [a["pawn"] for a in dis] == ["imp1p2", "imp1p1"]   # lv2 pawn before lv5


def test_purge_prefers_moving_non_target_to_a_donor_with_room():
    # a co-located donor has room -> the non-target pawn is moved (preserved), not dismissed.
    armies = [_army("tank", [3206, 3206, 3206]),
              _army("imp1", [3305, {"id": 3101, "lv": 5}]),
              _army("imp2", [3305, 3305, 3305]),
              _army("donor", [3305])]                 # room for more
    r = plan_composition_step(TARGET, armies, CITY, strike_uids=["tank", "imp1", "imp2"],
                              reserved_uids=set(), unlocked_ids={3206, 3305}, army_cap=9)
    assert not any(a["op"] == "dismiss_pawn" for a in r["actions"])
    assert any(a["op"] == "move_pawn" and a["pawn"] == "imp1p1" and a["to"] == "donor"
               for a in r["actions"])


def test_purge_never_empties_an_unfilled_strike_army():
    # a strike army holding ONLY non-target pawns (no 3305 yet) must keep >=1 pawn
    # so its uid survives until target pawns arrive.
    armies = [_army("tank", [3206, 3206, 3206]),
              _army("imp1", [3305, 3305, 3305]),
              _army("imp2", [{"id": 3101, "lv": 1}])]      # only junk, no target
    r = plan_composition_step(TARGET, armies, CITY, strike_uids=["tank", "imp1", "imp2"],
                              reserved_uids=set(), unlocked_ids={3206, 3305}, army_cap=9)
    dis = [a for a in r["actions"] if a["op"] == "dismiss_pawn" and a["army"] == "imp2"]
    assert dis == []                                        # last pawn kept


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


def test_pulls_from_mixed_donors_before_pure_ones():
    """User rule (2026-09-25): take IMP out of MIXED armies (IMP + Đao Khiên) to fill a
    short strike army; don't break up a pure IMP army (it moved 8 of a full 9-IMP one)."""
    armies = [_army("tank", [3206] * 3), _army("imp1", [3305]), _army("imp2", [3305] * 3),
              _army("mixed", [3305, 3305, 3201, 3201, 3201]),    # mixed donor (listed FIRST:
              _army("pure", [3305, 3305, 3305])]                 # list order must not decide)
    r = plan_composition_step(TARGET, armies, CITY, strike_uids=["tank", "imp1", "imp2"],
                              reserved_uids=set(), unlocked_ids={3206, 3305}, army_cap=9)
    froms = [m["from"] for m in r["actions"] if m["op"] == "move_pawn" and m["to"] == "imp1"]
    assert froms == ["mixed", "mixed"]
