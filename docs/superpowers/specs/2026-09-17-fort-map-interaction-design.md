# Interactive territory map — coord rulers + accept/reject fort recs (D) — Design

Date: 2026-09-17
Status: Brainstorming approved (reframed with user) → pending user review of this spec
Owner: NTA-Agent execution (fort_advisor) + runtime (fort_service/config) + dashboard (server/TerritoryPanel/FortsPanel)

## 1. Problem

The territory mini-map is read-only and **hard to read positionally** — there are
no coordinates, so a cell's location is unclear. And fort recommendations are
shown but the player can't act on them from the map. Reframed goal (from the
user): the map should (1) show **coordinate rulers**, and (2) surface the fort
**recommendations on the map**, where clicking one lets the user **accept or
reject** it — the agent recommends, the user decides (it does **not** let the
user draw arbitrary forts; the old bot had no such thing either).

Built on the Vue FE + the existing `TerritoryPanel` canvas and the C2 fort
advisor.

## 2. Goals / non-goals

**Goals**
- **Coordinate rulers** around the map canvas (X across the top, Y down the left),
  adaptive spacing, aligned to the auto-scaled grid; hover shows a cell's (x, y).
- **Accept / Reject** a recommendation, persisted, honored by the advisor:
  - *Reject* → never recommend that cell again.
  - *Accept* → treat it as a planned fort: exclude from candidates, use as a
    spread anchor for future recs, and count it against the fort cap.
- Decisions take effect **immediately** (no waiting for a `landCount` change):
  the recommendation set is recomputed from the already-scanned owned cells.
- Both a **map click** (hit-test a rec → Accept/Reject) and **list buttons**
  (accessible equivalent in the Cứ Điểm panel).

**Non-goals**
- No user-drawn/arbitrary fort marking (only decisions on advisor recs).
- No auto-building forts (user still builds manually in-game).
- No editing owned cells / other players' cells.
- No new game requests for a decision (pure recompute from persisted data).

## 3. Data model

- `build/run/fort_decisions.json`: `{ "<cell_index>": "accepted" | "rejected", ... }`.
- `cfg.fort_decisions_path` → `log_dir/"fort_decisions.json"`.
- `forts.json` (written by `FortService`) gains `accepted: [[x,y], ...]` alongside
  the existing `owned_count`, `owned_cells`, `recommendations`. `recommendations`
  now exclude accepted + rejected cells.

## 4. Architecture & components

| File | Change |
|---|---|
| `nta_agent/execution/fort_advisor.py` | `recommend_forts(..., rejected=None)` — also exclude `rejected` indices from candidates. New pure `plan_forts(main, owned, existing_forts, decisions, cap, map_width=600, radius=6) -> (recs, accepted_indices)`: `accepted`/`rejected` split from `decisions`; `forts=existing_forts+accepted` (excluded + spread anchors); `slots = max(0, cap - len(existing_forts) - len(accepted))`; returns recs + accepted list. |
| `nta_agent/runtime/config.py` | Add `fort_decisions_path` → `log_dir/"fort_decisions.json"`. |
| `nta_agent/runtime/fort_service.py` | Load `fort_decisions.json`; use `plan_forts` (instead of calling `recommend_forts` directly); write `accepted` coords + recs into `forts.json`. Behavior unchanged when there are no decisions. |
| `nta_agent/dashboard/server.py` | `read_forts_view` includes `accepted`. New `POST /api/forts/decide {index:int, decision:"accept"|"reject"|"clear"}`: update `fort_decisions.json`, **recompute** `forts.json` from its `owned_cells` + snapshot main/forts + decisions via `plan_forts`, return the fresh forts view. A shared `recompute_forts(cfg)` helper reads owned_cells + territory + decisions and rewrites forts.json. |
| `nta_agent/dashboard/static/components/TerritoryPanel.js` | Draw coordinate rulers (top X, left Y) with adaptive label step; render accepted forts distinctly (e.g., filled orange with a check-dot) and pending recs as clickable red rings; on canvas click, hit-test the nearest rec → emit a `select` with its index → a small Accept/Reject popover. Hover tooltip shows (x, y). |
| `nta_agent/dashboard/static/components/FortsPanel.js` | Per-rec **Chấp thuận / Từ chối** buttons; an **Đã chấp thuận** list and an **Đã từ chối** list, each item with a **×** to clear the decision. Calls `POST /api/forts/decide`, then refreshes. |

### 4.1 `plan_forts` (the shared brain)
```
accepted = [i for i,d in decisions if d=="accepted"]
rejected = [i for i,d in decisions if d=="rejected"]
recs = recommend_forts(main, owned, forts=existing_forts+accepted,
                       rejected=rejected, max_forts=cap-len(existing)-len(accepted), ...)
return recs, accepted
```
Used by both `FortService.tick` (periodic, after a chunk scan) and the dashboard
`recompute_forts` (instant, after a decision) so they never diverge.

## 5. Data flow

```
periodic:  FortService.tick -> scan_owned -> plan_forts(decisions) -> forts.json
decision:  UI click Accept/Reject -> POST /api/forts/decide
             -> write fort_decisions.json
             -> recompute_forts: owned_cells(forts.json)+main/forts(snapshot)+decisions
                -> plan_forts -> rewrite forts.json  (no game request)
             -> return forts view -> map + list refresh
render:    TerritoryPanel draws rulers + owned + zone + forts + accepted + rec rings
```

## 6. UI details

- **Rulers**: reserve a small inner margin (≈24px left, ≈16px top) in the 640×360
  canvas; draw axis tick labels every `k` cells where `k` is chosen so labels are
  ≥ ~34px apart (adaptive to the auto-scaled cell size); light `--muted` color.
- **Recs**: red ring (as today) + a subtle pulse/label; clicking within ~half a
  cell of a rec centre selects it. A popover (absolutely-positioned div over the
  card) shows the cell (x, y) + **Chấp thuận** / **Từ chối** / **Đóng**.
- **Accepted**: rendered as an orange filled cell with a small check dot, to read
  as "planned fort". Listed in the panel with a **×** (clear → back to candidate).
- **Rejected**: not drawn; listed under "Đã từ chối" with a **×** to un-reject.

## 7. Error handling / edge

- No `fort_decisions.json` → no decisions → current behavior exactly.
- Decide on an index not in owned/recs → still recorded (harmless; ignored by
  `plan_forts` candidate filter if not owned).
- `clear` on an index → remove its key from decisions, recompute.
- Recompute when `forts.json` has no `owned_cells` yet (agent never scanned) →
  empty recs, accepted still echoed; no crash.
- Cap reached via accepted (slots 0) → no new recs.
- Concurrent decisions: the decide handler reads-modifies-writes the small JSON
  under the request; last write wins (single operator — acceptable).

## 8. Testing

- `fort_advisor`: `recommend_forts(..., rejected={idx})` excludes that cell;
  `plan_forts` — accepted becomes a spread anchor + excluded + counts toward cap
  (slots reduced), rejected excluded, returns accepted list; no decisions →
  same as before.
- `config`: `fort_decisions_path` name.
- `fort_service`: with a `fort_decisions.json`, `forts.json` recs exclude
  accepted/rejected and include `accepted` coords.
- `server`: `POST /api/forts/decide` writes the decision file and rewrites
  `forts.json` (recs updated) without any game request; `read_forts_view`
  includes `accepted`; `clear` removes a decision.
- FE: `TerritoryPanel.js` has ruler drawing + click hit-test + accepted marker;
  `FortsPanel.js` has accept/reject/clear + the two lists (marker assertions).
- Full `pytest` + `ruff`; **live verify on machine A**: rulers legible; a rec is
  clickable on the map and via the list; Accept removes it from recs and shows it
  as a planned fort (and future recs spread away); Reject removes it and it never
  returns; Clear restores it; all instant (no re-scan); no console errors.

## 9. Decomposition

One spec; implement as: advisor `rejected`+`plan_forts` (pure) → config +
fort_service wiring → server decide endpoint + recompute → FE rulers → FE
decisions (map click + list). The plan sequences these as tasks.
