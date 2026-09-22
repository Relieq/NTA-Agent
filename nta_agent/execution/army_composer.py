"""Assess an army-composition target and report feasibility + deficit.

The brain turns a user instruction ("1 army of rìu khiên + 4 armies of IMP") into
a composition target in the profile: ``army.composition.target`` = a list of
``{pawn_id, armies, size}`` (each entry = N armies of one pawn type, ``size`` pawns
each). This module assesses whether that target is reachable and what it would take,
so the BRAIN can respond to the user when a request isn't viable (e.g. a pawn type
isn't unlocked, or it exceeds the army-count cap) — the check mechanism the user
asked for.

Pure: no engine/API. Engine mechanics that shaped this (verified in
tools/re/decrypted/index.js, HD_ChangePawnArmy 31343):
- Moving a pawn between armies needs BOTH armies in the SAME cell; an army that
  reaches 0 pawns is auto-removed (frees a slot). So "disband an army" = move/dismiss
  all its pawns. New armies come from recruiting (drill into a new army name), not moves.
- Heroes can't be dismissed and shouldn't be counted as fungible troops.
The executor (ArmyComposer rule) turns this report into concrete rally / ChangePawnArmy
/ DrillPawn / DismissPawn steps.
"""
from __future__ import annotations

from dataclasses import dataclass


def _is_hero(p: dict) -> bool:
    """A hero pawn — excluded from fungible troop counts (can't be dismissed)."""
    return bool(p.get("hero")) or bool(p.get("avatarArmyUID"))


def count_owned(armies: list[dict], pawn_id: int) -> int:
    """Total non-hero pawns of ``pawn_id`` across all armies."""
    return sum(1 for a in armies for p in (a.get("pawns") or [])
               if int(p.get("id", 0) or 0) == pawn_id and not _is_hero(p))


@dataclass
class TargetStatus:
    pawn_id: int
    want_armies: int
    size: int
    want_pawns: int      # want_armies * size
    owned: int           # non-hero pawns of this type currently owned
    deficit: int         # pawns still needed (recruit); 0 if already enough
    unlocked: bool       # is this pawn type recruitable (in pawnSlots)


@dataclass
class CompositionReport:
    feasible: bool
    issues: list          # human-readable strings, for brain advice to the user
    targets: list         # list[TargetStatus]
    total_target_armies: int
    army_cap: int
    over_cap: bool


def assess_composition(target: list[dict], armies: list[dict],
                       unlocked_ids: set[int], army_cap: int) -> CompositionReport:
    """Assess a composition ``target`` against current ``armies``.

    ``target``: list of ``{pawn_id, armies, size}`` (size defaults to 9, armies to 1).
    ``unlocked_ids``: pawn ids that can be recruited (from pawnSlots).
    ``army_cap``: max number of armies the player may hold (0 = unknown -> not checked).

    A target is infeasible when it needs recruiting a locked pawn type, or the total
    target-army count exceeds the cap. A short-but-unlocked type is feasible (recruit
    the deficit); a short-but-locked type is only feasible if already owned in full.
    """
    issues: list[str] = []
    statuses: list[TargetStatus] = []
    total_armies = 0
    for t in target:
        pid = int(t["pawn_id"])
        na = int(t.get("armies", 1) or 1)
        sz = int(t.get("size", 9) or 9)
        want = na * sz
        owned = count_owned(armies, pid)
        deficit = max(0, want - owned)
        unlocked = pid in unlocked_ids
        total_armies += na
        if deficit > 0 and not unlocked:
            issues.append(
                f"pawn {pid} chưa unlock — không chiêu mộ được {deficit} lính còn thiếu")
        elif deficit > 0:
            issues.append(f"cần chiêu mộ thêm {deficit} lính loại {pid}")
        statuses.append(TargetStatus(pid, na, sz, want, owned, deficit, unlocked))

    over_cap = army_cap > 0 and total_armies > army_cap
    if over_cap:
        issues.append(
            f"target {total_armies} đội vượt cap {army_cap} đội — cần dồn/giải tán để lấy slot")

    feasible = (not over_cap) and all(s.deficit == 0 or s.unlocked for s in statuses)
    return CompositionReport(feasible=feasible, issues=issues, targets=statuses,
                             total_target_armies=total_armies, army_cap=army_cap,
                             over_cap=over_cap)
