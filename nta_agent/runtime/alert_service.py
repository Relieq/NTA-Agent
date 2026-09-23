"""Early-warning service: capture + incoming hostile marches + approach -> alerts.json.

Runs each tick (cheap). Every ``poll_every`` ticks it resyncs the world-march view
from ``HD_GetMarchs`` (world ADD/REMOVE_MARCH pushes keep it current in between),
then writes one ``alerts.json`` the dashboard banner and the brain read:

  level: "captured" > "danger" (enemy march on our city/cells) > "warn" (enemy
         massing near the capital, from forts.json approach) > "ok"

It only REPORTS — the agent never counter-attacks another player (agent = assistant);
defending the capital is the player's call. Never raises into the loop.
"""
from __future__ import annotations

import json
import sys
import time

from nta_agent.execution.alerts import capture_info, hostile_marches


class AlertService:
    def __init__(self, cfg, actions, on_event=None, poll_every: int = 6, clock=None,
                 map_width: int = 600):
        self.cfg = cfg
        self.actions = actions
        self._on_event = on_event or (lambda *a: None)
        self.poll_every = max(1, int(poll_every))
        self._clock = clock or time.time
        self.mw = map_width
        self._n = 0
        self._seen: set[str] = set()   # hostile march uids already announced

    def _forts(self) -> dict:
        try:
            return json.loads(self.cfg.forts_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def tick(self, state) -> None:
        try:
            now = self._clock()
            if self._n % self.poll_every == 0:
                try:
                    from nta_agent.state import set_world_marches
                    reply = self.actions.get_marches() or {}
                    set_world_marches(state, reply.get("list") or [], now=now)
                except Exception:
                    pass  # keep the push-maintained view
            self._n += 1
            forts = self._forts()
            owned = {int(y) * self.mw + int(x) for x, y in (forts.get("owned_cells") or [])}
            me = getattr(getattr(state, "user", None), "uid", "")
            incoming = hostile_marches(getattr(state, "world_marches", {}) or {}, me, owned,
                                       int(getattr(state, "main_city_index", 0) or 0),
                                       mw=self.mw, now=now)
            for h in incoming:
                if h["uid"] not in self._seen:
                    self._seen.add(h["uid"])
                    self._on_event("incoming_attack", h)
            self._seen &= {h["uid"] for h in incoming}   # forget finished marches
            captured = capture_info(state)
            approach = forts.get("approach") or {}
            level = ("captured" if captured else "danger" if incoming
                     else "warn" if approach.get("near_count") else "ok")
            out = {"level": level, "captured": captured, "incoming": incoming[:20],
                   "approach": approach, "updated_at": now}
            p = self.cfg.alerts_path
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            tmp.replace(p)
        except Exception as e:  # observability must not kill the loop
            sys.stderr.write(f"[alerts] tick failed: {e}\n")
