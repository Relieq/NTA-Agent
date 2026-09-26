"""Throttled territory scan → fort recommendations, written to forts.json.

Runs each tick but does real work only when ``player.landCount`` changes or the
periodic threat rescan is due (``rescan_every_s``), so most ticks cost zero
requests. A scan decodes the owned cells (Tier B chunks), computes deterministic
fort recommendations + threat/approach warnings, then writes ``forts.json`` for
the dashboard and the brain. Never blocks or kills the loop.
"""
from __future__ import annotations

import json
import sys
import time

from nta_agent.execution.fort_advisor import plan_forts, recommend_forts
from nta_agent.execution.territory import scan_map
from nta_agent.execution.threat import approach_summary, detect_incursions
from nta_agent.runtime import fort_decisions

FORT_BUILD_ID = 2102  # Cứ Điểm


class FortService:
    def __init__(self, cfg, actions, on_event=None, scan=None,
                 recommend=None, max_count_fn=None, map_width=600, radius=6,
                 rescan_every_s: float = 180.0, approach_radius: int = 8, clock=None):
        self.cfg = cfg
        self.actions = actions
        self._on_event = on_event or (lambda *a: None)
        self._scan = scan or scan_map
        self._recommend = recommend or recommend_forts
        self._max_count_fn = max_count_fn
        self.map_width = map_width
        self.radius = radius
        # Rescan on a landCount change OR every rescan_every_s: threat detection must
        # never go blind while territory is static (the 2026-09-23 capital siege went
        # unseen for 4h because only a landCount change triggered a rescan).
        self.rescan_every_s = rescan_every_s
        self.approach_radius = approach_radius
        self._clock = clock or time.time
        self._last_land = None
        self._last_scan = None
        self._prev_approach = None

    def _max_forts(self) -> int:
        if self._max_count_fn is not None:
            return int(self._max_count_fn(FORT_BUILD_ID))
        try:
            from nta_agent.data.config import GameConfig
            return int(GameConfig.load().max_count(FORT_BUILD_ID))
        except Exception:
            return 1

    def tick(self, state) -> None:
        try:
            player = (getattr(state, "raw", None) or {}).get("player", {}) or {}
            land = player.get("landCount")
            now = self._clock()
            due = self._last_scan is None or now - self._last_scan >= self.rescan_every_s
            if land is not None and land == self._last_land and not due:
                return  # no new territory and not due for a threat rescan -> no fetch
            self._last_land = land
            self._last_scan = now

            main = int(state.main_city_index or player.get("mainCityIndex", 0) or 0)
            uid = str(getattr(getattr(state, "user", None), "uid", "") or "")
            if not main or not uid:
                return

            m = self._scan(self.actions, main, uid, map_width=self.map_width)
            owned = m["owned"]

            # Detect built forts from the AUTHORITATIVE map-chunk city decode:
            # our cities map is {index: cityType} with cityType 1 = main city,
            # 2 = Cứ Điểm (fort). fortAutoSupports only lists forts with the
            # auto-support toggle registered (empty for a freshly built fort), so
            # relying on it left forts invisible. Union the two to be safe.
            cities = m.get("cities") or {}
            fort_set = {int(i) for i, t in cities.items()
                        if int(t) != 1 and int(i) != main}
            fort_set.update(int(f.get("index", 0)) for f in
                            (player.get("fortAutoSupports") or []) if isinstance(f, dict))
            fort_indices = sorted(fort_set)
            # Forts under construction: sent (so no longer in pending_forts) but not a
            # city yet — without this the dashboard showed nothing for ~30 min.
            building = []
            getq = getattr(self.actions, "get_bt_city_queues", None)
            if callable(getq):
                try:
                    for q in getq() or []:
                        i = int(q.get("index", 0) or 0)
                        if i in owned and i not in fort_set and int(q.get("id", 0) or 0) == FORT_BUILD_ID:
                            building.append({"x": i % self.map_width, "y": i // self.map_width,
                                             "index": i, "id": FORT_BUILD_ID,
                                             "surplus_s": int(q.get("surplusTime", 0) or 0) // 1000,
                                             "need_s": int(q.get("needTime", 0) or 0) // 1000})
                except Exception as e:  # optional: never block the scan
                    sys.stderr.write(f"[fort] build queue read failed: {e}\n")
            decisions = fort_decisions.load(self.cfg.fort_decisions_path)
            enemy = set(m.get("enemy_cells", ())) | set((m.get("enemy_cities") or {}).keys())
            recs, accepted = plan_forts(main, owned, fort_indices, decisions,
                                        self._max_forts(), map_width=self.map_width,
                                        radius=self.radius, enemy=enemy)
            mw = self.map_width
            cells = sorted([c % mw, c // mw] for c in owned)
            accepted_coords = sorted([i % mw, i // mw] for i in accepted)
            rejected_coords = sorted([i % mw, i // mw] for i, d in decisions.items()
                                     if d == "rejected")
            enemy_cells = sorted([i % mw, i // mw] for i in m.get("enemy_cells", ()))
            enemy_cities = [{"x": i % mw, "y": i // mw, "type": t}
                            for i, t in (m.get("enemy_cities") or {}).items()]
            frontier = sorted([i % mw, i // mw] for i in m.get("frontier", ()))
            # Recommended ZONE (user picks one owned cell in it to build a fort) —
            # replaces per-cell rec spam + accept/reject.
            from nta_agent.execution.fort_advisor import fort_zone
            cap = self._max_forts()
            zone = fort_zone(main, owned, fort_indices, map_width=mw,
                             radius=self.radius, enemy=enemy)
            zone_coords = sorted([c % mw, c // mw] for c in zone)
            # P3: detect enemy touching/penetrating our convex-hull territory.
            threat = detect_incursions(owned, m.get("enemy_cells", ()),
                                       m.get("enemy_cities") or {}, main, mw)
            # P1b: enemy massing NEAR the capital (before it touches our hull).
            approach = approach_summary(m.get("enemy_cells", ()), m.get("enemy_cities") or {},
                                        main, mw, radius=self.approach_radius,
                                        prev=self._prev_approach)
            self._prev_approach = approach
            threat["summary"]["approaching"] = approach["approaching"]
            threat["summary"]["near_count"] = approach["near_count"]
            fort_coords = sorted([i % mw, i // mw] for i in fort_indices)
            payload = {"owned_count": len(owned), "owned_cells": cells,
                       "accepted": accepted_coords, "rejected": rejected_coords,
                       "enemy_cells": enemy_cells, "enemy_cities": enemy_cities,
                       "frontier": frontier, "recommendations": recs,
                       "fort_zone": zone_coords,
                       "fort_count": len(fort_indices) + len(building),  # building counts to the cap
                       "building": building,
                       "forts": fort_coords, "fort_cap": cap,
                       "threats": threat["threats"][:50],
                       "threat_summary": threat["summary"],
                       "approach": approach, "scanned_at": now}
            path = self.cfg.forts_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            self._on_event("fort_scan", {"owned": len(owned), "recs": len(recs)})
            if threat["summary"]["count"]:  # P3: surface a defensive alert
                self._on_event("threat_alert", {"kind": "incursion", **threat["summary"]})
            if approach["approaching"]:     # P3b: enemy closing in on the capital
                self._on_event("threat_alert", {"kind": "approach", **approach})
        except Exception as e:  # never kill the loop
            sys.stderr.write(f"[fort] tick failed: {e}\n")
