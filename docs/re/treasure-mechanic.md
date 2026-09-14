# Chest / Treasure mechanic — RE findings (B1 Task 1)

Date: 2026-09-14. Source: `tools/re/decrypted/index.js` + `nta_agent/data/config/*`
+ protocol schema. Purpose: define the fields B1's `treasure_model` and occupy
planner read.

## 1. Cell → loot lookup

A resource cell's loot comes from its **landAttr** row (keyed by the cell's
`land_id`, ids ~1001–10xx):

- `treasures_count` = `"min,max"` — number of treasures (chests) the cell drops.
- `treasures_lv` = `"w1,w2,w3"` — **weights (percent) over treasure tiers 1/2/3**
  (e.g. `"50,0,0"` = tier-1 only; `"0,0,100"` = tier-3 only; `"70,30,0"` = 70% t1
  / 30% t2). NOT a single level.
- `armys_3/4/5` = defenders by group size (used by the sim already).
- `need_stamina`, `tonden_time` = cost/time.

Each tier maps to a `treasure.json` row group (ids 3xx=t1/2/3, 4xx, 5xx… — the
group is chosen by land/resource type; a secondary detail). A `treasure.json`
row has `rewards` = `"type,sub,min,max|…"` (resource type + amount range) and
`count`.

**Reward score (for ranking, not exact):**
`reward_value = chosen_count × Σ_i ( weight_i/100 × avg_reward(tier_i) )`
where `avg_reward` = mean of the `(min,max)` amounts in the tier's `rewards`.
`chosen_count` = upper bound of `treasures_count` (or its mean).

The engine's authoritative per-cell drop is `getBattleTreasureCount(cell, land)`
→ `{treasureIds, treasureCounts, specialTreasureId}` (empty for villages / owned
cells). For planning from config we use the landAttr lookup above; the engine
call is only needed if we later want exact drops.

## 2. Chest budget (open capacity)

**Two regimes (per the user):**
- **Newbie / ranked:** a daily open-capacity — `+50/day, capped at 50` when the
  current value `< 50`. This cap is **not** enforced in the client-side novice
  `HD_OpenTreasure` handler and **not** a config constant we could find — it is
  server-side / mode-specific. **Not observable from the novice test account.**
- **Free mode:** unlimited opens, but a pawn must have an **empty treasure slot**
  to receive a chest (bounded by per-pawn `pawnTreasures` capacity).

`HD_OpenTreasure(auid,puid,uid)` opens one pawn's treasure (err `500076` if it
has no unopened treasure / already opened), applies policy `TREASURE_AWARD`
boost. `HD_ClaimTreasure` then collects. Per-army variants:
`OpenArmyTreasure{index,auid}` / `ClaimArmyTreasure{index,auid}`; batch
`OpenArmysTreasure{targets}`. `PlayerInfo.hasNewTreasure` (bool) flags unopened.

**B1 decision:** `chest_budget(state)` returns a real capacity field **if
present** in `state.raw.player`; otherwise a large **unlimited sentinel** so the
loop never blocks. On the novice account this means the farming planner ranks by
**reward-per-chest** and takes the winnable cells in order (budget effectively
unbounded); the hard 50/day cap is applied only once a ranked account exposes the
field (revisit then). This matches "optimize chests by phase/capability" as far
as the data allows now.

## 3. Open → claim flow (agent)

1. Occupy a cell (existing) → winning pawns receive treasures (`pawnTreasures`).
2. `OpenArmyTreasure{index, auid}` (or per-pawn `OpenTreasure`) to reveal.
3. `ClaimArmyTreasure{index, auid}` (or `ClaimTreasure`) to collect rewards.
   `hasNewTreasure` / `pawnTreasures` indicate what is pending.

## 4. Consequences for the plan

- Task 3 `cell_loot(land_id, config)`: read `landAttr[land_id]`; `chest_cost` =
  upper of `treasures_count`; `reward_value` = tier-weighted avg × count (per §1).
- Task 3 `chest_budget(state)`: real field if present, else unlimited sentinel.
- Task 6 treasure open/claim: `Actions.open_army_treasure(index, auid)` +
  `claim_army_treasure(index, auid)` → routes `game/HD_OpenArmyTreasure` /
  `game/HD_ClaimArmyTreasure`.
