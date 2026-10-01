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
