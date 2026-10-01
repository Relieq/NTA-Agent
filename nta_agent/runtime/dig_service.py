"""Dig a path to a player-chosen cell: preview, then (after confirm) steer OccupyCell.

The dashboard writes ``dig_request.json`` ({seq, op: request|confirm|cancel,
index, buffer}); this service (agent process, every tick) answers in
``dig.json``. States::

    previewing -> preview -> active <-> waiting -> done | failed | cancelled

A preview never sends a game command: it scans the map chunks around
owned+target, costs cells with the sim (``CellCost``) and plans with
``dig_planner``. While active it re-plans when territory changes or every
``replan_every_s``: a lost target is retargeted to the nearest safe free cell,
a path that now must cross an unbeatable cell waits (retry every
``wait_retry_s``), and a Cứ Điểm due on the path is queued once it is ours.
``next_target()`` is the one cell OccupyCell should dig next.

PLAYER-DRAWN path (``mode == "drawn"``): the player draws the cells, the agent only
EVALUATES them (``evaluate`` -> a *draft*: per-cell verdicts, errors, cost), the
player redraws as often as needed, ``confirm_path`` makes the agent propose Cứ Điểm
along it, ``set_forts`` lets the player edit them, and the final ``confirm`` turns
the draft into the live dig. The draft sits beside a running dig and replaces it only
then. A drawn dig follows the drawing exactly: a cell it can't take or that someone
else holds makes it WAIT (never detour, never retarget).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from nta_agent.execution import dig_planner as dp
from nta_agent.execution.dig_cost import CellCost, attr_lv
from nta_agent.execution.mapchunk import chunk_id
from nta_agent.runtime import fort_queue

W = dp.W
LIVE = ("active", "waiting")


class _Superseded(Exception):
    """A newer dashboard op (cancel / new target / replan) arrived mid-plan."""


def _xy(i: int) -> list[int]:
    return [i % W, i // W]


def _read(path) -> dict:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def main_block(main: int) -> list[int]:
    return [main, main + 1, main + W, main + W + 1] if main else []


def dist_to_block(idx: int, main: int) -> int:
    mx, my = main % W, main // W
    x, y = idx % W, idx // W
    return max(mx - x, 0, x - (mx + 1)) + max(my - y, 0, y - (my + 1))


class DigService:
    def __init__(self, cfg, actions, *, world=None, profile=None, on_event=None,
                 scan=None, predict_factory=None, stamina_fn=None, forts_source=None,
                 clock=None, replan_every_s: float = 60.0, wait_retry_s: float = 300.0,
                 hard_ttl_s: float = 600.0, margin: int = 8, penalty_s: float = 30.0,
                 fort_every: int = 7):
        self.cfg = cfg
        self.actions = actions
        self._world = world
        self.profile = profile
        self._on_event = on_event or (lambda *a: None)
        if scan is None:
            from nta_agent.execution.territory import scan_map
            scan = scan_map
        self._scan = scan
        self._predict_factory = predict_factory
        self._stamina_fn = stamina_fn
        self._forts_source = forts_source or list
        self._clock = clock or time.time
        self.replan_every_s = replan_every_s
        self.wait_retry_s = wait_retry_s
        self.hard_ttl_s = hard_ttl_s
        self.margin = margin
        self.penalty_s = penalty_s
        self.fort_every = fort_every
        self.dig = _read(cfg.dig_state_path)   # resume an unfinished dig after a restart
        draft = self.dig.pop("draft", None)    # the path being drawn (not a dig yet)
        self.draft = draft if isinstance(draft, dict) else None
        self._hard: dict[int, float] = {}      # cell -> reported-unwinnable time
        self._cost: CellCost | None = None
        self._group_desc: list = []            # [{name, pawns}] the sim fights with, in order
        self._last_plan = None
        self._last_land = None
        self._dirty = self.dig.get("state") in LIVE
        self.abort_check_every = 10   # cost() calls between request-file checks mid-plan
        if self.dig.get("state") == "previewing":  # died mid-preview: take the request again
            self.dig["seq"] = None

    # ---- inputs from the other side -------------------------------------------------
    def next_target(self) -> int | None:
        """The cell OccupyCell should dig now (None unless a dig is active)."""
        if self.dig.get("state") != "active" or self._pending_op() == "cancel":
            return None  # a cancel the agent hasn't handled yet already stops the dig
        n = self.dig.get("next")
        return int(n) if n is not None else None

    def is_live(self) -> bool:
        """A confirmed dig is on (active or waiting): the dig group is reserved."""
        return self.dig.get("state") in LIVE and self._pending_op() != "cancel"

    def report_hard(self, idx: int) -> None:
        """OccupyCell couldn't win ``idx`` within max_loss with the real defenders:
        treat it as hard for a while and re-plan around it."""
        self._hard[int(idx)] = self._clock()
        self._dirty = True
        self._on_event("dig_hard", {"cell": int(idx), "xy": _xy(int(idx))})

    # ---- helpers ---------------------------------------------------------------------
    def _pending_op(self) -> str | None:
        """The dashboard op waiting for us (a newer seq than the one handled), if any."""
        req = _read(self.cfg.dig_request_path)
        if req.get("seq") is None or req.get("seq") == self.dig.get("seq"):
            return None
        return req.get("op")

    def world(self):
        if self._world is None:
            from nta_agent import paths
            from nta_agent.execution.worldmap import WorldMap
            self._world = WorldMap.load(paths.config_dir())
        return self._world

    def _save(self) -> None:
        self.dig["updated_at"] = self._clock()
        out = dict(self.dig)
        if self.draft:
            out["draft"] = self.draft
        _write(self.cfg.dig_state_path, out)

    def _event(self, kind: str, **detail) -> None:
        self._on_event(kind, detail)

    def _max_loss(self) -> float:
        if self.profile is None:
            return 0.0
        return float((self.profile.occupy or {}).get("max_loss", 0) or 0)

    def _stamina(self, idx: int) -> int:
        if self._stamina_fn is not None:
            return int(self._stamina_fn(idx) or 0)
        return 0

    # ---- the tick --------------------------------------------------------------------
    def reset_for_new_game(self) -> None:
        """A new match: the old dig's cells/armies no longer exist."""
        self.dig = {}
        self.draft = None

    def tick(self, state) -> None:
        try:
            for _ in range(5):  # a plan cut short by a newer op -> handle that op now
                try:
                    self._handle_request(state)
                    break
                except _Superseded:
                    continue
            st = self.dig.get("state")
            if st not in LIVE:
                return
            player = (getattr(state, "raw", None) or {}).get("player", {}) or {}
            land = player.get("landCount")
            now = self._clock()
            every = self.wait_retry_s if st == "waiting" else self.replan_every_s
            if (self._dirty or self._last_plan is None or now - self._last_plan >= every
                    or (land is not None and land != self._last_land)):
                self._last_land = land
                try:
                    self._replan(state)
                except _Superseded:
                    self._dirty = True
                    self._handle_request(state)
        except Exception as e:  # never kill the loop
            sys.stderr.write(f"[dig] tick failed: {e}\n")

    def _handle_request(self, state) -> None:
        req = _read(self.cfg.dig_request_path)
        seq = req.get("seq")
        if seq is None or seq == self.dig.get("seq"):
            return
        op = req.get("op")
        cur = self.dig.get("state")
        if op == "request" and req.get("index") is not None:
            if cur in LIVE:  # one dig at a time: a new pick replaces the running one
                self._event("dig_cancel", target=self.dig.get("target"), why="replaced")
            idx = int(req["index"])
            self.dig = {"seq": seq, "state": "previewing", "target": idx, "orig_target": idx,
                        "target_xy": _xy(idx), "buffer": int(req.get("buffer", 2) or 0),
                        "requested_at": self._clock(), "retargets": []}
            self._save()
            self._cost = None
            self._hard.clear()
            self._plan(state, preview=True)
        elif op == "evaluate":
            if cur in ("preview", "previewing"):  # a suggestion the player now edits
                self.dig = {"seq": seq, "state": "idle"}  # nothing was sent: drop it
            else:
                self.dig["seq"] = seq
            self._evaluate_draft(state, req)
            self._save()
        elif op == "confirm_path":
            self.dig["seq"] = seq
            self._propose_forts(state)
            self._save()
        elif op == "set_forts":
            self.dig["seq"] = seq
            self._set_forts(req.get("forts"))
            self._save()
        elif op == "cancel_draft":
            self.dig["seq"] = seq
            self.draft = None
            self._save()
        elif op == "confirm" and self.draft and self.draft.get("state") == "forts_proposed":
            self._promote_draft(seq)
        elif op == "confirm":
            self.dig["seq"] = seq
            if cur == "preview" and self.dig.get("reason") in ("ok", "blocked_by_hard"):
                self.dig["state"] = "active"
                self.dig["started_at"] = self._clock()
                self.dig["dug"] = 0
                self._dirty = True
                self._event("dig_start", target=self.dig.get("target"),
                            cells=len(self.dig.get("path") or []),
                            total_s=self.dig.get("total_s"))
            self._save()
        elif op == "replan":
            # "Tìm đường khác": plan again from scratch — fresh scan, fresh sims (the
            # generated defenders' gear is re-rolled), no stale hard marks
            self.dig["seq"] = seq
            if cur in ("preview", "active", "waiting", "failed"):
                self._cost = None
                self._hard.clear()
                self._event("dig_replan", target=self.dig.get("target"))
                if cur == "failed":
                    self.dig["state"] = "previewing"
                self._plan(state, preview=cur in ("preview", "failed"))
            else:
                self._save()
        elif op == "cancel":
            self.dig["seq"] = seq
            if cur in LIVE or cur in ("preview", "previewing"):
                self.dig["state"] = "cancelled"
                self._event("dig_cancel", target=self.dig.get("target"), why="user")
            self._save()
        else:
            self.dig["seq"] = seq
            self._save()

    def _replan(self, state) -> None:
        self._dirty = False
        self._plan(state, preview=False)

    # ---- planning --------------------------------------------------------------------
    def _plan(self, state, *, preview: bool) -> None:
        if self.dig.get("mode") == "drawn":
            self._plan_drawn(state)
            return
        self._last_plan = self._clock()
        main = int(getattr(state, "main_city_index", 0) or 0)
        uid = str(getattr(getattr(state, "user", None), "uid", "") or "")
        target = int(self.dig["target"])
        if not main or not uid:
            return
        focus = self._focus_chunks(main, target)
        from nta_agent.execution.alliance import ally_uids
        allies = ally_uids(self.actions, state)
        m = self._scan(self.actions, main, uid, map_width=W, focus=focus,
                       **({"allies": allies} if allies else {}))
        owned = set(m.get("owned") or ())
        # hostile players are kept at arm's length (buffer); alliance members' land is
        # just not ours to dig through (blocked, no buffer)
        enemy = set(m.get("enemy_cells") or ()) | set((m.get("enemy_cities") or {}).keys())
        others = enemy | set(m.get("ally_cells") or ()) | set((m.get("ally_cities") or {}).keys())
        world = self.world()
        if world.name is None:
            world.detect(owned)
        buffer = int(self.dig.get("buffer", 2))
        dig = self.dig

        if target in owned:
            if dig.get("state") in LIVE:
                dig.update(state="done", path=[], next=None, done_at=self._clock())
                self._event("dig_done", target=target, xy=_xy(target))
            else:
                dig.update(state="failed", reason="owned", path=[], next=None)
            self._save()
            return

        # target taken / now too close to an enemy -> nearest safe free cell
        if not dp.target_ok(target, passable=world.passable, others=others,
                            enemy=enemy, buffer=buffer):
            new = dp.retarget(target, owned=owned, passable=world.passable,
                              others=others, enemy=enemy, buffer=buffer)
            if new is None:
                dig.update(state="failed", reason="target_lost", path=[], next=None)
                self._event("dig_failed", target=target, reason="target_lost")
                self._save()
                return
            dig["retargets"] = (dig.get("retargets") or []) + [
                {"from": _xy(target), "to": _xy(new), "at": self._clock()}]
            self._event("dig_retarget", **{"from": _xy(target), "to": _xy(new)})
            target = new
            dig.update(target=new, target_xy=_xy(new))
            if new in owned:
                self._plan(state, preview=preview)
                return

        cost = self._cell_cost(state, main)
        now = self._clock()
        hard = {c for c, t in self._hard.items() if now - t < self.hard_ttl_s}

        calls = {"n": 0}

        def step(i: int):
            calls["n"] += 1
            if calls["n"] % self.abort_check_every == 0 and self._pending_op() not in (None, "confirm"):
                raise _Superseded()
            return None if i in hard else cost.cost(i)

        plan = dp.plan_path(owned, target, step, passable=world.passable, others=others,
                            enemy=enemy, buffer=buffer, penalty_s=self.penalty_s,
                            margin=self.margin)
        # planned forts whose cell we now hold stay planned until queued (the new path
        # only covers unowned cells, so re-placing would forget them) and act as nodes
        queued = set(dig.get("forts_queued") or [])
        carry = [f for f in (dig.get("fort_idx") or []) if f in owned and f not in queued]
        # the protection zone (radius 6 round the city) is already sped up: count
        # from its edge, like one big fort (user 2026-09-25)
        nodes = ([int(f) for f in (self._forts_source() or [])]
                 + fort_queue.load(self.cfg.pending_forts_path) + carry)
        forts = carry + (dp.place_forts(plan.path, nodes, world.lv, every=self.fort_every,
                                        main=main, main_radius=6)
                         if plan.path else [])
        stamina = sum(self._stamina(i) for i in plan.path)
        # what it would take: the loss % each hard cell costs (None = a defeat), so
        # the player can decide to raise occupy.max_loss instead of waiting
        losses = [None if i in hard else cost.hard_loss(i) for i in plan.hard]
        need_loss = (max(losses) if losses and all(x is not None for x in losses) else None)
        dig.update(path=[_xy(i) for i in plan.path], path_idx=plan.path,
                   total_s=round(plan.total_s, 1), cells=len(plan.path), reason=plan.reason,
                   hard=[_xy(i) for i in plan.hard], forts=[_xy(i) for i in forts],
                   hard_loss=losses, need_loss=need_loss, max_loss=self._max_loss(),
                   hard_why=[cost.why.get(i, "reported" if i in hard else "") for i in plan.hard],
                   fort_idx=forts, stamina=stamina, rough=bool(cost.rough),
                   sims=cost.sims, map=world.name, planned_at=now,
                   next=plan.path[0] if plan.path else None)

        if preview:
            dig["state"] = "preview"
            self._event("dig_preview", target=target, reason=plan.reason,
                        cells=len(plan.path), total_s=round(plan.total_s), forts=len(forts))
        elif plan.reason == "ok":
            if dig.get("state") == "waiting":
                self._event("dig_resume", target=target)
            dig["state"] = "active"
            self._queue_forts(owned)
        elif plan.reason == "blocked_by_hard":
            if dig.get("state") != "waiting":
                self._event("dig_wait", target=target, hard=[_xy(i) for i in plan.hard])
            dig["state"] = "waiting"
        else:
            dig["state"] = "failed"
            self._event("dig_failed", target=target, reason=plan.reason)
        self._save()

    def _scan_world(self, state, main: int, uid: str, cells):
        """(owned, enemy, others, ally, world) around ``main`` + the cells of interest.
        Hostile land is kept at arm's length (buffer); alliance land is not ours to dig
        but a cell touching it CAN be attacked (the game allows it), so ``ally`` also
        counts as a place a path may start from."""
        from nta_agent.execution.alliance import ally_uids
        allies = ally_uids(self.actions, state)
        m = self._scan(self.actions, main, uid, map_width=W,
                       focus=self._focus_for(main, cells),
                       **({"allies": allies} if allies else {}))
        owned = set(m.get("owned") or ())
        enemy = set(m.get("enemy_cells") or ()) | set((m.get("enemy_cities") or {}).keys())
        ally = set(m.get("ally_cells") or ()) | set((m.get("ally_cities") or {}).keys())
        others = enemy | ally
        world = self.world()
        if world.name is None:
            world.detect(owned)
        return owned, enemy, others, ally, world

    def _validate_drawing(self, path, owned, enemy, others, world, buffer, ally=()):
        """Walk the drawing in order: (cells to dig, errors). A cell must be occupiable
        land, nobody's, beyond ``buffer`` of any enemy and touch our land, an ally's land
        or a cell drawn before it (an errored cell still counts as drawn, so one gap is
        reported once)."""
        drawn = set(owned) | set(ally)
        cells, errors = [], []
        seen = set()
        for c in path:
            if c in seen or c in owned:
                continue
            seen.add(c)
            why = None
            if not (0 <= c < W * W):
                why = "terrain"
            elif c in others:
                why = "taken"
            elif not any(n in drawn for n in dp.neighbors(c)):
                why = "not_connected"
            elif not world.passable(c):
                why = "terrain"
            elif not dp.target_ok(c, passable=world.passable, others=others, enemy=enemy,
                                  buffer=buffer):
                why = "enemy_near"
            if why:
                errors.append({"xy": _xy(c), "why": why})
            else:
                cells.append(c)
            drawn.add(c)
        return cells, errors

    def _assess(self, cells, state, main: int, hard: set) -> dict:
        """Per-cell cost of a drawing: total seconds, stamina, the hard cells and the
        loss % that would take them. Aborts when a newer dashboard op arrives."""
        cost = self._cell_cost(state, main)
        total = 0.0
        hard_cells = []
        for n, c in enumerate(cells, start=1):
            if n % self.abort_check_every == 0 and self._pending_op() not in (None, "confirm"):
                raise _Superseded()
            s = None if c in hard else cost.cost(c)
            if s is None:
                hard_cells.append(c)
            else:
                total += s
        losses = [None if c in hard else cost.hard_loss(c) for c in hard_cells]
        need = max(losses) if losses and all(x is not None for x in losses) else None
        return {"total_s": round(total, 1), "stamina": sum(self._stamina(c) for c in cells),
                "hard": [_xy(c) for c in hard_cells], "hard_loss": losses, "need_loss": need,
                "max_loss": self._max_loss(), "rough": bool(cost.rough), "sims": cost.sims,
                "hard_why": [cost.why.get(c, "reported" if c in hard else "")
                             for c in hard_cells], "hard_idx": hard_cells}

    def _evaluate_draft(self, state, req: dict) -> None:
        main = int(getattr(state, "main_city_index", 0) or 0)
        uid = str(getattr(getattr(state, "user", None), "uid", "") or "")
        try:
            path = [int(c) for c in (req.get("path") or [])][:300]
        except (TypeError, ValueError):
            path = []
        buffer = int(req.get("buffer", self.dig.get("buffer", 2)) or 0)
        if not main or not uid or not path:
            self.draft = {"state": "failed", "reason": "no_path", "errors": [], "path": [],
                          "fort_idx": [], "forts": []}
            return
        owned, enemy, others, ally, world = self._scan_world(state, main, uid, path)
        cells, errors = self._validate_drawing(path, owned, enemy, others, world, buffer,
                                               ally)
        # every evaluation simulates with the group AS IT IS NOW (its order, its pawn
        # levels): a memo from an earlier evaluation would answer for the old group
        self._cost = None
        now = self._clock()
        hard = {c for c, t in self._hard.items() if now - t < self.hard_ttl_s}
        info = self._assess(cells, state, main, hard)
        info.pop("hard_idx")
        self.draft = {"state": "evaluated", "mode": "drawn", "route": cells,
                      "group": list(self._group_desc),
                      "path": [_xy(c) for c in cells], "cells": len(cells), "errors": errors,
                      "buffer": buffer, "map": world.name, "evaluated_at": now,
                      "fort_idx": [], "forts": [], **info}

    def _propose_forts(self, state) -> None:
        d = self.draft
        if (not d or d.get("state") not in ("evaluated", "forts_proposed") or d.get("errors")
                or not d.get("route")):
            return
        main = int(getattr(state, "main_city_index", 0) or 0)
        nodes = ([int(f) for f in (self._forts_source() or [])]
                 + fort_queue.load(self.cfg.pending_forts_path))
        forts = dp.place_forts(d["route"], nodes, self.world().lv, every=self.fort_every,
                               main=main or None, main_radius=6)
        d.update(state="forts_proposed", fort_idx=forts, forts=[_xy(f) for f in forts])

    def _set_forts(self, forts) -> None:
        d = self.draft
        if not d or d.get("state") != "forts_proposed":
            return
        want = set()
        for f in forts if isinstance(forts, list) else []:
            try:
                want.add(int(f))
            except (TypeError, ValueError):
                continue
        keep = [c for c in d["route"] if c in want]   # only cells ON the path, in order
        d.update(fort_idx=keep, forts=[_xy(f) for f in keep])

    def _promote_draft(self, seq) -> None:
        d = self.draft
        if self.dig.get("state") in LIVE:
            self._event("dig_cancel", target=self.dig.get("target"), why="replaced")
        route = list(d["route"])
        target = route[-1]
        self.dig = {"seq": seq, "mode": "drawn", "state": "active", "target": target,
                    "orig_target": target, "target_xy": _xy(target),
                    "buffer": d.get("buffer", 2), "requested_at": self._clock(),
                    "retargets": [], "route": route, "path": d["path"], "cells": len(route),
                    "fort_idx": list(d["fort_idx"]), "forts": list(d["forts"]),
                    "forts_queued": [], "total_s": d.get("total_s"), "stamina": d.get("stamina"),
                    "hard": d.get("hard") or [], "hard_loss": d.get("hard_loss") or [],
                    "need_loss": d.get("need_loss"), "max_loss": d.get("max_loss"),
                    "rough": d.get("rough"), "map": d.get("map"), "reason": "ok",
                    "started_at": self._clock(), "dug": 0, "next": route[0]}
        self.draft = None
        self._cost = None
        self._hard.clear()
        self._dirty = True
        self._event("dig_start", target=target, cells=len(route), total_s=d.get("total_s"),
                    drawn=True)
        self._save()

    def _plan_drawn(self, state) -> None:
        """Follow the player's drawing: the next cell is the first still-unowned one that
        touches our land. Never replans around anything — a cell it can't take or that
        someone else holds makes the dig wait (and tells the player why)."""
        now = self._clock()
        self._last_plan = now
        main = int(getattr(state, "main_city_index", 0) or 0)
        uid = str(getattr(getattr(state, "user", None), "uid", "") or "")
        dig = self.dig
        route = [int(c) for c in dig.get("route") or []]
        if not main or not uid or not route:
            return
        owned, _enemy, others, ally, world = self._scan_world(state, main, uid, route)
        remaining = [c for c in route if c not in owned]
        if not remaining:
            dig.update(state="done", path=[], next=None, done_at=now)
            self._event("dig_done", target=route[-1], xy=_xy(route[-1]))
            self._save()
            return
        hard = {c for c, t in self._hard.items() if now - t < self.hard_ttl_s}
        info = self._assess(remaining, state, main, hard)
        hard_idx = set(info.pop("hard_idx"))
        taken = [c for c in remaining if c in others]
        frontier = next((c for c in remaining
                         if any(n in owned or n in ally for n in dp.neighbors(c))), None)
        if taken:
            reason, state_name = "path_taken", "waiting"
        elif frontier is None:
            reason, state_name = "disconnected", "waiting"
        elif frontier in hard_idx:
            reason, state_name = "blocked_by_hard", "waiting"
        else:
            reason, state_name = "ok", "active"
        dig.update(info, path=[_xy(c) for c in remaining], cells=len(remaining), reason=reason,
                   planned_at=now, map=world.name, taken=[_xy(c) for c in taken],
                   next=frontier if state_name == "active" else None)
        if state_name == "active":
            if dig.get("state") == "waiting":
                self._event("dig_resume", target=route[-1])
            dig["state"] = "active"
            self._queue_forts(owned)
        else:
            if dig.get("state") != "waiting":
                self._event("dig_wait", target=route[-1], reason=reason,
                            hard=info["hard"][:3])
            dig["state"] = "waiting"
        self._save()

    def _queue_forts(self, owned: set[int]) -> None:
        """Queue each planned Cứ Điểm once, as soon as its cell is ours. The planned
        fort cells stay listed until queued, so a replan that moves them only changes
        which cells are still waiting."""
        queued = set(self.dig.get("forts_queued") or [])
        for f in list(self.dig.get("fort_idx") or []):
            if f in owned and f not in queued:
                fort_queue.add(self.cfg.pending_forts_path, f)
                queued.add(f)
                self._event("dig_fort", cell=f, xy=_xy(f))
        self.dig["forts_queued"] = sorted(queued)

    def _focus_chunks(self, main: int, target: int) -> list[int]:
        return self._focus_for(main, [target])

    def _focus_for(self, main: int, cells) -> list[int]:
        """Chunks covering the box main..cells (+margin) — scan_map already fetches
        the main chunk and the ones our border touches."""
        xs = [main % W] + [c % W for c in cells]
        ys = [main // W] + [c // W for c in cells]
        x0, x1 = max(0, min(xs) - self.margin), min(W - 1, max(xs) + self.margin)
        y0, y1 = max(0, min(ys) - self.margin), min(W - 1, max(ys) + self.margin)
        out = set()
        for y in range(y0, y1 + 1, 50):
            for x in range(x0, x1 + 1, 50):
                out.add(chunk_id(y * W + x, W))
        for x, y in ((x1, y0), (x0, y1), (x1, y1)):
            out.add(chunk_id(y * W + x, W))
        return sorted(out)

    def _cell_cost(self, state, main: int) -> CellCost:
        if self._cost is None:
            predict, speed, verify = (None, 0, None)
            if self._predict_factory is not None:
                got = self._predict_factory(state)
                predict, speed = got[0], got[1]
                verify = got[2] if len(got) > 2 else None
                self._group_desc = (got[3] if len(got) > 3 else None) or []
                self.dig["group"] = self._group_desc
            if predict is None:
                def predict(*_a):
                    raise RuntimeError("no battle predictor")
            self._cost = CellCost(predict, self.world(),
                                  dist_fn=lambda i: dist_to_block(i, main),
                                  max_loss=self._max_loss(), speed=speed, verify=verify)
        return self._cost


def make_stamina_fn(config, world_fn, main_fn):
    """need_stamina of a cell = landAttr[1000*land_lv + attrLv].need_stamina."""
    table = config.table("landAttr") if config is not None else {}

    def fn(idx: int) -> int:
        w = world_fn()
        lv = w.lv(idx)
        row = table.get(1000 * lv + attr_lv(dist_to_block(idx, main_fn()), lv)) \
            or table.get(str(1000 * lv + attr_lv(dist_to_block(idx, main_fn()), lv))) or {}
        return int(row.get("need_stamina", 0) or 0)
    return fn


def make_predict_factory(actions, profile):
    """(state) -> (predict(idx, land_id, dist), march_speed) for the dig group: the
    active formation group (else the biggest army), at full hp, in group order; the
    sim generates each cell's defenders from its landId."""
    def factory(state):
        from nta_agent.execution.occupy_planner import full_hp_pawns
        from nta_agent.execution.predictors.sim_bridge import get_bridge
        from nta_agent.execution.predictors.sim_predictor import SimBattlePredictor
        from nta_agent.execution.profile import active_formation
        try:
            armies = [a for a in (actions.get_player_armys() or []) if a.get("pawns")]
        except Exception:
            armies = []
        grp = [str(x) for x in (active_formation(profile).get("group") or [])] \
            if profile is not None else []
        by_uid = {str(a.get("uid")): a for a in armies}
        group = [by_uid[u] for u in grp if u in by_uid]
        if not group and armies:
            group = [max(armies, key=lambda a: len(a.get("pawns") or []))]
        speeds = [int(a.get("marchSpeed", 0) or 0) for a in group]
        speed = min([s for s in speeds if s > 0], default=0)
        if not group or not get_bridge().available():
            return None, speed
        sim = SimBattlePredictor()
        main = int(getattr(state, "main_city_index", 0) or 0)
        same_cell = [{"uid": a.get("uid"), "name": a.get("name"), "index": main,
                      "pawns": full_hp_pawns(a.get("pawns") or [])} for a in group]

        def predict(idx, land_id, dist):
            return sim.predict_armies(state, same_cell, target_index=idx,
                                      land_id=land_id, distance=dist)

        uid = str(getattr(getattr(state, "user", None), "uid", "") or "")

        def verify(idx):
            # the cell's REAL defenders (read-only get_area) — the generated ones
            # carry random gear, so a borderline verdict must be settled on these
            from nta_agent.execution.occupy_planner import _hostile_pawns
            area = (actions.get_area(int(idx)) or {}).get("data", {}) or {}
            pawns = _hostile_pawns(area, uid)
            if not pawns:
                return None
            hp = area.get("hp") or [0, 0]
            conf = {"armys": [{"index": int(idx), "uid": "npc", "owner": "", "state": 2,
                               "pawns": pawns}], "hp": [hp[0], hp[-1]]}
            return sim.predict_armies(state, same_cell, target_index=int(idx), land_id=0,
                                      distance=dist_to_block(int(idx), main),
                                      enemy_army_conf=conf)
        desc = [{"name": a.get("name"), "pawns": len(a.get("pawns") or [])} for a in group]
        return predict, speed, verify, desc
    return factory
