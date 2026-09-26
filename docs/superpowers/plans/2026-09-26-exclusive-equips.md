# Exclusive Equipment Implementation Plan

> **For agentic workers:** execute task-by-task with TDD (failing test → code → green → commit).

**Goal:** Player chooses exclusive equipment + smelting on the dashboard (agent sends exactly that); the agent
recasts exclusive equips toward per-effect minimums, locking the first satisfied effect with a fixator.

**Spec:** `docs/superpowers/specs/2026-09-26-exclusive-equips-design.md`

## Global Constraints
- Exclusive effect pools come from `HD_GetWorldRandomInfo.exclusiveMap` (per match), never `equipBase.effect`.
- Fixators per recast = (1 if locked) + smelted effects whose type is in the equip's pool.
- The agent never smelts, restores a smelt or equips on its own; smelt/restore only from a confirmed dashboard command.
- Per-item iron AND fixator budgets; lock only an effect meeting all its minimums; never recast an equip locked on an
  unwanted effect; no forge while smelting (500237) and vice versa.
- Commit per task on `feat-exclusive-equips`; merge `--no-ff`; trailer as usual.

### Task 1: Game API + state
- `Actions.get_world_random_info() -> {exclusive: {id: [types]}, pawn_cost: {id: n}}`,
  `smelting_equip(main_uid, vice_ids)`, `restore_smelt_equip(uid)`.
- store: notify 64 SMELT_EQUIP_RET (`data_64` EquipInfo) → clear `player.currSmeltEquip`, upsert equip.
- Tests: request shapes; notify handling.

### Task 2: `execution/exclusive.py` (pure)
- `is_exclusive(base)`, `smelted_types(equip)` (attrs[i][4] smeltId), `natural_effects(equip)`,
  `fixator_per_recast(equip, pool)`, `smelt_slots(smithy_lv)`, `vice_candidates(equips, base_of, exclude)`,
  `smelt_preview(main, vice_bases, pool, effect_row)`.

### Task 3: `forge.py` for exclusives
- `craft_candidates(..., exclusive=True)` crafts studied exclusives too.
- `next_recast(..., pools, fixators)` → decisions `recast` | `lock`; exclusive: pool from `pools`, fixator cost, budget
  `fixator_budget`, lock-first-satisfied, unwanted-lock guard, skip when smelting.
- `forge_view` rows for exclusives (pool options, lock, smelted marks, fixator/recast, blocked reason).

### Task 4: Forge rule + targets
- Forge rule: pools source, lock action (`lock_equip_effect`), spend `(uid, iron, fixator)`, wait while smelting.
- `forge_targets`: `fixator_budget`, `spend(path, uid, iron, fixator=0)`; server `set_forge_target` accepts it.

### Task 5: World random info cache
- Runner fetches it once at start (+ on new game) → `build/run/world_random.json`; forge rule + dashboard read it.

### Task 6: Dashboard — forge + decisions
- ForgePanel: exclusive rows (pawn tag, per-match effect list, lock, fixator budget, fixators per recast, blocked msg).
- Decisions: equip options that are exclusive show pawn + per-match effects.

### Task 7: Dashboard — smelting
- `GET /api/smelt` (exclusives, vice candidates, open slots by smithy lv, current smelt), `POST /api/smelt/preview`,
  commands `smelt` / `restore_smelt` (DecisionService executes). SmeltPanel with preview + confirm + restore.

### Task 8: Verify + docs
- Full suite; restart; read-only live: world random info fetched, views render. README + memory.
