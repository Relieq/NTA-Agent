"""Throttled territory scan → fort recommendations, written to forts.json.

Runs each tick but does real work only when ``player.landCount`` changes (the
cheap change signal), so most ticks cost zero requests. On a change it decodes
the owned cells (Tier B chunks) and computes deterministic fort recommendations,
then writes ``forts.json`` for the dashboard. Never blocks or kills the loop.
"""
from __future__ import annotations

import json
import sys

from nta_agent.execution.fort_advisor import recommend_forts
from nta_agent.execution.territory import scan_owned

FORT_BUILD_ID = 2102  # Cứ Điểm


class FortService:
    def __init__(self, cfg, actions, on_event=None, scan=None,
                 recommend=None, max_count_fn=None, map_width=600, radius=6):
        self.cfg = cfg
        self.actions = actions
        self._on_event = on_event or (lambda *a: None)
        self._scan = scan or scan_owned
        self._recommend = recommend or recommend_forts
        self._max_count_fn = max_count_fn
        self.map_width = map_width
        self.radius = radius
        self._last_land = None

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
            if land is not None and land == self._last_land:
                return  # no new territory -> no fetch
            self._last_land = land

            main = int(state.main_city_index or player.get("mainCityIndex", 0) or 0)
            uid = str(getattr(getattr(state, "user", None), "uid", "") or "")
            if not main or not uid:
                return

            owned, _cities = self._scan(self.actions, main, uid, map_width=self.map_width)

            fort_indices = [int(f.get("index", 0)) for f in
                            (player.get("fortAutoSupports") or []) if isinstance(f, dict)]
            slots = max(0, self._max_forts() - len(fort_indices))
            recs = self._recommend(main, owned, forts=fort_indices,
                                   map_width=self.map_width, max_forts=slots,
                                   radius=self.radius) if slots else []

            payload = {"owned_count": len(owned), "recommendations": recs}
            path = self.cfg.forts_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            self._on_event("fort_scan", {"owned": len(owned), "recs": len(recs)})
        except Exception as e:  # never kill the loop
            sys.stderr.write(f"[fort] tick failed: {e}\n")
