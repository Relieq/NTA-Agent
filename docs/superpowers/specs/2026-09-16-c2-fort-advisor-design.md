# C2 — Fort placement advisor (+ Tier B map data) — Design

Date: 2026-09-16
Status: Approved (brainstorming) → ready for implementation plan
Owner: NTA-Agent execution (mapchunk/territory/fort_advisor) + io/api + runtime + dashboard

## 1. Problem

Recommend where to build Cứ Điểm (strongholds) so the player extends their
fast+heal reach outward (border expansion). Forts give x3 march speed on all
main-city↔fort and fort↔fort routes plus on-site healing, so a forward fort lets
you push occupations further and farm continuously. The agent only recommends;
the user builds (forts cost ~30 min and are limited in number). Deterministic
geometry — no LLM.

Blocker resolved: fort recommendations need the positions of owned cells + the
farming frontier, which are **not** in player fields (`armyDists` only lists
cells with a stationed army; `buildCitys` is not index-keyed; no owned-cell list
exists). They come from the map. A spike proved the packed map chunk is
decodable (Tier B): decoding the main-city chunk yielded exactly `landCount=23`
owned cells + the main city in the cities map.

## 2. Ground truth (RE + live spike 2026-09-16)

- `game/HD_GetMapChunk{chunkId}` → `cells: map<playerUid, PlayerCellBytesInfo>`;
  `PlayerCellBytesInfo{indexs1: bytes, indexs2: bytes, cities: bytes}` (packed
  bitstreams). `cells[myUid]` = my cells in that chunk.
- Map 600×600; `CHUNK_SIZE = 100×100` → 6 chunks/row, `chunkId = cy*6 + cx`;
  chunk origin = `(cx*100, cy*100)`; cell index = `y*600 + x`.
- Decoders (engine, reimplemented + live-verified):
  - `indexs1` = run-length rectangles (delta-coded), MSB-first bit reader.
  - `indexs2` = zig-zag delta point list.
  - `cities` = repeated `(dx:7, dy:7, cityType:8)` → `{index: cityType}`
    (cityType 1 = main city; fort has its own type via `CITY_FORT_NID`).
- Cheap change signal: `player.landCount` (in state every tick) — increments when
  you occupy a new cell. `fortAutoSupports` lists existing forts.
- Fort count cap: `config.max_count(2102)` (Cứ Điểm). Fort build ~30 min (context;
  not modeled).

## 3. Chosen approach (locked)

Two cohesive layers, both deterministic:

**Tier B map data (sparse, focused fetch — decode is cheap; requests are the
cost):**
- Re-scan only when `landCount` changes (else skip entirely — most ticks = 0
  requests), or on a long fallback timer, or a manual/profile focus.
- Fetch only chunks that hold territory: start with the main-city chunk; add an
  adjacent chunk only when owned cells touch that chunk's border. Optional
  profile `focus_chunks` to watch specific chunks.
- Decode → the set of owned cell indices + cities map (main city / forts).

**Fort advisor (border-expansion, deterministic geometry):**
- Candidates = owned cells outside the main-city speed radius (Chebyshev, 6),
  not already forts.
- Rank by frontier-ness (distance from main city) and spread (each pick far from
  already-chosen recs and existing forts, so recommendations cover different
  expansion directions — supports "build one, farm another way").
- Recommend up to `max_count(2102) − current_fort_count` cells.
- Output `[{index, pos, reason}]`; surfaced on the dashboard. User builds.

## 4. Components

| File | Responsibility |
|---|---|
| `nta_agent/execution/mapchunk.py` | `BitReader`; `decode_indexs1/2`, `decode_cities`; `decode_player_cells(info, origin_x, origin_y, map_width=600) -> (owned:list[int], cities:dict[int,int])`; `chunk_id(index, map_width, chunk=100)`, `chunk_origin(chunk_id, ...)`. Pure. |
| `nta_agent/execution/actions.py` | `get_map_chunk(chunk_id) -> dict` (`game/HD_GetMapChunk`). |
| `nta_agent/execution/territory.py` | Extend `Territory` with `owned_cells: set[int]`; a `scan_owned(actions, main, uid, map_width, focus=None) -> (owned, cities)` that fetches the city chunk (+ border-adjacent chunks) and decodes. Keep Tier-A build_territory unchanged. |
| `nta_agent/execution/fort_advisor.py` | `recommend_forts(main, owned, forts, map_width, max_forts, radius=6) -> list[dict]` (border-expansion + spread, deterministic). Pure. |
| `nta_agent/runtime/*` | A throttled territory-scan step: only when `landCount` changed since last scan (or a long timer); compute owned + fort recs; write to a JSON (`forts_path`). Never blocks the loop. |
| `nta_agent/dashboard/server.py` + `page.py` | `GET /api/forts` (recs + owned count) → a "Cứ Điểm — gợi ý" panel. |

## 5. Data flow

```
tick: landCount changed? (cheap, from state)  --no--> skip (0 requests)
  --yes--> scan_owned: get_map_chunk(city chunk [+ border chunks])
           -> decode_player_cells -> owned cells + cities/forts
        -> recommend_forts(main, owned, forts, max_forts)
        -> write forts.json {owned_count, recommendations:[{index,pos,reason}]}
dashboard: GET /api/forts -> "Cứ Điểm — gợi ý" panel (user builds manually)
```

## 6. Error handling / edge

- Chunk fetch fails / bytes empty → treat as no new data; keep last scan.
- `landCount` unchanged → no fetch (the whole point).
- No candidates (all territory within radius 6, or fort cap reached) → empty recs.
- Map width unknown → 600 default.
- Decode robust to short/empty byte fields (returns []).

## 7. Non-goals

- Auto-building forts (user builds; ~30-min, limited).
- Modeling a fort-relay max range (x3 assumed on all city/fort routes).
- Full-map crawl (only territory chunks + optional focus; not the whole 6×6 grid
  continuously).
- Brain/LLM involvement (deterministic; brain tuning later if wanted).
- Occupiable-frontier detection beyond owned cells (v1 uses the owned-cell
  frontier; enemy/occupiable cells from other players' chunk entries deferred).

## 8. Testing

- `mapchunk` — golden: decode the real fixture (`tests/fixtures/mapchunk_real.json`)
  → exactly `land_count` owned cells + main city in cities. BitReader unit tests.
- `chunk_id`/`chunk_origin` — round-trip for known indices (main 109726 → chunk 11,
  origin (500,100)).
- `recommend_forts` — pure: excludes cells within radius 6 and existing forts;
  ranks outer/frontier cells; spreads picks; respects the fort-count cap.
- `territory.scan_owned` — fake actions returning a chunk → owned set decoded;
  border-adjacent fetch triggered only when cells touch a border.
- runtime scan — fires only when landCount changes; writes forts.json.
- dashboard — `/api/forts` + panel present.
- Full Python suite + ruff.
