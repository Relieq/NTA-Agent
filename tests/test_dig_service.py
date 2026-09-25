"""DigService: preview (no game command) -> confirm -> active/waiting/done, retarget,
fort queueing, cancel, and next_target for OccupyCell."""
from __future__ import annotations

import json
from types import SimpleNamespace

from nta_agent.execution.predictors.battle import BattlePrediction
from nta_agent.runtime import fort_queue
from nta_agent.runtime.dig_service import DigService

W = 600


def I(x, y):
    return y * W + x


class World:
    name = "maps_15"

    def __init__(self, walls=()):
        self.walls = set(walls)

    def detect(self, owned):
        return self.name

    def passable(self, i):
        return i not in self.walls

    def land_id(self, i):
        return 301

    def lv(self, i):
        return 1


class Cfg:
    def __init__(self, tmp):
        self.dig_request_path = tmp / "dig_request.json"
        self.dig_state_path = tmp / "dig.json"
        self.pending_forts_path = tmp / "pending_forts.json"


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


class Actions:
    """Records any call: a preview must never touch the game."""
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def f(*a, **k):
            self.calls.append(name)
        return f


MAIN = I(10, 10)


def _state(land=1):
    return SimpleNamespace(main_city_index=MAIN, user=SimpleNamespace(uid="me"),
                           raw={"player": {"landCount": land}})


def _pred(*_a):
    return BattlePrediction(win=True, my_power=1, enemy_power=1, ratio=1,
                            loss_percent=0, loss_lv=0, duration_s=10.0)


def _svc(tmp, scan_state, **kw):
    clock = Clock()

    def scan(actions, main, uid, map_width=600, focus=None):
        scan_state["calls"] = scan_state.get("calls", 0) + 1
        return {"owned": set(scan_state["owned"]), "enemy_cells": set(scan_state.get("enemy", ())),
                "enemy_cities": {}, "cities": {}}
    svc = DigService(Cfg(tmp), Actions(), world=kw.pop("world", World()), scan=scan,
                     predict_factory=lambda st: (_pred, 60), clock=clock,
                     stamina_fn=lambda i: 2, **kw)
    return svc, clock


def _req(tmp, seq, op, **kw):
    (tmp / "dig_request.json").write_text(json.dumps({"seq": seq, "op": op, **kw}))


def _owned_block():
    return {MAIN, MAIN + 1, MAIN + W, MAIN + W + 1}


def test_preview_plans_without_sending_game_commands(tmp_path):
    scan = {"owned": _owned_block()}
    svc, _ = _svc(tmp_path, scan)
    _req(tmp_path, 1, "request", index=I(16, 10), buffer=2)
    svc.tick(_state())
    d = json.loads((tmp_path / "dig.json").read_text())
    assert d["state"] == "preview" and d["reason"] == "ok"
    assert d["cells"] == 5 and d["path"][0] == [12, 10] and d["path"][-1] == [16, 10]
    assert d["total_s"] == 5 * (60.0 + 10.0)
    assert d["stamina"] == 10
    assert svc.actions.calls == []          # nothing sent to the game
    assert svc.next_target() is None        # not active until confirmed
    svc.tick(_state())                       # same seq -> no re-plan
    assert scan["calls"] == 1


def test_confirm_activates_and_next_target_follows_the_frontier(tmp_path):
    scan = {"owned": _owned_block()}
    svc, _ = _svc(tmp_path, scan)
    _req(tmp_path, 1, "request", index=I(16, 10))
    svc.tick(_state())
    _req(tmp_path, 2, "confirm")
    svc.tick(_state())
    assert svc.dig["state"] == "active"
    assert svc.next_target() == I(12, 10)
    # we took (12,10): landCount changes -> immediate re-plan, next moves on
    scan["owned"] = _owned_block() | {I(12, 10)}
    svc.tick(_state(land=2))
    assert svc.next_target() == I(13, 10)
    # target owned -> done
    scan["owned"] |= {I(13, 10), I(14, 10), I(15, 10), I(16, 10)}
    svc.tick(_state(land=5))
    assert svc.dig["state"] == "done" and svc.next_target() is None


def test_lost_target_is_retargeted_to_nearest_safe_cell(tmp_path):
    scan = {"owned": _owned_block()}
    svc, clock = _svc(tmp_path, scan)
    _req(tmp_path, 1, "request", index=I(20, 10), buffer=1)
    svc.tick(_state())
    _req(tmp_path, 2, "confirm")
    svc.tick(_state())
    events = []
    svc._on_event = lambda k, d=None: events.append((k, d))
    scan["enemy"] = {I(20, 10)}                 # somebody grabbed the target
    clock.t += 61
    svc.tick(_state())
    assert svc.dig["state"] == "active"
    new = svc.dig["target"]
    assert new != I(20, 10)
    assert abs(new % W - 20) + abs(new // W - 10) == 2  # just outside buffer 1
    assert any(k == "dig_retarget" for k, _ in events)
    assert svc.dig["orig_target"] == I(20, 10)


def test_unwinnable_cell_on_the_only_route_waits(tmp_path):
    walls = {I(x, y) for x in range(5, 25) for y in range(5, 20) if y != 10}
    walls -= _owned_block()
    scan = {"owned": _owned_block()}
    svc, clock = _svc(tmp_path, scan, world=World(walls))
    _req(tmp_path, 1, "request", index=I(16, 10))
    svc.tick(_state())
    _req(tmp_path, 2, "confirm")
    svc.tick(_state())
    assert svc.next_target() == I(12, 10)
    svc.report_hard(I(14, 10))                  # OccupyCell: can't win it now
    svc.tick(_state())
    assert svc.dig["state"] == "waiting" and svc.next_target() is None
    assert svc.dig["hard"] == [[14, 10]]
    # after the hard mark expires and the wait retry is due -> active again
    clock.t += 700
    svc.tick(_state())
    assert svc.dig["state"] == "active"


def test_forts_are_queued_once_when_their_cell_is_ours(tmp_path):
    scan = {"owned": _owned_block()}
    svc, clock = _svc(tmp_path, scan)
    _req(tmp_path, 1, "request", index=I(30, 10))
    svc.tick(_state())
    fort = svc.dig["fort_idx"][0]
    _req(tmp_path, 2, "confirm")
    svc.tick(_state())
    assert fort_queue.load(tmp_path / "pending_forts.json") == []
    scan["owned"] = _owned_block() | {I(x, 10) for x in range(12, fort % W + 1)}
    svc.tick(_state(land=9))
    assert fort_queue.load(tmp_path / "pending_forts.json") == [fort]
    fort_queue.remove(tmp_path / "pending_forts.json", fort)   # FortBuild built it
    clock.t += 61
    svc.tick(_state(land=9))
    assert fort_queue.load(tmp_path / "pending_forts.json") == []  # not re-queued


def test_cancel_stops_the_dig(tmp_path):
    scan = {"owned": _owned_block()}
    svc, _ = _svc(tmp_path, scan)
    _req(tmp_path, 1, "request", index=I(16, 10))
    svc.tick(_state())
    _req(tmp_path, 2, "confirm")
    svc.tick(_state())
    _req(tmp_path, 3, "cancel")
    svc.tick(_state())
    assert svc.dig["state"] == "cancelled" and svc.next_target() is None


def test_active_dig_resumes_after_restart(tmp_path):
    scan = {"owned": _owned_block()}
    svc, _ = _svc(tmp_path, scan)
    _req(tmp_path, 1, "request", index=I(16, 10))
    svc.tick(_state())
    _req(tmp_path, 2, "confirm")
    svc.tick(_state())
    svc2, _ = _svc(tmp_path, scan)              # agent restarted
    assert svc2.next_target() == I(12, 10)
    svc2.tick(_state())
    assert svc2.dig["state"] == "active"


def test_preview_tells_the_loss_needed_to_dig_now(tmp_path):
    walls = {I(x, y) for x in range(5, 25) for y in range(5, 20) if y != 10}
    walls -= _owned_block()
    scan = {"owned": _owned_block()}
    clock = Clock()

    def lossy(idx, land_id, dist):   # every cell: a win that costs 3%
        return BattlePrediction(win=True, my_power=1, enemy_power=1, ratio=1,
                                loss_percent=3.0, loss_lv=1, duration_s=10.0)

    def scan_fn(actions, main, uid, map_width=600, focus=None):
        return {"owned": set(scan["owned"]), "enemy_cells": set(), "enemy_cities": {}}
    svc = DigService(Cfg(tmp_path), Actions(), world=World(walls), scan=scan_fn,
                     predict_factory=lambda st: (lossy, 60), clock=clock)
    _req(tmp_path, 1, "request", index=I(14, 10))
    svc.tick(_state())
    assert svc.dig["reason"] == "blocked_by_hard"
    assert svc.dig["need_loss"] == 3.0 and svc.dig["max_loss"] == 0.0
