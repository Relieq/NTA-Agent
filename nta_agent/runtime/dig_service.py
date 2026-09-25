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
        self._hard: dict[int, float] = {}      # cell -> reported-unwinnable time
        self._cost: CellCost | None = None
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
        _write(self.cfg.dig_state_path, self.dig)

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
        self._last_plan = self._clock()
        main = int(getattr(state, "main_city_index", 0) or 0)
        uid = str(getattr(getattr(state, "user", None), "uid", "") or "")
        target = int(self.dig["target"])
        if not main or not uid:
            return
        focus = self._focus_chunks(main, target)
        m = self._scan(self.actions, main, uid, map_width=W, focus=focus)
        owned = set(m.get("owned") or ())
        others = set(m.get("enemy_cells") or ()) | set((m.get("enemy_cities") or {}).keys())
        # every other player counts as 'enemy' (kept at arm's length): chunks carry
        # no alliance info, so an ally's border is treated with the same caution
        enemy = others
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
        """Chunks covering the box main..target (+margin) — scan_map already fetches
        the main chunk and the ones our border touches."""
        mx, my = main % W, main // W
        tx, ty = target % W, target // W
        x0, x1 = max(0, min(mx, tx) - self.margin), min(W - 1, max(mx, tx) + self.margin)
        y0, y1 = max(0, min(my, ty) - self.margin), min(W - 1, max(my, ty) + self.margin)
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
                self.dig["group"] = got[3] if len(got) > 3 else None
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
