# Tier B full-map — enemy cells + unowned frontier — Design

Date: 2026-09-17
Status: Approved (brainstorming) → pending user review
Owner: NTA-Agent execution (mapchunk/territory) + runtime (fort_service) + dashboard (server/TerritoryPanel)

## 1. Problem

The territory map shows only *my* cells. The packed map chunks we already fetch
(`game/HD_GetMapChunk` → `cells: map<playerUid, PlayerCellBytesInfo>`) contain
**every player's** owned cells in that chunk, so enemy territory + enemy
cities/forts are decodable for **free** (no extra requests). We also want the
**unowned frontier** — cells bordering my territory that nobody owns in the
fetched area — as an approximate "where I can expand" hint.

**Data limits found (RE):** the chunk reply is *only* `cells` per player
(`indexs1`/`indexs2`/`cities` bytes). There is **no terrain/land-type** field, so
true "occupiable resource cell" cannot be derived; the frontier is an
approximation (unowned neighbours of my land) and cannot distinguish resource
land from sea/obstacle. Enemy/frontier are limited to the chunks we fetch (main +
border-adjacent), i.e. **near** my territory — a whole-map crawl (36 chunks) is
out of scope.

## 2. Goals / non-goals

**Goals**
- Decode **all players** in the already-fetched chunks → `enemy_cells`,
  `enemy_cities` (with cityType, incl. enemy forts) — no extra requests.
- Compute the **unowned frontier**: 4-neighbours of my owned cells that are in
  bounds and owned by nobody (me or any enemy) in the fetched area.
- Render enemy territory + enemy cities + frontier on the map, with legend +
  hover/click states.

**Non-goals**
- No whole-map crawl / "scan all 36 chunks" button.
- No terrain detection (impossible from this reply); frontier is approximate.
- No fort-advisor change (this is a data + visualization layer; using enemies to
  tune recommendations is a later step).
- No per-enemy colouring (all enemies one colour in v1; uid kept for tooltip).

## 3. Architecture & components

| File | Change |
|---|---|
| `nta_agent/execution/territory.py` | New `scan_map(actions, main, uid, map_width=600, focus=None) -> dict` with keys `owned` (set), `cities` (dict idx→type, mine), `enemy_cells` (set), `enemy_cities` (dict idx→type), `frontier` (set). Same chunk-fetch + border-adjacency as `scan_owned`, but for each chunk decode **every** uid entry: `uid==str(mine)` → owned/my-cities; else → enemy_cells/enemy_cities. After all chunks: `frontier = { n for c in owned for n in 4-neighbours(c) if in-bounds and n not in owned and n not in enemy_cells }`. Keep `scan_owned` (thin wrapper or unchanged) for back-compat. |
| `nta_agent/runtime/fort_service.py` | Use `scan_map` instead of `scan_owned`; add `enemy_cells`, `enemy_cities`, `frontier` (as `[x,y]` / `{x,y,type}` coord lists) to the `forts.json` payload. `plan_forts` still uses `owned` only (advisor unchanged). |
| `nta_agent/dashboard/server.py` | `read_forts_view` + `recompute_forts` pass through `enemy_cells`, `enemy_cities`, `frontier` (default `[]`). |
| `nta_agent/dashboard/static/components/TerritoryPanel.js` | Render enemy cells (red fill), enemy cities (distinct marker), frontier (subtle dotted neutral outline). Extend the cell-state map + tooltip/click ("địch", "biên giới trống") + legend. Include enemy/frontier in the fit bounding box. |

## 4. Rendering

- **Enemy cells**: filled red (validate the fill set {owned aqua #199e70, main blue
  #3987e5, fort orange #d95926, enemy red} with the dataviz script; pick the red
  step that passes). Enemy fills never coincide with my rec **rings** (recs are my
  cells), and shape differs, so overlap is a non-issue.
- **Enemy cities/forts**: a small distinct marker (e.g. a dark-outlined dot or a
  small triangle) on enemy city cells, coloured by cityType if useful.
- **Frontier**: a subtle dotted **neutral** (`--muted`) outline per frontier cell
  (no fill) so it reads as "empty, expandable" without dominating.
- Draw order: zone fill → owned → enemy → garrisons → forts → accepted → frontier
  outline → recs → main → hover. (Frontier under recs/main.)
- Legend adds: red = ô địch; enemy-city marker; dotted = biên giới trống (xấp xỉ,
  có thể mở).

## 5. Data flow

```
FortService.tick (landCount changed): scan_map(actions, main, uid)
  -> for each fetched chunk, decode EVERY uid -> owned + enemy_cells + enemy_cities
  -> frontier = unowned 4-neighbours of owned (in fetched area)
  -> forts.json += {enemy_cells, enemy_cities, frontier}   (plan_forts unchanged)
dashboard /api/forts -> view passes enemy_cells/enemy_cities/frontier through
TerritoryPanel -> draws enemy + frontier; tooltip/click/legend
```

## 6. Edge cases

- No enemies in view → empty lists; map unchanged from today.
- A neighbour owned in an unfetched chunk shows as frontier (approximation) — documented.
- Large enemy sets: same viewport culling as owned; only visible cells drawn.
- forts.json without the new keys (old file) → view defaults to `[]`; no crash.
- `scan_map` with a chunk missing / empty → skip that chunk (as `scan_owned`).

## 7. Testing

- `territory.scan_map` (fake actions returning a chunk with 2 uids): mine →
  `owned`; other → `enemy_cells`/`enemy_cities`; `frontier` = unowned neighbours
  of owned excluding enemy; border-adjacent fetch still triggered by my cells.
- `fort_service`: `forts.json` gains `enemy_cells`/`enemy_cities`/`frontier`;
  `recommendations` unchanged (still from owned).
- `server`: `read_forts_view`/`recompute_forts` include the new keys (default []).
- FE marker tests: `TerritoryPanel.js` references `enemy_cells`/`frontier`, an
  enemy colour, and legend text "địch"/"biên giới".
- Palette: dataviz validate the 4 fills; record PASS (adjust enemy red if needed).
- Full `pytest` + `ruff`.
- **Live verify on machine A** (reuse the tab): if enemies exist near the main
  city they render (red) with cities; frontier cells show as dotted outlines;
  hover/click report "địch"/"biên giới trống"; owned/recs still correct; no
  console errors. (If no enemy is near, verify no regression + frontier around the
  owned cluster.)

## 8. Decomposition

One spec: (1) `scan_map` decode-all + frontier (pure-ish, testable), (2)
fort_service + server passthrough, (3) TerritoryPanel rendering + palette
validate + live verify. The plan sequences these.
