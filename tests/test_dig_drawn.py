"""Dig along a path the PLAYER draws: evaluate (per-cell verdicts, nothing sent) -> player
edits and re-evaluates -> confirm the path -> agent proposes Cứ Điểm -> player edits them ->
confirm the plan -> the agent digs EXACTLY that path (waits at a cell it cannot take, never
detours). The draft lives beside a running dig and replaces it only on the final confirm."""
from __future__ import annotations

import json

from nta_agent.execution.predictors.battle import BattlePrediction
from nta_agent.runtime import fort_queue
from tests.test_dig_service import I, World, _owned_block, _pred, _req, _state, _svc


def _line(x0, x1, y=10):
    return [I(x, y) for x in range(x0, x1 + 1)]


def _draft(svc):
    return json.loads((svc.cfg.dig_state_path).read_text())["draft"]


def _evaluate(tmp, svc, seq, path, scan=None, **kw):
    _req(tmp, seq, "evaluate", path=path, **kw)
    svc.tick(_state())
    return _draft(svc)


def test_evaluate_costs_each_cell_and_sends_nothing(tmp_path):
    svc, _ = _svc(tmp_path, {"owned": _owned_block()})
    d = _evaluate(tmp_path, svc, 1, _line(12, 16))
    assert d["state"] == "evaluated" and d["errors"] == [] and d["hard"] == []
    assert d["cells"] == 5 and d["path"][0] == [12, 10] and d["path"][-1] == [16, 10]
    assert d["total_s"] == 5 * (60.0 + 10.0) and d["stamina"] == 10
    assert svc.actions.calls == []
    assert svc.next_target() is None            # a draft is not a dig


def test_owned_cells_in_the_drawing_are_skipped(tmp_path):
    svc, _ = _svc(tmp_path, {"owned": _owned_block() | {I(12, 10)}})
    d = _evaluate(tmp_path, svc, 1, _line(12, 14))
    assert d["errors"] == [] and d["cells"] == 2 and d["path"][0] == [13, 10]


def test_errors_say_which_cell_and_why(tmp_path):
    scan = {"owned": _owned_block(), "enemy": {I(30, 30)}}
    svc, _ = _svc(tmp_path, scan, world=World({I(13, 10)}))
    d = _evaluate(tmp_path, svc, 1, [I(12, 10), I(13, 10), I(14, 10)])
    assert [(e["xy"], e["why"]) for e in d["errors"]] == [([13, 10], "terrain")]
    # a gap (not touching our land or the cells drawn so far)
    d = _evaluate(tmp_path, svc, 2, [I(12, 10), I(15, 10)])
    assert [(e["xy"], e["why"]) for e in d["errors"]] == [([15, 10], "not_connected")]
    # somebody else's land, and too close to an enemy
    scan["enemy"] = {I(12, 10)}
    d = _evaluate(tmp_path, svc, 3, [I(12, 10)])
    assert d["errors"][0]["why"] == "taken"
    scan["enemy"] = {I(14, 12)}
    svc.world().walls = set()
    d = _evaluate(tmp_path, svc, 4, _line(12, 14), buffer=2)
    assert [e["why"] for e in d["errors"]] == ["enemy_near"] and d["errors"][0]["xy"] == [14, 10]


def test_hard_cells_are_marked_with_the_loss_that_would_take_them(tmp_path):
    def hard_at_dist4(st):
        def predict(idx, land_id, dist):
            if dist == 4:
                return BattlePrediction(win=True, my_power=1, enemy_power=1, ratio=1,
                                        loss_percent=35, loss_lv=0, duration_s=10.0)
            return _pred()
        return predict, 60
    svc, _ = _svc(tmp_path, {"owned": _owned_block()}, max_loss=20) \
        if False else _svc(tmp_path, {"owned": _owned_block()})
    svc._predict_factory = hard_at_dist4
    d = _evaluate(tmp_path, svc, 1, _line(12, 16))
    assert d["hard"] == [[15, 10]] and d["hard_loss"] == [35.0] and d["need_loss"] == 35.0
    assert d["cells"] == 5


def test_confirm_path_proposes_forts_and_the_player_edits_them(tmp_path):
    svc, _ = _svc(tmp_path, {"owned": _owned_block()})
    _evaluate(tmp_path, svc, 1, _line(12, 32))
    _req(tmp_path, 2, "confirm_path")
    svc.tick(_state())
    d = _draft(svc)
    assert d["state"] == "forts_proposed" and d["fort_idx"] and set(d["fort_idx"]) <= set(
        _line(12, 32))
    assert len(d["forts"]) == len(d["fort_idx"])
    # the player removes them all and adds one of his own (only path cells are accepted)
    _req(tmp_path, 3, "set_forts", forts=[I(20, 10), I(20, 12)])
    svc.tick(_state())
    d = _draft(svc)
    assert d["fort_idx"] == [I(20, 10)] and d["forts"] == [[20, 10]]


def test_confirm_path_refuses_a_drawing_with_errors(tmp_path):
    svc, _ = _svc(tmp_path, {"owned": _owned_block()}, world=World({I(13, 10)}))
    _evaluate(tmp_path, svc, 1, _line(12, 14))
    _req(tmp_path, 2, "confirm_path")
    svc.tick(_state())
    assert _draft(svc)["state"] == "evaluated"


def test_editing_the_path_goes_back_to_evaluated_and_drops_the_forts(tmp_path):
    svc, _ = _svc(tmp_path, {"owned": _owned_block()})
    _evaluate(tmp_path, svc, 1, _line(12, 32))
    _req(tmp_path, 2, "confirm_path")
    svc.tick(_state())
    d = _evaluate(tmp_path, svc, 3, _line(12, 20))
    assert d["state"] == "evaluated" and d["fort_idx"] == []


def test_final_confirm_digs_exactly_the_drawn_path_in_order(tmp_path):
    scan = {"owned": _owned_block()}
    svc, _clock = _svc(tmp_path, scan)
    path = [I(12, 10), I(12, 11), I(13, 11), I(14, 11)]      # an L-shaped detour, not the shortest
    _evaluate(tmp_path, svc, 1, path)
    _req(tmp_path, 2, "confirm_path")
    svc.tick(_state())
    _req(tmp_path, 3, "confirm")
    svc.tick(_state())
    assert svc.dig["state"] == "active" and svc.dig["mode"] == "drawn"
    assert svc.draft is None and svc.next_target() == I(12, 10)
    scan["owned"] = _owned_block() | {I(12, 10)}
    svc.tick(_state(land=2))
    assert svc.next_target() == I(12, 11)           # follows the drawing, not a shortcut
    scan["owned"] |= {I(12, 11), I(13, 11), I(14, 11)}
    svc.tick(_state(land=5))
    assert svc.dig["state"] == "done" and svc.next_target() is None


def test_a_cell_it_cannot_take_waits_and_never_detours(tmp_path):
    scan = {"owned": _owned_block()}
    svc, clock = _svc(tmp_path, scan)
    _evaluate(tmp_path, svc, 1, _line(12, 15))
    _req(tmp_path, 2, "confirm_path")
    svc.tick(_state())
    _req(tmp_path, 3, "confirm")
    svc.tick(_state())
    scan["owned"] = _owned_block() | {I(12, 10)}
    svc.tick(_state(land=2))
    assert svc.next_target() == I(13, 10)
    svc.report_hard(I(13, 10))                      # OccupyCell lost against it
    svc.tick(_state(land=2))
    assert svc.dig["state"] == "waiting" and svc.next_target() is None
    assert svc.dig["reason"] == "blocked_by_hard" and svc.dig["hard"][0] == [13, 10]
    assert svc.dig["path"][0] == [13, 10]           # same drawing, no detour planned
    clock.t += 700                                  # the mark expires -> try again
    svc.tick(_state(land=2))
    assert svc.dig["state"] == "active" and svc.next_target() == I(13, 10)


def test_a_cell_taken_by_someone_else_waits_for_the_player(tmp_path):
    scan = {"owned": _owned_block()}
    svc, clock = _svc(tmp_path, scan)
    _evaluate(tmp_path, svc, 1, _line(12, 15))
    _req(tmp_path, 2, "confirm_path")
    svc.tick(_state())
    _req(tmp_path, 3, "confirm")
    svc.tick(_state())
    scan["enemy"] = {I(14, 10)}
    clock.t += 61
    svc.tick(_state())
    assert svc.dig["state"] == "waiting" and svc.dig["reason"] == "path_taken"
    assert svc.next_target() is None and svc.dig["target"] == I(15, 10)   # never retargeted


def test_drawn_forts_are_queued_once_their_cell_is_ours(tmp_path):
    scan = {"owned": _owned_block()}
    svc, _clock = _svc(tmp_path, scan)
    _evaluate(tmp_path, svc, 1, _line(12, 24))
    _req(tmp_path, 2, "confirm_path")
    svc.tick(_state())
    _req(tmp_path, 3, "set_forts", forts=[I(18, 10)])
    svc.tick(_state())
    _req(tmp_path, 4, "confirm")
    svc.tick(_state())
    scan["owned"] = _owned_block() | {I(x, 10) for x in range(12, 19)}
    svc.tick(_state(land=8))
    assert fort_queue.load(tmp_path / "pending_forts.json") == [I(18, 10)]


def test_a_draft_does_not_disturb_a_running_dig_until_confirmed(tmp_path):
    scan = {"owned": _owned_block()}
    svc, _ = _svc(tmp_path, scan)
    for seq, p in enumerate([_line(12, 14)], start=1):
        _evaluate(tmp_path, svc, seq, p)
    _req(tmp_path, 2, "confirm_path")
    svc.tick(_state())
    _req(tmp_path, 3, "confirm")
    svc.tick(_state())
    assert svc.next_target() == I(12, 10)
    d = _evaluate(tmp_path, svc, 4, _line(12, 20))       # redraw while digging
    assert d["state"] == "evaluated" and svc.next_target() == I(12, 10)
    assert svc.dig["state"] == "active"
    _req(tmp_path, 5, "cancel_draft")
    svc.tick(_state())
    assert svc.draft is None and svc.dig["state"] == "active"
    saved = json.loads(svc.cfg.dig_state_path.read_text())
    assert "draft" not in saved and saved["state"] == "active"


def test_a_suggestion_preview_is_dropped_when_the_player_edits_it(tmp_path):
    svc, _ = _svc(tmp_path, {"owned": _owned_block()})
    _req(tmp_path, 1, "request", index=I(16, 10))
    svc.tick(_state())
    assert svc.dig["state"] == "preview"
    d = _evaluate(tmp_path, svc, 2, [I(x, 10) for x in range(12, 17)])
    assert d["state"] == "evaluated" and svc.dig.get("state") in (None, "idle")


def test_draft_survives_an_agent_restart(tmp_path):
    scan = {"owned": _owned_block()}
    svc, _ = _svc(tmp_path, scan)
    _evaluate(tmp_path, svc, 1, _line(12, 14))
    svc2, _ = _svc(tmp_path, scan)
    assert svc2.draft and svc2.draft["state"] == "evaluated"
