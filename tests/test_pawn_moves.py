"""Swapping / moving / reordering pawns on the player's request (chat): the brain only
PROPOSES, the guard resolves the pawns deterministically, the player confirms, then a
queue waits for idle armies. A change that the active strike goal (ArmyComposer) would
undo cancels that goal on confirm — the player's rearrangement is the final word."""
from __future__ import annotations

import json
from pathlib import Path

from nta_agent.dashboard.server import confirm_pawn_moves, handle_chat
from nta_agent.execution.pawn_moves import (
    apply_moves,
    sanitize_pawn_moves,
    strike_conflicts,
)
from nta_agent.runtime.commands import read_pending
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.pawn_move_queue import PawnMoveQueue


def _army(uid, name, pawns, state=0, index=100):
    out = []
    for i, t in enumerate(pawns):
        p = {"uid": f"{uid}{i}", "id": t[0], "lv": t[1]}
        if len(t) > 2 and t[2]:
            p["hero"] = True
        out.append(p)
    return {"uid": uid, "name": name, "index": index, "state": state, "pawns": out}


def _armies():
    return [_army("A", "Đội 1", [(3206, 3), (3206, 1), (3305, 2), (3305, 4)]),
            _army("B", "Đội 2", [(3305, 1), (3305, 3), (3206, 2)]),
            _army("C", "Đội 3", [(3305, 1)], index=200),               # another cell
            _army("D", "Đội 4", [(3305, 5)], state=1)]                 # marching


# ---- guard -----------------------------------------------------------------------
def test_swap_picks_the_lowest_level_pawns_of_each_type():
    out, _ = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3206, "army_b": "B", "pawn_b": 3305}],
        _armies())
    (m,) = out
    assert m["op"] == "swap" and m["count"] == 1
    assert m["pairs"] == [["A1", "B0"]]            # A's lowest 3206 (lv1) <-> B's lowest 3305 (lv1)


def test_swap_needs_the_same_cell_and_two_different_armies():
    out, notes = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3206, "army_b": "C", "pawn_b": 3305},
         {"op": "swap", "army_a": "A", "pawn_a": 3206, "army_b": "A", "pawn_b": 3305}],
        _armies())
    assert out == [] and any("cùng ô" in n for n in notes)


def test_swap_clamps_count_to_what_both_sides_have():
    out, _ = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3206, "army_b": "B", "pawn_b": 3206,
          "count": 5}], _armies())
    assert out[0]["count"] == 1                       # B has a single 3206


def test_move_takes_lowest_level_and_respects_the_army_cap():
    out, _ = sanitize_pawn_moves(
        [{"op": "move", "army_from": "A", "army_to": "B", "pawn_id": 3305, "count": 1}],
        _armies(), cap=9)
    assert out[0]["pawn_uids"] == ["A2"] and out[0]["to"] == "B"
    out, notes = sanitize_pawn_moves(
        [{"op": "move", "army_from": "A", "army_to": "B", "pawn_id": 3305, "count": 2}],
        _armies(), cap=4)                              # B has 3, cap 4 -> room for 1
    assert out[0]["count"] == 1 and any("chỗ" in n for n in notes)


def test_move_to_a_new_army_and_heroes_stay_put():
    armies = _armies()
    armies[0]["pawns"][0]["hero"] = True
    out, _ = sanitize_pawn_moves(
        [{"op": "move", "army_from": "A", "army_to": "new", "pawn_id": 3206, "count": 2}],
        armies)
    assert out[0]["to"] == "new" and out[0]["pawn_uids"] == ["A1"]   # the hero A0 is skipped


def test_reorder_sorts_listed_types_first_keeping_the_rest_stable():
    out, _ = sanitize_pawn_moves([{"op": "reorder", "army": "A", "order": [3305]}], _armies())
    (m,) = out
    new = apply_moves(out, _armies())
    a = next(x for x in new if x["uid"] == "A")
    assert [p["id"] for p in a["pawns"]] == [3305, 3305, 3206, 3206]
    assert m["op"] == "reorder" and m["swaps"]
    out, _ = sanitize_pawn_moves([{"op": "reorder", "army": "A", "order": [3206]}], _armies())
    assert out == []                                  # already in that order -> nothing to do


def test_unknown_armies_and_garbage_are_dropped():
    out, _ = sanitize_pawn_moves(
        ["x", {"op": "swap"}, {"op": "move", "army_from": "ZZ", "army_to": "A", "pawn_id": 1},
         {"op": "teleport"}], _armies())
    assert out == []


# ---- the strike goal -------------------------------------------------------------
def test_a_swap_that_mixes_a_strike_army_conflicts_with_the_goal():
    # A = the 3206 strike army, B = the 3305 strike army; after the swap both are mixed
    armies = _armies()
    armies[0]["pawns"] = [p for p in armies[0]["pawns"] if p["id"] == 3206]
    armies[1]["pawns"] = [p for p in armies[1]["pawns"] if p["id"] == 3305]
    ops, _ = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3206, "army_b": "B", "pawn_b": 3305}], armies)
    assert strike_conflicts(ops, armies, ["A", "B"])
    assert strike_conflicts(ops, armies, []) == []        # no goal armies -> nothing to undo
    assert strike_conflicts(ops, armies, ["C"]) == []     # untouched army


def test_reorder_never_conflicts_and_a_donor_is_free_to_change():
    armies = _armies()
    ops, _ = sanitize_pawn_moves([{"op": "reorder", "army": "A", "order": [3305]}], armies)
    assert strike_conflicts(ops, armies, ["A"]) == []


# ---- queue -----------------------------------------------------------------------
class Acts:
    def __init__(self, armies):
        self.armies, self.calls = armies, []

    def get_player_armys(self):
        return self.armies

    def exchange_pawn_army(self, index, army_uid, uid1, uid2, army_uid2=None):
        self.calls.append(("ex", index, army_uid, uid1, uid2, army_uid2))

    def change_pawn_army(self, index, army_uid, pawn_uid, new_army_uid="", **kw):
        self.calls.append(("mv", index, army_uid, pawn_uid, new_army_uid, kw))


def test_queue_swaps_when_both_armies_are_idle(tmp_path):
    ops, _ = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3206, "army_b": "B", "pawn_b": 3305}],
        _armies())
    q = PawnMoveQueue(tmp_path / "q.json")
    q.add(ops[0])
    acts = Acts(_armies())
    acts.armies[1]["state"] = 1                        # B marches: wait
    q.process(acts, lambda *a: None)
    assert acts.calls == []
    acts.armies[1]["state"] = 0
    ev = []
    q.process(acts, lambda k, d: ev.append(k))
    assert acts.calls == [("ex", 100, "A", "A1", "B0", "B")] and ev == ["pawn_move_done"]
    assert q.pending() == {}


def test_queue_moves_into_a_new_army_then_fills_it(tmp_path):
    ops, _ = sanitize_pawn_moves(
        [{"op": "move", "army_from": "B", "army_to": "new", "pawn_id": 3305, "count": 2}],
        _armies())
    q = PawnMoveQueue(tmp_path / "q.json")
    q.add(ops[0])

    class Acts2(Acts):
        def change_pawn_army(self, index, army_uid, pawn_uid, new_army_uid="", **kw):
            super().change_pawn_army(index, army_uid, pawn_uid, new_army_uid, **kw)
            if kw.get("is_new_create"):
                self.armies.append(_army("N", "Mới", [(3305, 1)]))

    acts = Acts2(_armies())
    q.process(acts, lambda *a: None)
    assert acts.calls[0][5].get("is_new_create") is True
    assert acts.calls[1][:5] == ("mv", 100, "B", "B1", "N")
    assert q.pending() == {}


def test_queue_reorders_by_swapping_inside_the_army(tmp_path):
    ops, _ = sanitize_pawn_moves([{"op": "reorder", "army": "A", "order": [3305]}], _armies())
    q = PawnMoveQueue(tmp_path / "q.json")
    q.add(ops[0])
    acts = Acts(_armies())
    q.process(acts, lambda *a: None)
    assert acts.calls and all(c[0] == "ex" and c[2] == "A" and c[5] in (None, "A")
                              for c in acts.calls)


def test_queue_drops_a_permanent_refusal(tmp_path):
    class Refuse(Acts):
        def exchange_pawn_army(self, *a, **k):
            raise RuntimeError("game/HD_ExchangePawnArmy: ecode.500099")
    ops, _ = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3206, "army_b": "B", "pawn_b": 3305}],
        _armies())
    q = PawnMoveQueue(tmp_path / "q.json")
    q.add(ops[0])
    ev = []
    q.process(Refuse(_armies()), lambda k, d: ev.append(k))
    assert ev == ["pawn_move_failed"] and q.pending() == {}


# ---- chat: propose, then confirm --------------------------------------------------
def _cfg(tmp_path, strike=None):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    Path(cfg.armies_path).write_text(json.dumps(_armies(), ensure_ascii=False), encoding="utf-8")
    if strike is not None:
        Path(tmp_path / "composition_status.json").write_text(
            json.dumps({"active": True, "strike": strike}), encoding="utf-8")
    return cfg


SWAP = {"op": "swap", "army_a": "A", "pawn_a": 3206, "army_b": "B", "pawn_b": 3305}


def test_chat_proposes_pawn_moves_without_executing(tmp_path):
    cfg = _cfg(tmp_path)

    def propose(digest, profile, instruction=None, history=None):
        return {"pawn_moves": [SWAP]}
    out = handle_chat(cfg, "đổi 1 rìu khiên đội 1 lấy 1 IMP đội 2", history=[], propose=propose)
    assert out["ok"] and out["needs_confirm"] is True
    (m,) = out["pawn_moves"]
    assert m["op"] == "swap" and m["name_a"] == "Đội 1" and m["conflict"] == []
    assert not [c for c in read_pending(cfg.commands_path, cfg.commands_done_path)
                if c.get("action") == "pawn_moves"]


def test_confirm_queues_the_move_and_cancels_a_conflicting_goal(tmp_path):
    from nta_agent.execution.profile import load_profile, save_profile
    cfg = _cfg(tmp_path, strike=["A", "B"])
    armies = _armies()
    armies[0]["pawns"] = [p for p in armies[0]["pawns"] if p["id"] == 3206]
    armies[1]["pawns"] = [p for p in armies[1]["pawns"] if p["id"] == 3305]
    Path(cfg.armies_path).write_text(json.dumps(armies), encoding="utf-8")
    prof = load_profile(cfg.profile_path)
    prof.army["strike_target"] = [{"pawn_id": 3206, "armies": 1, "size": 9},
                                  {"pawn_id": 3305, "armies": 1, "size": 9}]
    save_profile(prof, cfg.profile_path)

    r = confirm_pawn_moves(cfg, [SWAP])
    assert r["ok"] and len(r["queued"]) == 1 and r["cancelled_goal"] is True
    cmds = read_pending(cfg.commands_path, cfg.commands_done_path)
    assert [c["action"] for c in cmds] == ["profile_edit", "pawn_moves"]
    assert cmds[0]["edits"] == {"army": {"strike_target": []}}
    assert load_profile(cfg.profile_path).army["strike_target"] == []


def test_confirm_without_a_conflict_keeps_the_goal(tmp_path):
    cfg = _cfg(tmp_path, strike=[])
    r = confirm_pawn_moves(cfg, [SWAP])
    assert r["ok"] and r["cancelled_goal"] is False
    assert [c["action"] for c in read_pending(cfg.commands_path, cfg.commands_done_path)] \
        == ["pawn_moves"]


def test_decision_service_hands_the_command_to_the_queue(tmp_path):
    from nta_agent.runtime.decision_service import DecisionService
    svc = DecisionService.__new__(DecisionService)
    svc.actions, svc.profile = Acts([]), None
    svc.pawn_moves = PawnMoveQueue(tmp_path / "pq.json")
    ops, _ = sanitize_pawn_moves([SWAP], _armies())
    svc._execute({"action": "pawn_moves", "ops": ops})
    assert len(svc.pawn_moves.pending()) == 1


# ---- feedback + tolerant parsing (live 2026-10-01: a bare op from the brain = silence) ----
def test_slot_position_picks_the_last_or_first_pawn_of_a_type():
    out, _ = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3305, "pos_a": "last",
          "army_b": "B", "pawn_b": 3206, "pos_b": "first"}], _armies())
    assert out[0]["pairs"] == [["A3", "B2"]]          # A's LAST 3305 slot, B's first 3206
    out, _ = sanitize_pawn_moves(
        [{"op": "move", "army_from": "A", "army_to": "B", "pawn_id": 3206, "pos": "last"}],
        _armies())
    assert out[0]["pawn_uids"] == ["A1"]


def test_every_drop_says_why():
    _, notes = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3305, "army_b": "A", "pawn_b": 3206},
         {"op": "swap", "army_a": "A", "pawn_a": 9999, "army_b": "B", "pawn_b": 3206},
         {"op": "swap", "army_a": "ZZ", "pawn_a": 3305, "army_b": "B", "pawn_b": 3206},
         {"op": "reorder", "army": "A", "order": [3206]}], _armies())
    text = " ".join(notes)
    assert "cùng" in text or "hai đội khác nhau" in text
    assert "không có lính loại 9999" in text and "Không xác định" in text and "đúng thứ tự" in text


def test_a_bare_op_from_the_brain_is_still_proposed(tmp_path):
    cfg = _cfg(tmp_path)

    def propose(digest, profile, instruction=None, history=None):
        return dict(SWAP)                                  # no "pawn_moves" wrapper
    out = handle_chat(cfg, "đổi lính", history=[], propose=propose)
    assert out["needs_confirm"] and out["pawn_moves"][0]["op"] == "swap"

    def single(digest, profile, instruction=None, history=None):
        return {"pawn_moves": dict(SWAP)}                  # a dict instead of a list
    assert handle_chat(cfg, "đổi lính", history=[], propose=single)["pawn_moves"]


def test_a_rearrangement_request_is_never_answered_with_silence(tmp_path):
    cfg = _cfg(tmp_path)

    def nothing(digest, profile, instruction=None, history=None):
        return {}
    out = handle_chat(cfg, "Tráo đổi 1 lính thợ săn từ đội D3 với lính cung độc cuối đội 5",
                      history=[], propose=nothing)
    assert out["pawn_moves"] == [] and out["notices"]
    out = handle_chat(cfg, "xây thêm kho lương", history=[], propose=nothing)
    assert not any("tráo" in n for n in out["notices"])


def test_what_the_card_sends_back_confirms(tmp_path):
    """The dashboard sends each proposal's ``spec`` on confirm (live 2026-10-01: it sent the
    RESOLVED op, the re-validation found no army_a/pawn_a and refused every confirm)."""
    cfg = _cfg(tmp_path)
    ops = [
        dict(SWAP, pos_a="last"),
        {"op": "move", "army_from": "A", "army_to": "B", "pawn_id": 3305, "count": 1},
        {"op": "reorder", "army": "A", "order": [3305]},
    ]

    def propose(digest, profile, instruction=None, history=None):
        return {"pawn_moves": ops}
    out = handle_chat(cfg, "đổi lính", history=[], propose=propose)
    specs = [m["spec"] for m in out["pawn_moves"]]
    assert [s["op"] for s in specs] == ["swap", "move", "reorder"]
    r = confirm_pawn_moves(cfg, specs)
    assert r["ok"] and [q["op"] for q in r["queued"]] == ["swap", "move", "reorder"]
    swap = r["queued"][0]
    assert swap["pairs"] == out["pawn_moves"][0]["pairs"]      # the same pawns as proposed


# ---- armies in different cells: gather at the main city first -----------------------
CITY = 100          # _armies(): A, B, D at 100; C at 200


def test_different_cells_are_kept_with_a_gather_step_when_there_is_a_meeting_cell():
    ops, notes = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3206, "army_b": "C", "pawn_b": 3305}],
        _armies(), meet=CITY)
    assert notes == [] and ops[0]["gather"] is True and ops[0]["index"] == CITY
    from nta_agent.dashboard.server import pawn_move_label
    assert "(100, 0)" in pawn_move_label(ops[0]) and ops[0]["travel"] == ["Đội 3"]
    # same cell: no gather
    ops, _ = sanitize_pawn_moves([SWAP], _armies(), meet=CITY)
    assert ops[0]["gather"] is False
    # no meeting cell known: dropped with the old notice
    ops, notes = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3206, "army_b": "C", "pawn_b": 3305}],
        _armies())
    assert ops == [] and any("cùng ô" in n for n in notes)


class MovingActs(Acts):
    """Armies march one tick after the order, then arrive idle at the target."""
    def __init__(self, armies):
        super().__init__(armies)
        self.arriving = []

    def move_cell_army(self, armies, target):
        self.calls.append(("move", [a["uid"] for a in armies], target))
        for a in armies:
            army = next(x for x in self.armies if x["uid"] == a["uid"])
            army["state"] = 1
            self.arriving.append((army, target))

    def land(self):
        for army, target in self.arriving:
            army["state"], army["index"] = 0, target
        self.arriving = []


def test_queue_gathers_the_far_army_waits_for_it_then_swaps(tmp_path):
    ops, _ = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3206, "army_b": "C", "pawn_b": 3305}],
        _armies(), meet=CITY)
    q = PawnMoveQueue(tmp_path / "q.json")
    q.add(ops[0])
    acts = MovingActs(_armies())
    ev = []
    q.process(acts, lambda k, d: ev.append(k))
    assert acts.calls == [("move", ["C"], CITY)] and ev == ["pawn_move_gather"]
    q.process(acts, lambda k, d: ev.append(k))            # C is marching: wait, no re-order
    assert len(acts.calls) == 1
    acts.land()
    q.process(acts, lambda k, d: ev.append(k))
    assert acts.calls[-1][0] == "ex" and acts.calls[-1][1] == CITY and ev[-1] == "pawn_move_done"
    assert q.pending() == {}


def test_both_far_armies_are_called_and_a_busy_one_waits_first(tmp_path):
    armies = _armies()
    armies[0]["index"] = 300                                # A is away too
    armies[0]["state"] = 1                                  # ... and marching
    ops, _ = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3206, "army_b": "C", "pawn_b": 3305}],
        armies, meet=CITY)
    q = PawnMoveQueue(tmp_path / "q.json")
    q.add(ops[0])
    acts = MovingActs(armies)
    q.process(acts, lambda *a: None)
    assert acts.calls == []                                 # A is busy: nothing is ordered yet
    armies[0]["state"] = 0
    q.process(acts, lambda *a: None)
    assert acts.calls == [("move", ["A", "C"], CITY)]       # both far: both are called


def test_gathering_gives_up_after_a_few_orders_that_do_nothing(tmp_path):
    class Stuck(Acts):
        def move_cell_army(self, armies, target):
            self.calls.append(("move",))
    ops, _ = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3206, "army_b": "C", "pawn_b": 3305}],
        _armies(), meet=CITY)
    q = PawnMoveQueue(tmp_path / "q.json")
    q.add(ops[0])
    acts, ev = Stuck(_armies()), []
    for _ in range(6):
        q.process(acts, lambda k, d: ev.append(k))
    assert len(acts.calls) == 3 and ev[-1] == "pawn_move_failed" and q.pending() == {}


def test_a_stalled_job_is_dropped_and_releases_its_armies(tmp_path):
    from nta_agent.runtime import pawn_move_queue as pq
    ops, _ = sanitize_pawn_moves([SWAP], _armies(), meet=CITY)
    q = PawnMoveQueue(tmp_path / "q.json")
    q.add(ops[0])
    assert q.army_uids() == {"A", "B"}
    armies = _armies()
    armies[0]["state"] = 3                                   # never idle (e.g. recruiting)
    acts, ev = Acts(armies), []
    for _ in range(pq.MAX_AGE + 2):
        q.process(acts, lambda k, d: ev.append(k))
    assert ev == ["pawn_move_failed"] and q.army_uids() == set()


def test_other_rules_are_kept_off_the_armies_a_job_is_gathering(tmp_path):
    from nta_agent.runtime.decision_service import DecisionService
    svc = DecisionService.__new__(DecisionService)
    svc.pawn_moves = PawnMoveQueue(tmp_path / "pq.json")
    ops, _ = sanitize_pawn_moves([SWAP, {"op": "reorder", "army": "B", "order": [3305]}],
                                 _armies(), meet=CITY)
    for op in ops:
        svc.pawn_moves.add(op)
    assert svc.pawn_moves.army_uids() == {"A", "B"}


def test_chat_offers_the_gather_and_a_question_gets_no_generic_notice(tmp_path):
    import json as _json
    cfg = _cfg(tmp_path)
    Path(cfg.snapshot_path).write_text(_json.dumps({"main_city_index": CITY}), encoding="utf-8")

    def propose(digest, profile, instruction=None, history=None):
        return {"pawn_moves": [{"op": "swap", "army_a": "A", "pawn_a": 3206,
                                "army_b": "C", "pawn_b": 3305}]}
    out = handle_chat(cfg, "tráo lính", history=[], propose=propose)
    (m,) = out["pawn_moves"]
    assert m["gather"] is True and "(100, 0)" in m["label"] and out["needs_confirm"]
    r = confirm_pawn_moves(cfg, [m["spec"]])
    assert r["ok"] and r["queued"][0]["gather"] is True

    def asks(digest, profile, instruction=None, history=None):
        return {"question": "Bạn muốn đổi lính nào?"}
    out = handle_chat(cfg, "tráo lính", history=[], propose=asks)
    assert out["question"] and not any("chưa đề xuất" in n for n in out["notices"])


# ---- the meeting cell: halfway inside our land, not the city ---------------------------
def _c(x, y):
    return y * 600 + x


def test_meeting_cell_is_halfway_between_the_armies_inside_our_land():
    from nta_agent.execution.pawn_moves import choose_meet
    owned = {_c(x, 10) for x in range(5, 40)}
    m = choose_meet([_c(10, 10), _c(20, 10)], owned, fallback=_c(5, 10))
    assert m == _c(15, 10)                                  # 5 cells each, not 10 for one army
    # one army off our land: the meeting cell is still ours, and the nearest one to both
    m = choose_meet([_c(10, 10), _c(10, 14)], owned, fallback=_c(5, 10))
    assert m in owned and max(abs(m % 600 - 10) + abs(m // 600 - 10),
                              abs(m % 600 - 10) + abs(m // 600 - 14)) <= 6
    # tie -> the cell with fewer armies already standing on it
    m = choose_meet([_c(10, 10), _c(13, 10)], owned, fallback=None)
    assert m == _c(11, 10)                                  # 11 and 12 tie -> the lower index
    m = choose_meet([_c(10, 10), _c(13, 10)], owned, fallback=None,
                    occupied={_c(11, 10): 3})
    assert m == _c(12, 10)
    # nothing known about our land -> the fallback (main city)
    assert choose_meet([_c(10, 10), _c(20, 10)], set(), fallback=_c(1, 1)) == _c(1, 1)
    assert choose_meet([_c(10, 10)], set()) is None


def test_chat_picks_the_midpoint_from_the_territory_file(tmp_path):
    import json as _json
    cfg = _cfg(tmp_path)
    armies = _armies()
    armies[0]["index"], armies[2]["index"] = _c(10, 10), _c(20, 10)    # A and C, 10 cells apart
    Path(cfg.armies_path).write_text(_json.dumps(armies), encoding="utf-8")
    Path(cfg.forts_path).write_text(_json.dumps(
        {"owned_cells": [[x, 10] for x in range(5, 40)]}), encoding="utf-8")

    def propose(digest, profile, instruction=None, history=None):
        return {"pawn_moves": [{"op": "swap", "army_a": "A", "pawn_a": 3206,
                                "army_b": "C", "pawn_b": 3305}]}
    out = handle_chat(cfg, "tráo lính", history=[], propose=propose)
    (m,) = out["pawn_moves"]
    assert m["meet"] == _c(15, 10) and sorted(m["travel"]) == ["Đội 1", "Đội 3"]
    assert "(15, 10)" in m["label"]


# ---- 5 armies per cell, and the army about to attack stays at the front -----------------
def test_a_cell_with_five_armies_is_never_the_meeting_cell():
    from nta_agent.execution.pawn_moves import choose_meet
    owned = {_c(x, 10) for x in range(5, 40)}
    full = {_c(15, 10): 5}                                  # the midpoint is full
    m = choose_meet([_c(10, 10), _c(20, 10)], owned, occupied=full)
    assert m != _c(15, 10) and m in owned
    assert choose_meet([_c(10, 10), _c(20, 10)], owned, occupied=full) in (_c(14, 10), _c(16, 10))
    # one army already stands on the cell (4 there, itself included) + 1 arriving = 5: allowed
    assert choose_meet([_c(10, 10), _c(11, 10)], {_c(11, 10)}, occupied={_c(11, 10): 4}) == _c(11, 10)
    # 5 there already -> a 6th cannot come
    assert choose_meet([_c(10, 10), _c(11, 10)], {_c(11, 10)}, occupied={_c(11, 10): 5}) is None
    # both would arrive: 4 + 2 = 6 > 5
    assert choose_meet([_c(10, 10), _c(12, 10)], {_c(11, 10)}, occupied={_c(11, 10): 4}) is None


def test_the_army_about_to_attack_stays_and_the_other_walks_over():
    from nta_agent.execution.pawn_moves import choose_meet
    owned = {_c(x, 10) for x in range(5, 40)}
    # hot army at x=30, the other at x=10: meet where the hot one is (it does not move)
    assert choose_meet([_c(30, 10), _c(10, 10)], owned, anchor=_c(30, 10)) == _c(30, 10)
    # its cell has no room -> the closest owned cell to it
    m = choose_meet([_c(30, 10), _c(10, 10)], owned, anchor=_c(30, 10),
                    occupied={_c(30, 10): 5})
    assert m in (_c(29, 10), _c(31, 10))


def test_chat_keeps_the_group_army_in_place_and_calls_the_other(tmp_path):
    import json as _json

    from nta_agent.execution.profile import load_profile, save_profile
    cfg = _cfg(tmp_path)
    armies = _armies()
    armies[0]["index"], armies[2]["index"] = _c(30, 10), _c(10, 10)      # A far east, C west
    Path(cfg.armies_path).write_text(_json.dumps(armies), encoding="utf-8")
    Path(cfg.forts_path).write_text(_json.dumps(
        {"owned_cells": [[x, 10] for x in range(5, 40)]}), encoding="utf-8")
    prof = load_profile(cfg.profile_path)
    prof.army["group"] = ["A"]                                            # A = the farm / dig group
    save_profile(prof, cfg.profile_path)

    def propose(digest, profile, instruction=None, history=None):
        return {"pawn_moves": [{"op": "swap", "army_a": "A", "pawn_a": 3206,
                                "army_b": "C", "pawn_b": 3305}]}
    (m,) = handle_chat(cfg, "tráo lính", history=[], propose=propose)["pawn_moves"]
    assert m["meet"] == _c(30, 10) and m["travel"] == ["Đội 3"] and m["stay"] == ["Đội 1"]
    assert "Đội 1 đứng yên" in m["label"]
    # both armies in the group (or neither): halfway
    prof.army["group"] = ["A", "C"]
    save_profile(prof, cfg.profile_path)
    (m,) = handle_chat(cfg, "tráo lính", history=[], propose=propose)["pawn_moves"]
    assert m["meet"] == _c(20, 10)


def test_no_meeting_cell_says_so(tmp_path):
    ops, notes = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3206, "army_b": "C", "pawn_b": 3305}],
        _armies(), meet=lambda involved: None)
    assert ops == [] and any("danh sách đất" in n for n in notes)


# ---- the names the player typed must match the armies the brain picked ------------------
def _named():
    return [_army("A", "D1", [(3305, 1)]), _army("B", "Đội 1", [(3201, 1), (3201, 2)]),
            _army("C", "Đội 5", [(3305, 3), (3305, 4)]), _army("E", "D3", [(3305, 2)])]


def test_a_named_army_that_does_not_exist_stops_the_proposal():
    from nta_agent.execution.pawn_moves import check_names
    armies = [a for a in _named() if a["uid"] != "A"]                 # there is no "D1" now
    ops, _ = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "C", "pawn_a": 3305, "army_b": "B", "pawn_b": 3201}], armies)
    keep, notes = check_names("Tráo 1 lính IMP từ đội D1 với lính Đao Khiên cuối Đội 1", ops, armies)
    assert keep == [] and "D1" in notes[0] and "Đội 5" in notes[0]    # lists what exists


def test_the_brain_using_other_armies_than_the_named_ones_is_not_accepted():
    from nta_agent.execution.pawn_moves import check_names
    armies = _named()
    wrong, _ = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "C", "pawn_a": 3305, "army_b": "B", "pawn_b": 3201}], armies)
    keep, notes = check_names("Tráo đổi 1 lính IMP từ đội D1 với lính cuối Đội 1", wrong, armies)
    assert keep == [] and notes
    right, _ = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "A", "pawn_a": 3305, "army_b": "B", "pawn_b": 3201}], armies)
    keep, notes = check_names("Tráo đổi 1 lính IMP từ đội D1 với lính cuối Đội 1", right, armies)
    assert len(keep) == 1 and notes == []
    # 'D1' is not 'Đội 1', and 'đội 5' / 'Đội 5' / 'doi5' are the same army
    from nta_agent.execution.pawn_moves import mentioned_armies
    assert mentioned_armies("đội D1 và đội 5", armies)[0] == ["A", "C"]
    assert mentioned_armies("doi5", armies)[0] == ["C"]
    assert mentioned_armies("lính 3D", armies) == ([], [])


def test_naming_fewer_armies_than_the_op_uses_is_not_second_guessed():
    from nta_agent.execution.pawn_moves import check_names
    armies = _named()
    ops, _ = sanitize_pawn_moves(
        [{"op": "swap", "army_a": "E", "pawn_a": 3305, "army_b": "C", "pawn_b": 3305}], armies)
    keep, notes = check_names("Tráo 1 lính của đội D3 với lính cuối đội IMP bất kỳ", ops, armies)
    assert len(keep) == 1 and notes == []
    keep, notes = check_names("tráo lính cho tôi", ops, armies)         # no names at all
    assert len(keep) == 1 and notes == []


def test_chat_refuses_a_guessed_army_and_says_which_names_exist(tmp_path):
    import json as _json
    cfg = _cfg(tmp_path)
    Path(cfg.armies_path).write_text(_json.dumps(_named()[1:]), encoding="utf-8")   # no D1

    def propose(digest, profile, instruction=None, history=None):
        return {"pawn_moves": [{"op": "swap", "army_a": "C", "pawn_a": 3305,
                                "army_b": "B", "pawn_b": 3201}]}
    out = handle_chat(cfg, "Tráo 1 lính IMP từ đội D1 với lính cuối Đội 1", history=[],
                      propose=propose)
    assert out["pawn_moves"] == [] and any("Không có đội tên D1" in n for n in out["notices"])


# ---- 2026-10-03: 'Thay 1 IMP cuối Đội 5 thành 1 Thợ Săn' — the player names ONE army; the brain
# invented the partner ('Đội 1 không có lính loại 3304'). The hands find who holds the type. ----
def _swap(a, pa, b, pb, **kw):
    return {"op": "swap", "army_a": a, "pawn_a": pa, "army_b": b, "pawn_b": pb, "count": 1,
            "pos_a": "last", **kw}


def test_a_swap_without_a_partner_takes_the_pawn_from_the_army_that_holds_the_type():
    out, notes = sanitize_pawn_moves([_swap("B", 3305, None, 3206)], _armies())
    assert out and out[0]["b"] == "A" and out[0]["pawn_b"] == 3206 and notes == []


def test_a_partner_that_lacks_the_type_is_replaced_by_one_that_has_it_and_it_is_said():
    out, notes = sanitize_pawn_moves([_swap("B", 3305, "C", 3206)], _armies(),
                                     pawn_names={3206: "Lính Rìu Khiên"})
    assert out and out[0]["b"] == "A"
    assert any("Đội 3" in n and "Lính Rìu Khiên" in n and "Đội 1" in n for n in notes)


def test_no_army_holds_an_unlocked_type_proposes_recruiting_a_locked_one_is_refused_by_name():
    out, notes = sanitize_pawn_moves([_swap("B", 3305, "A", 3304)], _armies(),
                                     pawn_names={3304: "Thợ Săn"})
    assert out and out[0]["op"] == "recruit_swap" and notes == []        # unlock unknown: allowed
    out, notes = sanitize_pawn_moves([_swap("B", 3305, "A", 3304)], _armies(),
                                     pawn_names={3304: "Thợ Săn"}, unlocked={3305})
    assert out == [] and len(notes) == 1 and "Thợ Săn" in notes[0] and "mở khoá" in notes[0]
    assert "3304" not in notes[0]
