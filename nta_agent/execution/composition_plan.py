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

from nta_agent.execution.army_composer import _is_hero, assess_composition


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
    report = assess_composition(target, armies, unlocked_ids, army_cap)
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

    # 2) co-located: pull target-type pawns from donors, then recruit the remainder.
    actions: list[dict] = []
    # track donor pawns still available to move (co-located only)
    donor_pool: dict[int, list[tuple[str, str]]] = {}  # pid -> [(donor_uid, pawn_uid)]
    for d in donors:
        if d.get("index") != city_index:
            continue
        for p in (d.get("pawns") or []):
            pid = int(p.get("id", 0) or 0)
            if pid in needed_types and not _is_hero(p):
                donor_pool.setdefault(pid, []).append((d["uid"], p.get("uid")))

    for a in assign:
        if not a["uid"]:
            continue  # a fresh army to create is handled by recruit below
        pid, sz = a["pawn_id"], a["size"]
        have = _count(by_uid[a["uid"]], pid)
        need = sz - have
        while need > 0 and donor_pool.get(pid):
            src_uid, pawn_uid = donor_pool[pid].pop()
            actions.append({"op": "move_pawn", "from": src_uid, "pawn": pawn_uid, "to": a["uid"]})
            need -= 1

    # 3) RECRUIT any remaining per-type deficit (owned across strike+donors < needed).
    for t in report.targets:
        if t.deficit <= 0:
            continue
        # deficit already accounts for owned; subtract what donor moves will cover is
        # implicit (moves come from owned, which deficit excluded). Recruit t.deficit.
        # spread into the short strike armies of this type (executor picks the army).
        shorts = [a["uid"] for a in assign if a["pawn_id"] == t.pawn_id]
        actions.append({"op": "recruit", "pawn_id": t.pawn_id,
                        "army": shorts[0] if shorts else None, "count": t.deficit})

    done = not actions and all(
        a["uid"] and _count(by_uid[a["uid"]], a["pawn_id"]) >= a["size"] for a in assign)
    return {"assign": [a for a in assign if a["uid"]], "actions": actions,
            "done": done, "blocked": False, "report": report}
