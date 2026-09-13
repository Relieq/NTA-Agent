# Sim-Advisor v2 (record-validated reinforcement + auto selection-order) — Design

Date: 2026-09-13
Status: Approved (brainstorming) → ready for implementation plan
Owner: NTA-Agent execution/predictors + execution (heuristics/advisor) + io/api

## 1. Problem

Sim-advisor v1 (`execution/advisor.py::best_occupy`) plans over **single armies**
with a harness (`tools/battlesim/area-factory.js`) that stacks all selected
armies into one battle at once (block order: our pawns, then enemy). That does
**not** reproduce the game's real turn order for the **1-tile** tactic, where a
later-selected army (e.g. the tank) arrives after the others and joins as a
**reinforcement wave** — so it acts after the enemy, not before it.

v2 delivers auto **selection-order** planning (attack with the order that wins
with least predicted loss) on a sim whose turn order matches the real game,
**validated against real battle records** the game stores.

The user's tactical priorities: (a) "đánh nổi không" + loss% (already trusted);
(b) **thứ tự chọn đội** (this spec); (c) tank troop order (deferred — §8).

## 2. Ground truth: the game stores full battle records

The game persists every battle and can replay it. Confirmed live via API
(`GAME_HD_GetBattleRecordsList` → `GAME_HD_GetBattleRecord{uid}` →
`BattleRecordInfo.frames[]`). A record is a **complete, deterministic
re-simulation input plus the real outcome** — no video, no guessing.

Real 1-tile record fetched 2026-09-13 (cung Đội 2 + tank Đội 3 vs a monster
tile, index 109725, isWin=true, 0 dead), saved as
`tools/battlesim/test/fixtures/battle_1tile.json`:

- **Frame type 0 (initial):** `randSeed=686685` (= `floor(uid/100)+index`,
  matches our formula), `fps=20`, `armys` = our cung army (5× id 3305, lv1,
  attackSpeed 5, hp/point) + enemy army (3× id 4116, lv2, attackSpeed 7), and
  `fighters` = the ordering: **cung ai 1–5 (camp 2), then enemy ai 6–8 (camp 1)**.
  Each fighter carries its `buffs` inline (e.g. policy 1027 +10%).
- **Frame type 1 (reinforce) `currentFrameIndex=1`:** `army` = tank "Đội 3"
  (7× id 3101, lv1, attackSpeed 6), `fighters` = **tank ai 9–15 (camp 2)** —
  appended **after** the enemy.
- **Frame type 200 `currentFrameIndex=1537`:** battle-end marker.

**This confirms the mechanism (and the user's recollection):** turn order =
`attackIndex` order = **cung (1-5) → enemy (6-8) → tank (9-15)**; the tank is a
**separate reinforcement wave** (arrived frame 1), so it acts *after* the enemy,
last. Our attacker pawns form a block before the enemy within each wave (not a
global speed mix). See also engine reading in
`nta-agent-re-findings` memory / §1 of the battle-simulator spec.

`FighterInfo` fields per fighter: `uid, camp, attackIndex, enterIndex, point,
hp, buffs, enterDir` (id/lv are 0 inline — pawn stats live in the frame's
`armys[].pawns`, keyed by uid). `AreaPawnInfo`: `id, lv, attackSpeed, hp, point`.

## 3. Chosen approach (locked)

1. **Battle records are the ground truth + validation oracle.** Add a thin
   read-only API capability to fetch records; keep the saved fixture as a golden
   oracle. Replaying a record's frames through the sim must reproduce its
   recorded outcome (isWin + dead count).
2. **Model reinforcement with a "frames" abstraction that mirrors the record
   format.** The sim consumes a list of waves: one type-0 (initial: armys +
   fighters + randSeed + fps) and zero-or-more type-1 (`currentFrameIndex` +
   army + fighters). A thin Node driver runs the initial wave via
   `battleLocalBegin`, and at each type-1 frame injects the wave by replicating
   the engine's `restartBattleWithReinforce` (source read: remove current armys,
   re-add arriving army + enemies, `battleLocalBegin(..., currentFrameIndex)`).
   Rejected: instantiating `ArtofwarForecastObj` — `require` of it **hangs**
   headless (module-load side effects) and it drags in the world model + cache.
   We reuse the engine's *methods/objects* (`AreaObj`, `battleLocalBegin`,
   `restartBattleWithReinforce`) without the world-bound wrapper.
3. **Two producers of the frames abstraction:**
   - *Record path* (oracle/tests): frames straight from a `BattleRecordInfo`.
   - *Live path* (advisor): frames built from current armies + target —
     schedule arrivals from marchTime (verified formula:
     `frame = max(1, floor((marchTime_i − marchTime_0)/(1000/FPS))) + tiebreak`;
     first army → frame 0), order pawns by attackSpeed desc, append enemy.
4. **Advisor v2** evaluates candidate selection orders on the faithful sim and
   the occupy rule auto-applies the best.

Determinism unchanged: `randSeed = floor(uid/100) + targetIndex` (matches
records).

## 4. Battle-record infrastructure (Python, `io`/tools)

- `execution/actions.py`: `get_battle_records_list() -> list[dict]`
  (`game/HD_GetBattleRecordsList`); `get_battle_record(uid: str) -> dict`
  (`game/HD_GetBattleRecord`).
- `tools/re/` or a small script: fetch + save a record as a JSON fixture (the
  saved `battle_1tile.json` is the first). Read-only; no game state changes.
- Fixture doubles as the sidecar oracle input (§5).

## 5. Sidecar changes (`tools/battlesim/`)

| File | Change |
|---|---|
| `cc-shim.js` | **Done in spike:** add static `Vec2.equals(a,b)` — melee pathfinding calls it; absence crashed multi-wave/melee battles. Keep. |
| `frames.js` **(new)** | Build the frames abstraction from a Forecast Input (live path): schedule arrivals from marchTime; produce `{initial:{armys,fighters,randSeed,fps}, waves:[{currentFrameIndex,army,fighters}]}`. Pure, unit-testable. |
| `reinforce.js` **(new)** | Driver: run `initial` via `AreaObj.battleLocalBegin`; pump `update(dt)`; at each wave's `currentFrameIndex`, inject via the engine's `restartBattleWithReinforce`-equivalent (remove armys, add arriving army + enemies, `battleLocalBegin(..., currentFrameIndex)`); return `{isWin, lossLv, lossPercent, survivors}`. |
| `record-replay.js` **(new, test util)** | Convert a `BattleRecordInfo` (fixture) into the frames abstraction and run it through `reinforce.js` — the oracle. |
| `area-factory.js` | Slimmed: the all-at-once multi-army stacking is superseded by `frames.js` + `reinforce.js`. Single-army = one initial wave, no reinforcement. |
| `forecast.js` | Route: single-army / no march skew → existing fast path; multi-army → `frames.js` + `reinforce.js`. Interface unchanged. |
| `server.js`, `run-once.js` | **Interface unchanged.** |
| `test/golden.test.js` | Add **oracle golden**: load `fixtures/battle_1tile.json`, replay via `record-replay.js`, assert `isWin===true` and self losses === 0 (matches the record). Keep single-army goldens (4/4) green. |

**Design guardrail:** `reinforce.js` and the record driver share one code path
(the frames abstraction), so validating the record path validates the live path's
engine driver; only frame *construction* differs.

## 6. Advisor + occupy behavior (Python)

**`execution/advisor.py` — pure over injected `predict`:**
- `Plan{armies: list[dict] (ordered), target: int, label: str, prediction}`.
- `best_plan(candidates, plans_for, predict)`: `plans_for(cell) -> list[Plan
  without prediction]`; predict each; pick the winning plan with lowest
  `loss_percent`; tie → fewer armies. (v1 `best_occupy` = single-army special
  case.)

**Candidate generation (rule/wiring layer, keeps advisor pure):** for the
reachable idle-army group, emit a few tactically-meaningful orders (not N!):
**archers-first** (1-tile), **tanks-first** (avoid 1-tile), **each single
army**. Classify by PawnType (3 = archer). ~3–5 plans/target.

**`execution/heuristics.py::OccupyCell` (auto-apply):**
- Build `plans_for(cell)`; predict via `SimBattlePredictor` (multi-army →
  reinforcement path); emit `occupy_plan{target,label,order,loss_percent}`;
  issue `occupy_cell(target, plan.armies)` — list order = selection order.

**marchTime per (army,target):** derive from army `march_speed` + cell distance
(records confirm the arrival-frame formula). Relative order dominates.

**Guardrails/perf:** commit a group only when a plan wins; else strongest single
army or skip. Cap plan count; optional cache by (target, composition).

## 7. Data flow

```
GameState → occupy candidates → reachable idle armies (group)
  → plans_for: {archers-first, tanks-first, single-army}
  → frames.js (schedule arrivals) → reinforce.js (engine driver)
  → best_plan: lowest-loss winning plan
  → occupy_cell(target, plan.armies)  +  emit occupy_plan{label, order, loss}

Validation (offline): fixtures/battle_1tile.json → record-replay.js
  → reinforce.js → assert outcome == recorded (isWin, dead=0)
```

Edge cases (loop never dies): Node/engine absent → `SimUnavailable` → stats
fallback → default order (archers-first). Equal/unknown marchTime → arrive
together, order by selection/attackSpeed. Single army → one wave. No winning
plan → skip. Enemy dies before reinforcement → settle, no spurious wave.

## 8. Non-goals (Phase 1)

- (c) tank troop-order optimization + mutating persistent pawn attack-speed →
  separate Phase 2 spec.
- Joint-march grouping config / tactics profile → Track B.
- Live per-tick record fetching for closed-loop calibration → later; Phase 1
  uses records offline as oracle/fixtures.
- Full `ArtofwarForecastObj` / world-model boot → rejected (hangs).
- Brute-force N! search → heuristic candidate strategies.
- New dashboard UI → `occupy_plan` already on the feed.

## 9. Testing

- **Oracle golden (headline):** replay `battle_1tile.json` → sim reproduces
  isWin=true, 0 self losses. This is the fidelity gate.
- `frames.js` — pure: arrival scheduling from marchTime (first→frame0, later→
  computed frame); pawn ordering.
- `reinforce.js` — a 2-wave scenario injects the second wave at its frame.
- `advisor.best_plan` — pure: picks min-loss winning plan; tie → fewer armies.
- `OccupyCell` — fake predictor: commits the winning order, emits `occupy_plan`.
- Fallback — `SimUnavailable`: still returns a plan via stats predictor.
- Python: `get_battle_records_list`/`get_battle_record` send the right routes.
- Existing single-army goldens (4/4) stay green.
