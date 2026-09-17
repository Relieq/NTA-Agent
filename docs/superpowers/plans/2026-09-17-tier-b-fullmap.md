# Tier B Full-map (enemy cells + frontier) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decode every player's cells in the chunks we already fetch to surface enemy territory + enemy cities and an approximate unowned frontier, and render them on the territory map — with no extra requests and no advisor change.

**Architecture:** New `territory.scan_map` decodes all uids per fetched chunk (mine → owned, others → enemy) and computes the unowned frontier (4-neighbours of my cells owned by nobody in view). `FortService` writes `enemy_cells`/`enemy_cities`/`frontier` into `forts.json`; the dashboard passes them through and `TerritoryPanel` draws them.

**Tech Stack:** Python 3.12; Vue 3 (vendored, no-build); `<canvas>`.

**Spec:** `docs/superpowers/specs/2026-09-17-tier-b-fullmap-design.md`

## Global Constraints

- No extra requests: `scan_map` fetches the *same* chunks as `scan_owned` (main + border-adjacent + focus); it just decodes all uids in them.
- No terrain data exists → frontier is approximate (unowned neighbours of my land); document it in the legend.
- Fort-advisor unchanged: `plan_forts` still uses `owned` only.
- Enemy/frontier limited to fetched (near) chunks; no whole-map crawl.
- Tests: `.venv/Scripts/python.exe -m pytest -q`; lint `.venv/Scripts/python.exe -m ruff check nta_agent tests`.
- Commit footer on every commit:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_017SWX7TP9uSdjA1HbV883Tm`.

---

### Task 1: `territory.scan_map` (decode all players + frontier)

**Files:**
- Modify: `nta_agent/execution/territory.py`
- Test: `tests/test_scan_map.py`

**Interfaces:**
- Produces: `scan_map(actions, main, uid, map_width=600, focus=None) -> {"owned":set, "cities":dict, "enemy_cells":set, "enemy_cities":dict, "frontier":set}`. `scan_owned` stays for back-compat.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scan_map.py
from nta_agent.execution.territory import scan_map


def _idx(x, y, mw=600): return y * mw + x


class FakeActions:
    """One chunk id 0 (origin 0,0) with my cells + an enemy's cells."""
    def __init__(self, cells): self._cells = cells; self.requested = []
    def get_map_chunk(self, cid):
        self.requested.append(cid)
        return {"cells": self._cells} if cid == 0 else {"cells": {}}


def _rect_bytes(x0, y0, x1, y1):
    # encode a run-length rect via indexs1 (same bit layout mapchunk decodes)
    bits = []
    def put(v, n):
        for i in range(n - 1, -1, -1): bits.append((v >> i) & 1)
    put(x0, 7); put(y0, 7)
    def span(d):  # d in 0..7 uses the 4-bit short form (flag 0 + 3 bits)
        put(0, 1); put(d, 3)
    span(x1 - x0); span(y1 - y0)
    while len(bits) % 8: bits.append(0)
    out = bytearray()
    for i in range(0, len(bits), 8):
        b = 0
        for j in range(8): b = (b << 1) | bits[i + j]
        out.append(b)
    return bytes(out)


def test_scan_map_splits_mine_and_enemy_and_frontier():
    mine = {"indexs1": _rect_bytes(10, 10, 11, 11), "indexs2": b"", "cities": b""}   # 2x2 at (10,10)
    enemy = {"indexs1": _rect_bytes(20, 20, 20, 20), "indexs2": b"", "cities": b""}  # 1 cell (20,20)
    acts = FakeActions({"57696053": mine, "999": enemy})
    m = scan_map(acts, main=_idx(10, 10), uid="57696053", map_width=600)
    assert _idx(10, 10) in m["owned"] and _idx(11, 11) in m["owned"]
    assert _idx(20, 20) in m["enemy_cells"] and _idx(20, 20) not in m["owned"]
    # frontier: unowned 4-neighbours of my 2x2 block, excluding owned + enemy
    assert _idx(9, 10) in m["frontier"] and _idx(12, 10) in m["frontier"]
    assert _idx(10, 10) not in m["frontier"]        # owned is not frontier
    assert _idx(20, 20) not in m["frontier"]         # enemy is not frontier
```

- [ ] **Step 2: Run → FAIL** (`ImportError: scan_map`).

- [ ] **Step 3: Implement `scan_map`** (append to `territory.py`, reusing `_neighbor_chunks`, `chunk_id`, `chunk_origin`, `decode_player_cells`):

```python
def scan_map(actions, main: int, uid, map_width: int = 600, focus=None) -> dict:
    """Fetch the near chunks and decode EVERY player in them.

    Returns owned/cities (mine), enemy_cells/enemy_cities (all other players),
    and frontier (in-bounds 4-neighbours of my cells owned by nobody in view).
    Fetches the same chunks as ``scan_owned`` — no extra requests.
    """
    uid = str(uid)
    owned: set[int] = set()
    cities: dict[int, int] = {}
    enemy_cells: set[int] = set()
    enemy_cities: dict[int, int] = {}
    seen: set[int] = set()

    def fetch(cid: int) -> list[int]:
        if cid in seen:
            return []
        seen.add(cid)
        reply = actions.get_map_chunk(int(cid)) or {}
        cells_map = reply.get("cells") or {}
        ox, oy = chunk_origin(int(cid), map_width)
        mine_here: list[int] = []
        for u, info in cells_map.items():
            if not info:
                continue
            cells, cmap = decode_player_cells(info, ox, oy, map_width)
            if str(u) == uid:
                owned.update(cells)
                cities.update(cmap)
                mine_here = cells
            else:
                enemy_cells.update(cells)
                enemy_cities.update(cmap)
        return mine_here

    start = chunk_id(int(main), map_width)
    start_cells = fetch(start)
    for cid in _neighbor_chunks(start_cells, start, map_width):
        fetch(cid)
    for cid in (focus or []):
        fetch(int(cid))

    frontier: set[int] = set()
    for c in owned:
        x, y = c % map_width, c // map_width
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < map_width and 0 <= ny < map_width:
                n = ny * map_width + nx
                if n not in owned and n not in enemy_cells:
                    frontier.add(n)
    return {"owned": owned, "cities": cities, "enemy_cells": enemy_cells,
            "enemy_cities": enemy_cities, "frontier": frontier}
```

- [ ] **Step 4: Run + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_scan_map.py tests/test_scan_owned.py -q` → PASS.
```bash
git add nta_agent/execution/territory.py tests/test_scan_map.py
git commit -m "feat(territory): scan_map — decode all players + unowned frontier"
```

---

### Task 2: FortService writes enemy/frontier; server passthrough

**Files:**
- Modify: `nta_agent/runtime/fort_service.py`
- Modify: `nta_agent/dashboard/server.py` (`read_forts_view`, `recompute_forts`)
- Test: `tests/test_fort_service.py`, `tests/test_dashboard_forts.py`, `tests/test_dashboard_decide.py`

**Interfaces:**
- Consumes: `scan_map` (T1).
- Produces: `forts.json` gains `enemy_cells: [[x,y]]`, `enemy_cities: [{x,y,type}]`, `frontier: [[x,y]]`; the forts view + recompute pass them through.

- [ ] **Step 1: Update fort_service tests** (the fake `scan` now returns the `scan_map` dict)

In `tests/test_fort_service.py`, change the injected `scan` fakes to return a dict and assert the new keys. Replace each `def scan(...): return set(owned), {}` with:
```python
    def scan(actions, main, uid, map_width=600, focus=None):
        return {"owned": set(owned), "cities": {}, "enemy_cells": set(),
                "enemy_cities": {}, "frontier": set()}
```
Add one enemy/frontier case to `test_scans_and_writes_on_first_tick`:
```python
    def scan(actions, main, uid, map_width=600, focus=None):
        return {"owned": set(owned), "cities": {}, "enemy_cells": {120*600+130},
                "enemy_cities": {120*600+130: 1}, "frontier": {100*600+101}}
    # ... after tick:
    assert [130, 120] in data["enemy_cells"]
    assert {"x": 130, "y": 120, "type": 1} in data["enemy_cities"]
    assert [101, 100] in data["frontier"]
```
(Existing `owned_count`/`recommendations` assertions stay.)

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Wire `fort_service`** — swap the scan + payload:

Change the import: `from nta_agent.execution.territory import scan_map` and default `self._scan = scan or scan_map` (in `__init__`). Replace the scan + payload block in `tick`:
```python
            m = self._scan(self.actions, main, uid, map_width=self.map_width)
            owned = m["owned"]
            fort_indices = [int(f.get("index", 0)) for f in
                            (player.get("fortAutoSupports") or []) if isinstance(f, dict)]
            decisions = fort_decisions.load(self.cfg.fort_decisions_path)
            recs, accepted = plan_forts(main, owned, fort_indices, decisions,
                                        self._max_forts(), map_width=self.map_width,
                                        radius=self.radius)
            mw = self.map_width
            cells = sorted([c % mw, c // mw] for c in owned)
            accepted_coords = sorted([i % mw, i // mw] for i in accepted)
            rejected_coords = sorted([i % mw, i // mw] for i, d in decisions.items()
                                     if d == "rejected")
            enemy_cells = sorted([i % mw, i // mw] for i in m.get("enemy_cells", ()))
            enemy_cities = [{"x": i % mw, "y": i // mw, "type": t}
                            for i, t in (m.get("enemy_cities") or {}).items()]
            frontier = sorted([i % mw, i // mw] for i in m.get("frontier", ()))
            payload = {"owned_count": len(owned), "owned_cells": cells,
                       "accepted": accepted_coords, "rejected": rejected_coords,
                       "enemy_cells": enemy_cells, "enemy_cities": enemy_cities,
                       "frontier": frontier, "recommendations": recs}
```
(Keep the file-write + `fort_scan` event; `recommend_forts` import may remain for the default arg.)

- [ ] **Step 4: Server passthrough**

In `read_forts_view` add to both the success return and the missing-file default:
`"enemy_cells": data.get("enemy_cells") or [], "enemy_cities": data.get("enemy_cities") or [], "frontier": data.get("frontier") or [],`
In `recompute_forts`, carry the existing map layers over unchanged (recompute only redoes recs from owned+decisions):
```python
    payload = {"owned_count": len(owned), "owned_cells": cells,
               "accepted": sorted([i % mw, i // mw] for i in accepted),
               "rejected": sorted([i % mw, i // mw] for i, d in decisions.items() if d == "rejected"),
               "enemy_cells": fdj.get("enemy_cells") or [],
               "enemy_cities": fdj.get("enemy_cities") or [],
               "frontier": fdj.get("frontier") or [],
               "recommendations": recs}
```

- [ ] **Step 5: Update view/decide tests**

In `tests/test_dashboard_forts.py`: the missing-file assertion becomes
`{"owned_count":0,"owned_cells":[],"accepted":[],"rejected":[],"enemy_cells":[],"enemy_cities":[],"frontier":[],"recommendations":[]}`;
the present-file test asserts `v["enemy_cells"]`/`v["frontier"]` pass through when set.
In `tests/test_dashboard_decide.py`: add `"enemy_cells":[[99,99]]` to the seeded forts.json and assert `recompute_forts(cfg)["enemy_cells"] == [[99,99]]` (carried over).

- [ ] **Step 6: Run + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_fort_service.py tests/test_dashboard_forts.py tests/test_dashboard_decide.py -q` → PASS.
```bash
.venv/Scripts/python.exe -m ruff check nta_agent/runtime/fort_service.py nta_agent/dashboard/server.py
git add nta_agent/runtime/fort_service.py nta_agent/dashboard/server.py tests/test_fort_service.py tests/test_dashboard_forts.py tests/test_dashboard_decide.py
git commit -m "feat(fort-service): write enemy cells/cities + frontier to forts.json"
```

---

### Task 3: Render enemy + frontier on the map

**Files:**
- Modify: `nta_agent/dashboard/static/components/TerritoryPanel.js`
- Test: `tests/test_dashboard_components.py`

**Interfaces:**
- Consumes: `/api/forts` `enemy_cells`/`enemy_cities`/`frontier`.

- [ ] **Step 1: Add failing assertions**

```python
def test_territory_map_enemy_and_frontier():
    terr = _c("TerritoryPanel.js")
    assert "enemy_cells" in terr and "frontier" in terr
    assert "địch" in terr and "biên giới" in terr   # legend/state text
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement in `TerritoryPanel.js`**

In `load()`, extend `data` from `f`:
```js
    enemy:(f.enemy_cells||[]), enemyCities:(f.enemy_cities||[]), frontier:(f.frontier||[]),
```
(add these keys to the `data = {...}` object).

In `buildStateMap()`, after the owned loop, add (so tooltip/click report them; owned/enemy/main take priority over frontier):
```js
   data.enemy.forEach(([x,y])=>put(x,y,"địch"));
   data.frontier.forEach(([x,y])=>put(x,y,"biên giới trống"));
```

In `render()`, in the draw sequence: after `data.owned.forEach(... box green)` and before garrisons, draw enemy fills; before recs draw frontier outlines. Concretely add:
```js
   data.enemy.forEach(([x,y])=>{ if(inView(x,y)) box(x,y,"#da3633"); });          // enemy (red)
   data.enemyCities.forEach(c=>{ if(inView(c.x,c.y)){ ctx.strokeStyle="#0b1320"; ctx.lineWidth=2;
    ctx.strokeRect(sX(c.x)+3,sY(c.y)+3,scale-6,scale-6); } });                     // enemy city marker
```
and, just before the rec-rings loop:
```js
   ctx.strokeStyle="#8b949e"; ctx.lineWidth=1; ctx.setLineDash([2,2]);
   data.frontier.forEach(([x,y])=>{ if(inView(x,y)) ctx.strokeRect(sX(x)+2,sY(y)+2,scale-4,scale-4); });
   ctx.setLineDash([]);
```
Extend the fit bounding box `pts` to include enemy + frontier:
```js
   ...data.enemy, ...data.frontier,
```
Update the legend line to add:
```
· <b style="color:#da3633">■</b> ô địch · <b class="muted">▢</b> biên giới trống (xấp xỉ)
```

- [ ] **Step 4: Validate palette (dataviz) + run tests**

Run from the dataviz base dir:
```bash
node scripts/validate_palette.js "#3987e5,#199e70,#d95926,#da3633" --mode dark --pairs all
```
(main, owned, fort, enemy). If enemy↔fort (blue-orange-red) FAILs the normal-vision floor, nudge the enemy red toward a dataviz step and update `#da3633` in the component; re-run to PASS.
Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_components.py -q` → PASS.

- [ ] **Step 5: Full suite + lint + live verify**

Run: `.venv/Scripts/python.exe -m pytest -q` → all pass. `ruff check nta_agent tests` → clean.
Live-verify on machine A (reuse the existing tab): start the agent (dashboard Start) so a scan runs; on the Lãnh thổ tab, enemy cells (if any near) render red with city markers, frontier cells show dotted outlines, hover/click report "địch"/"biên giới trống", legend updated; owned/recs/zone unchanged; no console errors. Screenshot.

- [ ] **Step 6: Commit**

```bash
git add nta_agent/dashboard/static/components/TerritoryPanel.js tests/test_dashboard_components.py
git commit -m "feat(dashboard): render enemy cells/cities + frontier on the map"
```

---

## Self-Review notes (author)

- **Spec coverage**: decode-all + frontier (T1), forts.json enemy/frontier + server passthrough (T2), map rendering + legend + palette validate + live verify (T3). Advisor untouched (spec non-goal). All covered.
- **Type consistency**: `scan_map` dict keys (`owned/cities/enemy_cells/enemy_cities/frontier`) consumed by fort_service; forts.json keys (`enemy_cells [[x,y]]`, `enemy_cities [{x,y,type}]`, `frontier [[x,y]]`) produced in T2, read in view/recompute (T2) and TerritoryPanel (T3).
- **No requests added**: `scan_map` fetches the same chunks as `scan_owned`.
- **No placeholders**: full code inline. Frontier is documented as approximate (no terrain).
