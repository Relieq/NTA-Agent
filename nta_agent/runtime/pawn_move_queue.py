"""Durable queue for the player-confirmed pawn rearrangements (swap / move / reorder).

A job waits until every army it touches is idle and in the same cell (the server refuses
otherwise), is sent a few pawns per tick, and is dropped on a permanent refusal. It lives
in a small JSON file so pending jobs survive an agent restart (like the dismiss queue).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from nta_agent.execution.army_health import is_idle
from nta_agent.execution.pawn_moves import reorder_swaps

_ECODE = re.compile(r"ecode\.(\d+)")
TRANSIENT = {"500036", "500011", "500020", "500000", "500080"}   # busy / moved: later
PER_TICK = 4


def _key(op: dict) -> str:
    return "|".join([op["op"]] + sorted(
        str(op.get(k)) for k in ("a", "b", "from", "to", "army") if op.get(k)))


class PawnMoveQueue:
    def __init__(self, path, retry_ticks: int = 6, give_up_missing: int = 20,
                 max_tries: int = 30):
        self.path = Path(path)
        self.retry_ticks = retry_ticks
        self.give_up_missing = give_up_missing
        self.max_tries = max_tries

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

    def add(self, op: dict) -> None:
        d = self.pending()
        d[_key(op)] = {**op, "tries": 0, "wait": 0, "missing": 0}
        self._save(d)

    @staticmethod
    def _armies_of(job: dict) -> list:
        if job["op"] == "swap":
            return [job["a"], job["b"]]
        if job["op"] == "move":
            return [job["from"]] + ([] if job["to"] == "new" else [job["to"]])
        return [job["army"]]

    def process(self, actions, on_event) -> None:
        d = self.pending()
        if not d:
            return
        by_uid = {str(a.get("uid")): a for a in (actions.get_player_armys() or [])}
        for key, job in list(d.items()):
            armies = [by_uid.get(u) for u in self._armies_of(job)]
            if any(a is None for a in armies):
                job["missing"] = job.get("missing", 0) + 1
                if job["missing"] >= self.give_up_missing:
                    del d[key]
                    on_event("pawn_move_failed",
                             {"op": job["op"], "reason": "đội không còn tồn tại"})
                continue
            if job.get("wait", 0) > 0:
                job["wait"] -= 1
                continue
            if not all(is_idle(a) for a in armies):
                continue
            if len({a.get("index") for a in armies}) > 1:
                continue  # not in the same cell (yet)
            try:
                finished = self._run(actions, job, by_uid)
            except Exception as e:
                m = _ECODE.search(str(e))
                job["tries"] = job.get("tries", 0) + 1
                if (m.group(1) if m else "") in TRANSIENT and job["tries"] < self.max_tries:
                    job["wait"] = self.retry_ticks
                else:
                    d.pop(key, None)
                    on_event("pawn_move_failed", {"op": job["op"], "error": str(e)[:120]})
                continue
            if finished:
                del d[key]
            on_event("pawn_move_done" if finished else "pawn_move_progress", {"op": job["op"]})
        self._save(d)

    def _run(self, actions, job: dict, by_uid: dict) -> bool:
        op = job["op"]
        if op == "swap":
            a, b = by_uid[job["a"]], by_uid[job["b"]]
            ha = {str(p.get("uid")) for p in a.get("pawns") or []}
            hb = {str(p.get("uid")) for p in b.get("pawns") or []}
            todo = [p for p in job["pairs"] if p[0] in ha and p[1] in hb]
            for pa, pb in todo[:PER_TICK]:
                actions.exchange_pawn_army(job["index"], job["a"], pa, pb, army_uid2=job["b"])
            job["pairs"] = todo[PER_TICK:]
            return not job["pairs"]
        if op == "reorder":
            for u1, u2 in reorder_swaps(by_uid[job["army"]], job["order"]):
                actions.exchange_pawn_army(job["index"], job["army"], u1, u2)
            return True
        src = by_uid[job["from"]]
        here = {str(p.get("uid")) for p in src.get("pawns") or []}
        todo = [p for p in job["pawn_uids"] if p in here]
        sent = 0
        while todo and sent < PER_TICK:
            puid = todo[0]
            if job["to"] == "new":
                before = set(by_uid)
                actions.change_pawn_army(job["index"], job["from"], puid, "",
                                         is_new_create=True, army_name="Đội mới")
                fresh = {str(a.get("uid")): a for a in (actions.get_player_armys() or [])}
                made = [u for u, a in fresh.items()
                        if u not in before and a.get("index") == job["index"]]
                if not made:
                    raise RuntimeError("không thấy đội mới vừa tạo")
                job["to"] = made[0]
            else:
                actions.change_pawn_army(job["index"], job["from"], puid, job["to"])
            todo.pop(0)
            sent += 1
        job["pawn_uids"] = todo
        return not todo
