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
MAX_AGE = 900        # process() calls (~5s each): a job that cannot finish in ~75 min is dropped
MAX_GATHERS = 3      # times the armies are called to the meeting cell before giving up


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
        if job["op"] == "recruit_swap":
            return [job["a"]] + ([job["host"]] if job.get("host") else [])
        if job["op"] == "swap":
            return [job["a"], job["b"]]
        if job["op"] == "move":
            return [job["from"]] + ([] if job["to"] == "new" else [job["to"]])
        return [job["army"]]

    def army_uids(self) -> set:
        """Armies a pending job needs: the other rules must leave them alone, or one of
        them marches off to farm between the gathering and the swap."""
        out: set = set()
        for job in self.pending().values():
            out.update(self._armies_of(job))
        return out

    def _fail(self, d: dict, key: str, job: dict, on_event, **why) -> None:
        d.pop(key, None)
        on_event("pawn_move_failed", {"op": job["op"], **why})

    def process(self, actions, on_event) -> None:
        d = self.pending()
        if not d:
            return
        by_uid = {str(a.get("uid")): a for a in (actions.get_player_armys() or [])}
        for key, job in list(d.items()):
            armies = [by_uid.get(u) for u in self._armies_of(job)]
            job["age"] = job.get("age", 0) + 1
            if job["age"] > MAX_AGE:
                self._fail(d, key, job, on_event, reason="quá lâu không thực hiện được")
                continue
            if job["op"] == "recruit_swap":   # recruits first: the target may be out marching
                if job.get("wait", 0) > 0:
                    job["wait"] -= 1
                    continue
                self._recruit_swap(actions, d, key, job, by_uid, on_event)
                continue
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
                if job.get("meet") is None:
                    continue  # not in the same cell (yet) and nowhere to gather them
                job["gathers"] = job.get("gathers", 0) + 1
                if job["gathers"] > MAX_GATHERS:
                    self._fail(d, key, job, on_event, reason="không gọi được các đội về cùng ô")
                    continue
                try:
                    actions.move_cell_army(
                        [{"uid": str(a["uid"]), "index": int(a.get("index", 0) or 0)}
                         for a in armies if a.get("index") != job["meet"]], int(job["meet"]))
                except Exception as e:
                    m = _ECODE.search(str(e))
                    if (m.group(1) if m else "") in TRANSIENT:
                        job["wait"] = self.retry_ticks
                    else:
                        self._fail(d, key, job, on_event, error=str(e)[:120])
                    continue
                on_event("pawn_move_gather", {"op": job["op"], "to": int(job["meet"])})
                continue
            job["index"] = int(armies[0].get("index", 0) or 0)   # where they are now
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

    def _recruit_swap(self, actions, d: dict, key: str, job: dict, by_uid: dict,
                      on_event) -> None:
        """Stage 1: order the missing pawn(s) (nothing holds the type yet); stage 2: once an
        army holds enough of them, turn the job into the plain swap and let it run."""
        from nta_agent.execution.pawn_moves import _holder, sanitize_pawn_moves
        a = by_uid.get(job["a"])
        if a is None:
            job["missing"] = job.get("missing", 0) + 1
            if job["missing"] >= self.give_up_missing:
                self._fail(d, key, job, on_event, reason="đội không còn tồn tại")
            return
        holder = _holder(list(by_uid.values()), job["a"], job["pawn_b"], a.get("index"))
        have = len([p for p in (holder or {}).get("pawns") or []
                    if int(p.get("id", 0) or 0) == int(job["pawn_b"])]) if holder else 0
        if holder is not None and have >= int(job["count"]):
            spec = {**job["spec"], "army_b": str(holder["uid"])}
            clean, notes = sanitize_pawn_moves([spec], list(by_uid.values()),
                                               cap=int(job.get("cap", 9)),
                                               meet=lambda _ar: job.get("city"))
            d.pop(key, None)
            if clean:
                nk = _key(clean[0])
                d[nk] = {**clean[0], "tries": 0, "wait": 0, "missing": 0,
                         "age": job.get("age", 0)}
                on_event("pawn_move_progress", {"op": "recruit_swap", "note": "đã có lính, đổi ngay"})
            else:
                on_event("pawn_move_failed", {"op": "recruit_swap",
                                              "reason": " ".join(notes)[:160]})
            return
        if job.get("ordered"):
            return    # in training: wait (MAX_AGE bounds it)
        host = self._pick_host(list(by_uid.values()), job)
        try:
            for _ in range(int(job["count"])):
                actions.drill_pawn(actions.building_uid(2004), int(job["pawn_b"]),
                                   army_uid=str(host["uid"]) if host else "",
                                   army_name="" if host else self._new_name(by_uid))
        except Exception as e:
            m = _ECODE.search(str(e))
            code = m.group(1) if m else ""
            job["tries"] = job.get("tries", 0) + 1
            # short of cereal / queue full / busy: ask again later; the cap or anything else: stop
            if code in TRANSIENT | {"500012", "500018"} and job["tries"] < self.max_tries:
                job["wait"] = self.retry_ticks
                return
            self._fail(d, key, job, on_event,
                       reason=("đã đạt giới hạn số đội — giải tán bớt một đội rồi thử lại"
                               if code == "500054" else str(e)[:120]))
            return
        job["ordered"] = True
        if host:
            job["host"] = str(host["uid"])
        on_event("pawn_move_progress", {"op": "recruit_swap", "note": "đã đặt chiêu mộ"})

    @staticmethod
    def _new_name(by_uid: dict) -> str:
        from nta_agent.execution.heuristics import _unused_army_name
        return _unused_army_name(list(by_uid.values()))

    @staticmethod
    def _pick_host(armies: list, job: dict):
        """An idle army at the city with room whose main type is the one being replaced (the
        replaced pawn will land there), never the target or a leveling buffer; else None
        (a new army is made)."""
        from nta_agent.execution.heuristics import _main_pawn_type
        cap = int(job.get("cap", 9))
        for x in armies:
            if str(x.get("uid")) == job["a"] or str(x.get("name", "")).startswith("Nâng Cấp"):
                continue
            if not is_idle(x) or x.get("index") != job.get("city"):
                continue
            if len(x.get("pawns") or []) + len(x.get("drillPawns") or []) + int(job["count"]) > cap:
                continue
            if _main_pawn_type(x) == int(job["pawn_a"]):
                return x
        return None

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
