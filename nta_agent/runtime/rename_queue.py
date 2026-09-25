"""Durable army-rename queue: a rename waits until its army is idle, then is sent with
the army's CURRENT cell index; transient refusals retry, permanent ones are dropped.

Why: renames were one-shot commands. Live 2026-09-25 three of them failed at once —
500036 (army in battle) and 500011 ('army not found': a marching army's index had
changed) — and nothing retried, so the player's names silently never appeared.
The queue lives in a small JSON file so pending renames survive an agent restart.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from nta_agent.execution.army_health import is_idle

_ECODE = re.compile(r"ecode\.(\d+)")
# busy / moved / slot races: try again later. Anything else (e.g. 500061 name
# already used, bad name) won't fix itself -> drop and report.
TRANSIENT = {"500036", "500011", "500020", "500000"}


class RenameQueue:
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

    def add(self, uid: str, name: str) -> None:
        d = self.pending()
        d[str(uid)] = {"name": str(name), "tries": 0, "wait": 0, "missing": 0}
        self._save(d)

    # ---- work ----------------------------------------------------------- #
    def process(self, actions, on_event) -> None:
        d = self.pending()
        if not d:
            return
        by_uid = {str(a.get("uid")): a for a in (actions.get_player_armys() or [])}
        for uid, job in list(d.items()):
            name = job.get("name", "")
            army = by_uid.get(uid)
            if army is None:
                job["missing"] = job.get("missing", 0) + 1
                if job["missing"] >= self.give_up_missing:
                    del d[uid]
                    on_event("rename_failed", {"uid": uid, "name": name,
                                               "reason": "đội không còn tồn tại"})
                continue
            if army.get("name") == name:
                del d[uid]
                continue
            if job.get("wait", 0) > 0:
                job["wait"] -= 1
                continue
            if not is_idle(army):
                continue  # fighting/marching/recruiting: the server would refuse
            try:
                actions.rename_army(int(army.get("index", 0) or 0), uid, name)
            except Exception as e:
                m = _ECODE.search(str(e))
                code = m.group(1) if m else ""
                job["tries"] = job.get("tries", 0) + 1
                if code in TRANSIENT and job["tries"] < self.max_tries:
                    job["wait"] = self.retry_ticks
                else:
                    del d[uid]
                    on_event("rename_failed", {"uid": uid, "name": name,
                                               "error": str(e)[:120]})
                continue
            del d[uid]
            on_event("rename_done", {"uid": uid, "name": name})
        self._save(d)
