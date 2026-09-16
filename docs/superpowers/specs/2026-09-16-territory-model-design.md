# Territory model (Tier A: own territory + geometry) — Design

Date: 2026-09-16
Status: Approved (brainstorming) → ready for implementation plan
Owner: NTA-Agent execution (territory) + dashboard

## 1. Problem

To recommend Cứ Điểm (stronghold) placements later (C2) and to reason about
march-speed geography, the agent needs a **territory model**: where the main
city, strongholds/forts, and our armies are, plus geometry helpers (positions,
distances, the ~6-tile speed radius around the main city). Today the agent only
probes a small square around the city per tick — no persistent spatial picture.

This spec builds **Tier A**: our own territory, read cheaply from player state
fields (no packed-chunk decoding). The wider map (occupiable frontier, others'
cells via `GetMapChunk` packed bytes) is deferred (Tier B).

## 2. Ground truth (RE 2026-09-16)

Cheap, structured sources already in `player` (no chunk decode):
- `mainCityIndex` — the main city cell.
- `fortAutoSupports` = `[{index, val}]` — our **fort (Cứ Điểm) cells** + whether
  auto-support (heal/reinforce) is on.
- `buildCitys` (map, keyed by cell index) — cities/forts we built.
- `armyDists` = `[{index, armys[]}]` — cells where our armies sit (garrisons).
- Cell position: `x = index % mapWidth`, `y = index // mapWidth`
  (`mapWidth` from the world map size; default 600 as elsewhere).
- Fort march bonus (game): x3 speed on main-city↔fort and fort↔fort routes +
  heals; and a speed zone within ~6 tiles of the main city (so forts inside that
  radius are redundant). The exact radius/metric is confirmed by the user as
  "6 tiles"; distance metric (Chebyshev vs Manhattan) is a config default, to be
  live-verified.

Deferred (Tier B): `GAME_HD_GetMapChunk{chunkId}` → `PlayerCellBytesInfo`
(`indexs1/indexs2/cities` packed bytes); `chunkId = cy*ceil(mapW/chunkW)+cx`.

## 3. Chosen approach (locked)

A pure `Territory` model built from the player state fields + geometry helpers,
plus a dashboard view. Deterministic; no chunk decode; no network beyond the
state we already hold. It is the foundation the C2 fort-advisor consumes.

## 4. Components

| File | Responsibility |
|---|---|
| `nta_agent/execution/territory.py` | `Territory` dataclass + `build_territory(state, map_width=600) -> Territory`. Fields: `main_city: int`, `forts: list[Fort]` (`Fort{index, auto_support}` from `fortAutoSupports`, plus any `buildCitys` not already forts), `garrisons: list[int]` (from `armyDists` indices), `map_width`. Helpers: `pos(index) -> (x,y)`; `dist(a, b) -> int` (Chebyshev by default); `near_main(index, radius=6) -> bool`; `nodes()` (main + forts) for network reasoning. Pure. |
| `nta_agent/dashboard/server.py` | `read_territory_view(cfg)` (from the snapshot's `player` subset — extend the snapshot to include the needed fields) → `{main_city, forts:[{index,auto_support,x,y}], garrisons:[...], map_width}`; wire `GET /api/territory`. |
| `nta_agent/runtime/snapshot.py` | `_player_subset` additionally carries `main_city_index` (already top-level), `forts` (from `fortAutoSupports`), `garrisons` (from `armyDists` indices), and `map_width` (from world map size). Small, JSON-safe. |
| `nta_agent/dashboard/page.py` | A "Lãnh thổ" panel: main city, forts (index + pos + auto-support on/off), garrison count. Read-only. |

**Fort source:** `fortAutoSupports` is the authoritative fort list (each is a
built stronghold with an auto-support flag). `buildCitys` may include the main
city and sub-cities; union them but tag forts via `fortAutoSupports` membership.

## 5. Data flow

```
state.raw.player.{mainCityIndex, fortAutoSupports, armyDists, buildCitys}
  -> build_territory(state) -> Territory{main_city, forts, garrisons, map_width}
snapshot: write forts/garrisons/map_width into state.json
dashboard: GET /api/territory -> "Lãnh thổ" panel
(next: C2 fort-advisor consumes Territory geometry)
```

## 6. Error handling / edge

- Missing player fields → empty forts/garrisons (Territory still builds).
- `map_width` unknown → default 600 (matches occupy_planner).
- No snapshot → dashboard shows "—" (like other panels).

## 7. Non-goals

- Tier B: packed-chunk decode / wider map (occupiable frontier, enemy cells).
- The fort-placement advisor itself (C2 — separate spec, consumes this).
- Auto-building forts (user builds manually).
- Persisting a crawl of discovered cells over time (local discovery stays the
  per-tick occupy probe).

## 8. Testing

- `build_territory` — from a fake state.raw: main city, forts (with
  auto_support), garrisons parsed; `pos`/`dist`/`near_main` correct (Chebyshev,
  radius 6 boundary).
- snapshot — `state_to_dict` includes forts/garrisons/map_width.
- `read_territory_view` — shapes the snapshot into the API payload.
- dashboard page — has the "Lãnh thổ" panel + `/api/territory`.
- Full Python suite + ruff.
