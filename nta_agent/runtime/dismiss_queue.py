"""Durable dismissal queue: the player-confirmed dismissals of armies / pawns.

Dismissing is irreversible, so jobs only ever come from a dashboard confirmation. A job
waits until its army is idle (the server refuses otherwise), is then sent with the
army's CURRENT cell index, and is dropped on a permanent refusal. Like the rename queue
it lives in a small JSON file so pending jobs survive an agent restart.

Job: ``{army uid: {"scope": "army" | "pawns", "pawn_uids": [...], "tries", "wait",
"missing"}}`` — one job per army (a newer confirmation replaces the older one).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from nta_agent.execution.army_health import is_idle

_ECODE = re.compile(r"ecode\.(\d+)")
TRANSIENT = {"500036", "500011", "500020", "500000"}   # busy / moved: try again later
PER_TICK = 3                                            # pawns dismissed per tick


class DismissQueue:
    def __init__(self, path, retry_ticks: int = 6, give_up_missing: int = 20,
                 max_tries: int = 30):
        self.path = Path(path)
        self.retry_ticks = retry_ticks
        self.give_up_missing = give_up_missing
        self.max_tries = max_tries

    # ---- storage -------------------------------------------------------- #
    def pending(self) -> dict:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return d if isinstance(d, dict) else {}

    def _save(self, d: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def add(self, uid: str, scope: str, pawn_uids) -> None:
        d = self.pending()
        d[str(uid)] = {"scope": scope, "pawn_uids": [str(p) for p in pawn_uids or []],
                       "tries": 0, "wait": 0, "missing": 0}
        self._save(d)

    # ---- work ----------------------------------------------------------- #
    def process(self, actions, on_event) -> None:
        d = self.pending()
        if not d:
            return
        by_uid = {str(a.get("uid")): a for a in (actions.get_player_armys() or [])}
        for uid, job in list(d.items()):
            army = by_uid.get(uid)
            if army is None:
                job["missing"] = job.get("missing", 0) + 1
                if job["missing"] >= self.give_up_missing:
                    del d[uid]
                    on_event("dismiss_failed", {"uid": uid, "reason": "đội không còn tồn tại"})
                continue
            if job.get("wait", 0) > 0:
                job["wait"] -= 1
                continue
            if not is_idle(army):
                continue  # marching/fighting/recruiting: the server would refuse
            index = int(army.get("index", 0) or 0)
            try:
                if job["scope"] == "army":
                    actions.dismiss_army(index, uid, 0)
                    n = len(army.get("pawns") or [])
                    del d[uid]
                else:
                    here = {str(p.get("uid")) for p in (army.get("pawns") or [])}
                    todo = [p for p in job.get("pawn_uids") or [] if p in here]
                    sent = 0
                    for puid in todo[:PER_TICK]:
                        actions.dismiss_pawn(index, uid, puid)
                        sent += 1
                    job["pawn_uids"] = [p for p in todo[sent:]]
                    n = sent
                    if not job["pawn_uids"]:
                        del d[uid]
            except Exception as e:
                m = _ECODE.search(str(e))
                code = m.group(1) if m else ""
                job["tries"] = job.get("tries", 0) + 1
                if code in TRANSIENT and job["tries"] < self.max_tries:
                    job["wait"] = self.retry_ticks
                else:
                    d.pop(uid, None)
                    on_event("dismiss_failed", {"uid": uid, "name": army.get("name"),
                                                "error": str(e)[:120]})
                continue
            on_event("dismiss_done" if uid not in d else "dismiss_progress",
                     {"uid": uid, "name": army.get("name"), "scope": job["scope"], "count": n})
        self._save(d)
