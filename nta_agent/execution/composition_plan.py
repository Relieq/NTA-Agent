"""Pure reconciliation planner for the army-composition strike group.

Given a composition target (e.g. 1 army of rìu khiên 3206 + 4 armies of IMP 3305),
the current armies, and which armies are off-limits (farm group / busy), decide the
NEXT batch of actions to move toward the target. Called each tick by the executor
rule (increment 2b), which applies the actions to live state and persists the
strike-army assignment.

Actions (ops):
- ``rally``       {uids:[...], to:cityIndex}         — bring scattered armies to the city
- ``move_pawn``   {from:uid, pawn:uid, to:uid}       — HD_ChangePawnArmy (co-located only)
- ``recruit``     {pawn_id, army:uid|None, count}    — HD_DrillPawn the deficit
- ``dismiss_pawn``{army:uid, pawn:uid}               — HD_DisMissPawn a low-level leftover

Engine constraints honored (verified, HD_ChangePawnArmy 31343): pawn moves need both
armies in the SAME cell; an emptied army auto-removes; new armies come from recruiting.
This module is PURE (no engine/API) so it is fully unit-tested.

NOTE (increment 2a): purging non-target pawns out of a strike army (move to a donor
or dismiss lowest-level) is deferred to the next increment with its own tests — this
version handles assign / rally / pull-target / recruit / done, which is the core.
"""
from __future__ import annotations

from nta_agent.execution.army_composer import _is_hero, assess_composition, count_owned


def _count(army: dict, pawn_id: int) -> int:
    return sum(1 for p in (army.get("pawns") or [])
              if int(p.get("id", 0) or 0) == pawn_id and not _is_hero(p))


def _slots(target: list[dict]) -> list[tuple[int, int]]:
    """Expand target into per-army (pawn_id, size) slots."""
    out: list[tuple[int, int]] = []
    for t in target:
        pid, na, sz = int(t["pawn_id"]), int(t.get("armies", 1) or 1), int(t.get("size", 9) or 9)
        out.extend([(pid, sz)] * na)
    return out


def _assign(target: list[dict], armies: list[dict], reserved: set,
            strike_uids: list) -> list[dict]:
    """Map strike armies to (pawn_id, size) slots by type affinity (stable).

    If ``strike_uids`` is given, only those armies are candidates (persisted choice);
    otherwise pick from idle, non-reserved armies. A slot with no available army gets
    ``uid=None`` (the executor must recruit a fresh army for it).
    """
    by_uid = {a["uid"]: a for a in armies}
    if strike_uids:
        pool = [by_uid[u] for u in strike_uids if u in by_uid]
    else:
        pool = [a for a in armies if a["uid"] not in reserved and a.get("state", 0) == 0]
    used: set = set()
    assign: list[dict] = []
    for pid, sz in _slots(target):
        cands = sorted((a for a in pool if a["uid"] not in used),
                       key=lambda a: (-_count(a, pid), str(a["uid"])))
        if cands:
            a = cands[0]
            used.add(a["uid"])
            assign.append({"uid": a["uid"], "pawn_id": pid, "size": sz})
        else:
            assign.append({"uid": None, "pawn_id": pid, "size": sz})
    return assign


def plan_composition_step(target, armies, city_index, strike_uids, reserved_uids,
                          unlocked_ids, army_cap):
    """Return {assign, actions, done, blocked, report} — the next step toward target."""
    # Feasibility is judged over the USABLE pool (reserved/farm pawns are never pulled),
    # so a request isn't called feasible just because the farm holds the pawns.
    usable_armies = [a for a in armies if a["uid"] not in set(reserved_uids)]
    report = assess_composition(target, usable_armies, unlocked_ids, army_cap)
    assign = _assign(target, armies, set(reserved_uids), list(strike_uids or []))
    if not report.feasible:
        return {"assign": [a for a in assign if a["uid"]], "actions": [],
                "done": False, "blocked": True, "report": report}

    by_uid = {a["uid"]: a for a in armies}
    strike_set = {a["uid"] for a in assign if a["uid"]}
    # donors = the pool: not a strike army, not reserved, has pawns.
    donors = [a for a in armies
              if a["uid"] not in strike_set and a["uid"] not in set(reserved_uids)]

    # 1) RALLY: strike armies + donors that hold a needed target type must be at the city.
    needed_types = {int(t["pawn_id"]) for t in target}
    scatter: list[str] = []
    for a in assign:
        if a["uid"] and by_uid[a["uid"]].get("index") != city_index:
            scatter.append(a["uid"])
    for d in donors:
        if d.get("index") != city_index and any(_count(d, pid) for pid in needed_types):
            scatter.append(d["uid"])
    if scatter:
        return {"assign": [a for a in assign if a["uid"]],
                "actions": [{"op": "rally", "uids": scatter, "to": city_index}],
                "done": False, "blocked": False, "report": report}

    # 2) co-located: purge non-target from strike armies, pull target from the pool,
    #    then recruit the remainder. Everything uses only co-located, non-reserved donors.
    actions: list[dict] = []
    co_donors = [d for d in donors if d.get("index") == city_index]
    donor_room = {d["uid"]: max(0, 9 - len(d.get("pawns") or [])) for d in co_donors}
    donor_pool: dict[int, list[tuple[str, str]]] = {}  # pid -> [(donor_uid, pawn_uid)]
    for d in co_donors:
        for p in (d.get("pawns") or []):
            pid = int(p.get("id", 0) or 0)
            if pid in needed_types and not _is_hero(p):
                donor_pool.setdefault(pid, []).append((d["uid"], p.get("uid")))

    # 2a) PURGE non-target pawns out of each strike army (end state = pure target type).
    #     Prefer MOVING to a co-located donor with room (preserve the unit), starting
    #     with the highest-level pawns; DISMISS the rest lowest-level first (user: dismiss
    #     low-level lính). Never empty a strike army that has no target pawns yet.
    dismissals: list[tuple[int, dict]] = []
    for a in assign:
        if not a["uid"]:
            continue
        army = by_uid[a["uid"]]
        pid = a["pawn_id"]
        have = _count(army, pid)
        pawns = army.get("pawns") or []
        non_target = [p for p in pawns
                      if int(p.get("id", 0) or 0) != pid and not _is_hero(p)]
        non_target.sort(key=lambda p: -int(p.get("lv", 0) or 0))  # high-lv first (to preserve)
        total = len(pawns)
        for p in non_target:
            if have == 0 and total <= 1:
                break  # keep >=1 so an unfilled strike army's uid survives
            dest = next((u for u, room in donor_room.items() if room > 0), None)
            if dest:
                actions.append({"op": "move_pawn", "from": a["uid"],
                                "pawn": p.get("uid"), "to": dest})
                donor_room[dest] -= 1
            else:
                dismissals.append((int(p.get("lv", 0) or 0),
                                   {"op": "dismiss_pawn", "army": a["uid"], "pawn": p.get("uid")}))
            total -= 1
    dismissals.sort(key=lambda x: x[0])          # dismiss lowest-level first
    actions.extend(d for _, d in dismissals)

    # 2b) PULL target-type pawns from the pool into short strike armies.
    for a in assign:
        if not a["uid"]:
            continue
        pid, sz = a["pawn_id"], a["size"]
        need = sz - _count(by_uid[a["uid"]], pid)
        while need > 0 and donor_pool.get(pid):
            src_uid, pawn_uid = donor_pool[pid].pop()
            actions.append({"op": "move_pawn", "from": src_uid, "pawn": pawn_uid, "to": a["uid"]})
            need -= 1

    # 2c) RECRUIT the remaining deficit — counted over the USABLE (non-reserved) pool
    #     only, since reserved (farm) pawns are never pulled into the strike group.
    usable = [a for a in armies if a["uid"] not in set(reserved_uids)]
    for pid in sorted(needed_types):
        want = sum(a["size"] for a in assign if a["pawn_id"] == pid)
        deficit = max(0, want - count_owned(usable, pid))
        if deficit > 0:
            # target a strike army of this type that still has ROOM — NOT just the
            # first one (which may already be full: recruiting into a full army loops
            # on ecode.500019 and the other short armies never get filled).
            shorts = [a["uid"] for a in assign if a["pawn_id"] == pid and a["uid"]
                      and _count(by_uid[a["uid"]], pid) < a["size"]
                      and len(by_uid[a["uid"]].get("pawns") or []) < 9]
            actions.append({"op": "recruit", "pawn_id": pid,
                            "army": shorts[0] if shorts else None, "count": deficit})

    done = not actions and all(
        a["uid"] and _count(by_uid[a["uid"]], a["pawn_id"]) >= a["size"] for a in assign)
    return {"assign": [a for a in assign if a["uid"]], "actions": actions,
            "done": done, "blocked": False, "report": report}
