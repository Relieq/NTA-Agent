# C1 — In-city construction (build new buildings) — Design

Date: 2026-09-16
Status: Approved (brainstorming) → ready for implementation plan
Owner: NTA-Agent execution (build_planner/heuristics) + data/config + io/api

## 1. Problem

The agent only **upgrades** existing buildings (`BuildOrder` + `build_planner.
next_upgrade` + `HD_UpAreaBuild`). It never **constructs new** buildings. When a
building is unlocked (prereqs met) but not yet present — or more instances are
allowed (e.g. up to 3 granaries) — the agent should build it. C1 adds
deterministic in-city construction; the brain does not participate (later).

## 2. Ground truth (RE 2026-09-16)

- **API:** `game/HD_AddAreaBuild{index, id}` constructs a new building; the
  **server auto-places** it (the player never picks a tile — matches the UX).
  `HD_MoveAreaBuild` relocates (not needed). `HD_UpAreaBuild{index,uid}` upgrades
  (already implemented).
- **`buildBase.json`** (24 rows): `id`, `type` (1 = in-city, 2 = outside/other),
  `bt_count`, `prep_cond`, `ui`. In-city = the 16 type-1 buildings (Thành Chính,
  Kho Lương, Binh Doanh, Chợ, Tiệm Rèn, Xưởng, Y Quán, …).
- **`bt_count`** = max instances, magnitude: `-1` = 1 allowed, `-3` = up to 3
  (Kho Lương). Model: `max_count(id) = abs(bt_count)` (0 → treat as 1).
- **Construction cost/prereq** = the level-1 row in `buildAttr`
  (`buildId*1000 + 1`), same table as upgrades → reuse `config.build_upgrade(id,
  1)` (`up_cost`, `prep_cond`). Building-level prereq (`prep_cond` type 4,
  `"4,<buildId>,<lv>"`) is checked locally; other types default true (server
  validates).
- Constraints mirror upgrades: build-queue slots, main-hall level cap
  (non-main buildings can't exceed main hall level — a fresh lv1 always ≤ cap
  when main ≥ 1), prereqs, affordability.

## 3. Chosen approach (locked)

Unify the planner into **one next build action** that is either a *construct* or
an *upgrade*, so `BuildOrder` drives both. Deterministic: for buildings in the
priority order, construct any that are unlocked, under their `bt_count`, and
affordable at lv1; otherwise upgrade as today. No profile/brain input in C1.

## 4. Components

| File | Change |
|---|---|
| `data/config.py` | `build_base(build_id) -> dict|None` (a `buildBase.json` row); `max_count(build_id) -> int` = `abs(bt_count)` (0 → 1); `in_city_build_ids() -> list[int]` (type==1). |
| `execution/build_planner.py` | `BuildAction` dataclass: `kind` = `"construct"` (with `build_id`, `up`) or `"upgrade"` (with `build`, `up`). `next_build_action(state, config, sequence=None, blocked=None) -> BuildAction|None`: walk the order; for each id, if current instance count `< max_count` and lv1 is prereq/cap/cost-OK and not blocked → construct(lv1); else fall through to the existing upgrade logic. Keep `next_upgrade` (used by tests / as the upgrade half). |
| `execution/actions.py` | `add_build(index, build_id) -> dict` → `game/HD_AddAreaBuild{index, id}`. |
| `execution/heuristics.py` (`BuildOrder`) | Use `next_build_action`; `_pending` carries the `BuildAction`. `act`: construct → `actions.add_build(state.main_city_index, build_id)`; upgrade → `actions.upgrade_build(index, uid)` (unchanged). Server reject → `blocked` (keyed so a construct and an upgrade of the same id are distinct); cleared when the builds signature changes (existing retry). |

**Blocked key:** upgrades key on `(uid, target_lv)`; constructs have no uid yet,
so key on `("construct", build_id)`. The planner skips blocked entries of both
shapes.

**Priority / count semantics:** a building id yields a *construct* step while its
instance count is below `max_count` and it's eligible; once at max (or not yet
eligible) it yields *upgrade* steps for its existing instances. This naturally
builds missing buildings (count 0 → 1) and extra allowed ones (granary ×3),
then upgrades, all following the same order the upgrade planner already uses.

## 5. Data flow

```
BuildOrder.applies -> next_build_action(state, config, sequence, blocked):
  for build_id in order:
    if count(build_id) < max_count(build_id) and eligible_lv1: -> construct
    else: existing upgrade walk -> upgrade
BuildOrder.act:
  construct -> actions.add_build(main_city_index, build_id)
  upgrade   -> actions.upgrade_build(index, uid)
  server reject -> blocked; retried when builds change
```

## 6. Error handling

- Config absent → `BuildOrder` never applies (as today).
- Server rejects a construct (a condition we can't verify locally) → add
  `("construct", build_id)` to `blocked`, surface the error; retried after the
  builds signature changes.
- Build-queue full → no action (existing check).

## 7. Non-goals

- Outside-city architecture / strongholds (C2).
- Brain-driven construction priority (later; C1 is a fixed deterministic order).
- Choosing the tile / `MoveAreaBuild` (server auto-places).
- New building *types* logic beyond buildBase type==1.

## 8. Testing

- `config.max_count` / `build_base` / `in_city_build_ids` — read buildBase
  correctly (abs(bt_count); 0→1; type filter).
- `next_build_action` — constructs a missing unlocked building (count 0 <
  max, prereq/cost ok); respects `bt_count` (won't construct beyond max);
  respects prereq/main-cap/cost/build-queue; falls through to upgrade when at
  max; skips blocked construct/upgrade entries.
- `BuildOrder` — dispatches construct → `add_build(city, id)` and upgrade →
  `upgrade_build`; a rejected construct is blocked and retried after builds
  change.
- `actions.add_build` — sends `game/HD_AddAreaBuild` with `{index, id}`.
- Full Python suite + ruff; existing upgrade tests stay green.
