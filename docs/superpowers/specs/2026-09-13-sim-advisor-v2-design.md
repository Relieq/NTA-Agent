# Sim-Advisor v2 (reinforcement-aware turn order + auto selection-order) — Design

Date: 2026-09-13
Status: Approved (brainstorming) → ready for implementation plan
Owner: NTA-Agent execution/predictors + execution (heuristics/advisor)

## 1. Problem

Sim-advisor v1 (`execution/advisor.py::best_occupy`) turns the battle predictor
into a planner, but only over **single armies** and with a harness
(`tools/battlesim/area-factory.js`) that stacks all selected armies into one
battle at once (block order: our pawns, then enemy). That does **not** reproduce
the game's real turn order for the **1-tile** tactic, where armies arrive at
different times and late armies join as reinforcements.

The user's tactical priorities when attacking are (from playstyle notes):
- (a) "đánh nổi không" + loss% — already handled correctly by the deterministic
  forecast predictor; **not** re-litigated here.
- (b) **thứ tự chọn đội** (selection order) for 1-tile (or to avoid it).
- (c) **thứ tự lính trong đội tank** to avoid deaths (deferred — see §7).

v2 delivers (b) with **auto-apply**: the agent picks the selection order that
wins with the least predicted loss and issues the occupy in that order. This
requires the sim to model army arrival timing (reinforcements).

## 2. Ground truth (verified in decrypted engine, 2026-09-13)

Read directly from `tools/re/decrypted/index.js`. Turn order is fully explicit
in code — no observation/guessing needed:

- **Turn loop** `FSPBattleController.getNextFighter()`: walks `this.fighters[]`
  **circularly** (`ut.loopValue`), skipping dead/noncombat. So turn order = the
  order of `fighters[]`. The controller sorts fighters ascending by the assigned
  `attackIndex`.
- **attackIndex assignment** (`ArtofwarObj.battleBegin` / `toArmyStrip`): each
  pawn gets a score; **attacker (our) pawns → `attackSpeed + 1e5`** (always
  first, sorted among themselves by attackSpeed desc); **defender/monster
  (owner "") → `100*attackSpeed + (99 - distToEntry)`** (≤ ~999, appended after).
  Result sorted **descending**, then reassigned `attackIndex = 1,2,3,…`. So one
  battle setup is a **block**: `[our pawns by attackSpeed desc][enemy]` — not a
  global speed mix.
- **Reinforcement = the 1-tile mechanism.** `e.armys.forEach(e => { if
  (!e.isMarching()) {…} })` excludes still-marching armies from the initial
  battle. Arrival scheduling (`ForecastObj.startForecast` case 2):
  - first-selected army → arrival frame 0;
  - army *i* → `O = max(1, floor((marchTime_i − marchTime_0)/(1000/FPS))) +
    tiebreak`; grouped into `addArmyDataMap[O]`.
  - After a wave settles, `getNextPendingFrame(frame)` finds the next arrival;
    if any, `pendingRestartFrame` is set and the update loop calls
    `restartBattleWithReinforce(frame)` (via `toArmyStrip` + `getEnemyArmys`),
    else `settleResult(frame)`.
- **Enemy target priority** (relevant to §7, not built here): within range,
  enemies favor the higher-attack-speed unit; ties break by in-army order.

**Consequence:** the user's recollection is correct and code-backed — select
archers first (arrive first) → they fight alone (turn 1 cung), then enemies
(turns 2–3), cung again next round (circular), and the tank joins **late as
reinforcement** (last). Not a global-speed sort. This resolves the previously
open 1-tile turn-order question; no ADB needed.

## 3. Chosen approach (locked)

**Approach A — reuse the engine's own reinforcement methods** via a thin Node
orchestrator, rather than reimplementing the reinforcement loop.

Driving the full `ForecastObj.startForecast` is rejected: `init()` pulls
`mc.getModel("artofwarServer"/"artofwarWorld")` and case 2 reads enemies from
`artofwarServer.getArea()`, dragging in the world model + a result cache. Too
heavy for headless.

Instead: instantiate `ForecastObj`, set its fields directly (bypassing
`init()`/`startForecast`), and call its own correctness-critical methods
(`toArmyStrip`, `getEnemyArmys`, `restartBattleWithReinforce`,
`getNextPendingFrame`, `settleResult`) plus the update pump. The orchestrator
supplies inputs (targetCell `{index, landId}`, `passPoints`, `selectArmys` in
selection order, optional `enemyArmyConf`, `owner`, `randSeed`, `FPS/FPS_MUL`)
and replicates only the ~20 lines of arrival-scheduling glue. All win/loss/order
logic stays engine code → faithful, no drift.

Determinism unchanged: `randSeed = floor(uid/100) + targetIndex`.

## 4. Sidecar changes (`tools/battlesim/`)

| File | Change |
|---|---|
| `bundle.js` | `loadEngine` also exposes the `ForecastObj` class (require by name). |
| `reinforce.js` **(new)** | Orchestrator: build `ForecastObj`, set fields, schedule arrivals into `addArmyDataMap`, run first wave + enemy, pump `update(dt)`, inject reinforcements at arrival frames via the engine methods, return `{isWin, lossLv, lossPercent}`. |
| `area-factory.js` | Slimmed to input-building; the hand-rolled multi-army stacking/ordering is removed (replaced by `reinforce.js`). Single-army = one wave at frame 0. |
| `forecast.js` | Route: single-army / no march-time skew → existing fast path; multi-army or skewed marchTime → `reinforce.js`. |
| `server.js`, `run-once.js` | **Interface unchanged** — Forecast Input in, `{isWin, lossLv, lossPercent}` out. |
| `test/golden.test.js` | Add a reinforcement/1-tile golden: 2 armies (archer small marchTime + tank larger) → assert (a) turn order archer→enemy→late-tank via a `beginAction` hook, (b) stable result. Existing single-army goldens stay green (4/4). |

**Implementation spikes (recorded in the plan, not blocking design):**
1. `ForecastObj` module name in the registry.
2. Minimal field-set to bypass `init()`/world/cache.
3. Exact `update()` pump sequence and how survivor HP/state carries across waves
   (engine behavior — validated by golden, not reasoned).
4. If `ForecastObj` proves inseparable from the world model, fallback: call the
   pure methods (`toArmyStrip`/`restartBattleWithReinforce`/`settleResult`) on a
   bare instance and hold minimal state in the orchestrator — still reuses the
   correct logic.

## 5. Advisor + occupy behavior (Python)

**`execution/advisor.py` — keep pure over injected `predict`.** Generalize from
"score each army" to "score each **plan** (ordered group)":

- `Plan{armies: list[dict] (ordered), target: int, label: str, prediction}`.
- `best_plan(candidates, plans_for, predict)`: `plans_for(cell) -> list[Plan
  without prediction]`; predict each; pick the **winning** plan with the lowest
  `loss_percent`; tie → **fewer armies** (don't waste troops). Single-army is
  just a 1-element plan (v1 `best_occupy` becomes a special case).

**Candidate generation (in the rule/wiring layer, so advisor stays pure).** For
the reachable idle-army group at a target, emit a small, tactically-meaningful
set instead of N! permutations:
- **archers-first** (1-tile: ranged seed, tank arrives late to absorb),
- **tanks-first** (avoid 1-tile / tank absorbs from the start),
- **each single army** (when one suffices).
Classify archer vs tank by PawnType (3 = archer). Typically 3–5 plans/target.

**`execution/heuristics.py::OccupyCell` (auto-apply):**
- Build `plans_for(cell)` from the strategies above.
- Predict via `SimBattlePredictor` (multi-army/skewed → reinforcement path).
- Emit `occupy_plan{target, label, order, loss_percent}` to the event feed
  (auditability: what was chosen and why).
- Issue `occupy_cell(target, plan.armies)` — **list order = selection order**
  (server respects it).

**marchTime per (army, target):** the arrival schedule needs each army's march
time to the target. Derive from army `march_speed` (armies.json) + cell
distance, or an API field if one exists (spike). Relative order (who arrives
first) is what dominates; absolute frame count affects only how many rounds
elapse before reinforcement.

**Guardrails / performance:**
- Auto-commit a group only when a plan **wins**; otherwise fall back to the
  strongest single army or skip (as today).
- Cap the number of plans; optionally cache by (target, army-composition) so the
  per-tick sim count stays bounded.

## 6. Data flow

```
GameState → occupy candidates → reachable idle armies (group)
  → plans_for: {archers-first, tanks-first, single-army}
  → SimBattlePredictor (multi-army → reinforce.js: schedule arrivals + inject reinforcements)
  → best_plan: lowest-loss winning plan
  → occupy_cell(target, plan.armies)  +  emit occupy_plan{label, order, loss}
```

Edge cases (loop must never die):
- **Node/engine absent** → `SimUnavailable` → stats-predictor fallback (no
  reinforcement modeling) → order degrades to a default heuristic
  (archers-first); still runs.
- **Equal/unknown marchTime** → armies arrive together (joint) → order by
  selection/attackSpeed; valid.
- **Single reachable army** → single-wave (frame 0), as today.
- **No winning plan** → skip the target, as today.
- **Enemy dies before reinforcement arrives** → `settleResult`, no spurious
  injection.

## 7. Non-goals (Phase 1)

- (c) tank troop-order optimization + mutating persistent pawn attack-speed →
  **separate Phase 2 spec** (needs the in-army reorder API RE'd + a decision on
  mutating durable config).
- Joint-march grouping configuration / tactics profile → **Track B**.
- Booting full `startForecast` / world model → deliberately bypassed.
- Brute-force N! permutation search → heuristic candidate strategies instead.
- New dashboard UI → `occupy_plan` already surfaces on the feed.

## 8. Testing

- `advisor.best_plan` — pure: picks the min-loss winning plan across strategies;
  tie-breaks to fewer armies.
- Sidecar golden — reinforcement/1-tile: turn order (archer→enemy→late-tank) +
  stable result; single-army goldens still 4/4.
- `OccupyCell` — fake predictor: verifies it commits the winning order and emits
  `occupy_plan`.
- Fallback — `SimUnavailable`: advisor still returns a plan via stats predictor.
