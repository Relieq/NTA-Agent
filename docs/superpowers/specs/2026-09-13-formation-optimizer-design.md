# Formation Optimizer (tank troop order) — Design

Date: 2026-09-13
Status: Approved (brainstorming) → ready for implementation plan
Owner: NTA-Agent execution (formation/heuristics) + predictors + io/api

## 1. Problem

Sim-Advisor v2 (Phase 1) picks which armies attack in what selection order. It
does not control **which pawn stands where** inside a melee/tank army. The user's
priority (c): arrange the tank army so the right pawn absorbs damage, minimizing
deaths and **spreading damage** so the group can fight several battles in a row
without returning to a city/fortress to heal.

## 2. Ground truth (verified in decrypted engine + spike, 2026-09-13)

- **Enemies attack the CLOSEST reachable target.** `Fighter.getTarget` picks
  `getCanAttackTargets()[0]`; the default weight in `addCanAttackTarget` is
  `99 - dist + 2e6` (distance-primary; low-hp / prestige are only strategy
  modifiers). So the **front-most pawn** (nearest the enemy) tanks.
- **Position is the lever.** `GAME_HD_MoveAreaPawns{index, armyUid,
  pawns:[MovePawnInfo{uid, point, armyUid}]}` sets each pawn's grid `point`
  (the in-game formation drag). Confirmed the game route (`net.request(
  "game/HD_MoveAreaPawns")`), used by the formation editor.
- **The sim respects custom per-pawn points** (spike, `runWithReinforce` with
  explicit points): same 3 pikemen vs the same enemy —
  - beefy(200hp) at front → **win, 33% loss, 2/3 survive**;
  - squishy(50hp) at front → **lose, 100% loss, 0/3 survive**.
  Formation flips win↔lose. So the sim can evaluate formations, and the effect
  is large.
- attackSpeed also influences position indirectly (faster acts first → advances
  first), but the **direct** lever the user uses is formation position — this
  spec uses position only; attackSpeed is out of scope.

## 3. Chosen approach (locked)

Add a **formation optimizer** for melee/tank armies, wired into the occupy flow
after Phase 1 picks the ordered plan. For each melee army in the plan:
1. Generate a few candidate pawn→slot assignments (rearranging pawns among the
   slots they already occupy — no new grid needed).
2. Evaluate each with the sim (per-pawn survival) — pick the one with the fewest
   deaths; tie-break by the smallest maximum single-pawn HP loss (damage spread,
   for multi-battle sustain).
3. Apply via `HD_MoveAreaPawns` before issuing the occupy.

Objective: minimize deaths; tie-break = spread damage. Auto-applied. Ranged
armies are left alone (they hold at range naturally).

Determinism/seed unchanged.

## 4. Formation slots (points)

Safest and RE-free: **permute pawns among the points they currently occupy**
(read from `GetPlayerArmys` — each pawn carries `point`). This needs no new grid
and no knowledge of the legal formation layout: we only reassign which pawn sits
in which already-legal slot. Candidate labels:
- `beefy-front` — pawns sorted by max-HP descending mapped onto slots ordered
  front→back (front = closest to the target's entry approach).
- `keep` — current assignment (baseline; chosen if reordering doesn't help).

"Front" ordering of the occupied slots is by proximity to the enemy approach
(the entry funnel direction), computed like the sim's entry geometry.

**Spike (in plan):** confirm `HD_MoveAreaPawns` accepts a permutation of existing
points for an idle (non-marching) army, and that it is legal pre-march. If the
route rejects arbitrary points, fall back to swapping pawns pairwise via
`ExchangePawnArmy`/`ChangePawnArmy` within the army, or skip apply (preview the
recommendation on the feed) — the sim evaluation still holds.

## 5. Components

| File | Change |
|---|---|
| `nta_agent/execution/formation.py` **(new)** | `slot_order(army, target, mapWidth) -> list[point]` (occupied slots front→back); `candidate_formations(army, target) -> list[(label, assignment)]` where `assignment = {pawn_uid: point}`; pure. |
| `nta_agent/execution/predictors/sim_input.py` | `_pawn` passes `point` when present, so a formation reaches the engine. |
| `tools/battlesim/frames.js` | honor a pawn's provided `point` instead of always overwriting with the entry point (fall back to entry when absent). |
| `tools/battlesim/reinforce.js` | result includes per-pawn survival: `survivors.pawns = [{uid, alive, hpLost}]` (for the spread tie-break). |
| `nta_agent/execution/predictors/sim_predictor.py` | surface per-pawn survival on `BattlePrediction` (or a sibling return) so the optimizer can read it. |
| `nta_agent/execution/actions.py` | `move_area_pawns(index, army_uid, assignment)` → `game/HD_MoveAreaPawns`. |
| `nta_agent/execution/heuristics.py` (`OccupyCell`) | after `best_plan`, for each melee army in `plan.armies` optimize formation via the sim, apply `move_area_pawns`, emit `formation_plan{army,label,loss}`, then occupy. |

## 6. Data flow

```
best_plan -> ordered armies
  for each melee army:
    candidate_formations(army, target)               # beefy-front, keep
      -> sim.predict_armies(..., army with assigned points)  # per-pawn survival
      -> pick fewest deaths; tie -> smallest max single-pawn hpLost
    if best != current: actions.move_area_pawns(index, armyUid, assignment)
                        emit formation_plan{army,label,loss}
  actions.occupy_cell(target, ordered armies)
```

Edge cases: single-pawn army → no reorder. Sim unavailable → skip optimization
(occupy proceeds with current formation). MoveAreaPawns fails → log, occupy
anyway (never block the loop). Homogeneous same-HP pawns → `keep` (no benefit).

## 7. Non-goals

- attackSpeed tuning (indirect lever) → not here.
- New formation grid slots / arbitrary repositioning → only permute existing.
- Ranged-army formation → not needed.
- Cross-battle HP planning beyond the single-battle spread tie-break → the
  sustain goal is served by consistently minimizing deaths + spreading.
- Joint-march / tactics profile → Track B.

## 8. Testing

- **Oracle (headline):** the formation spike as a golden — beefy-front vs
  squishy-front on a fixed matchup gives different survival (front tank matters).
- `formation.py` — pure: `slot_order` front→back; `candidate_formations`
  produces beefy-front (highest-HP pawn on the front slot) + keep; single-pawn →
  keep only.
- `reinforce.js` — result exposes per-pawn survival.
- `sim_input` — passes `point` through.
- `OccupyCell` — fake sim: picks the fewer-death formation, calls
  `move_area_pawns` with that assignment, emits `formation_plan`; sim-unavailable
  → no move call, occupy still happens.
- `actions.move_area_pawns` — sends `game/HD_MoveAreaPawns` with the right shape.
- Full Python suite + ruff; Node sidecar goldens stay green.
