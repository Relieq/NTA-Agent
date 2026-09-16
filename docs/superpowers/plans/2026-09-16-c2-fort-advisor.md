# C2 — Fort Advisor (+ Tier B map data) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recommend where to build Cứ Điểm (border-expansion, deterministic), fed by a sparsely-fetched, decoded map-chunk data layer; surface on the dashboard. User builds forts manually.

**Architecture:** `mapchunk` decodes packed `GetMapChunk` bytes → owned cells + cities/forts (spike-verified). A throttled scan (only when `landCount` changes) fetches territory chunks and computes fort recommendations via `fort_advisor` (frontier + spread), written to `forts.json` and shown on the dashboard.

**Tech Stack:** Python 3.12 (`.venv/Scripts/python.exe`), pytest, ruff. Reuses territory, config, runtime, dashboard, the API session.

**Spec:** `docs/superpowers/specs/2026-09-16-c2-fort-advisor-design.md`

## Global Constraints

- Lint `ruff check nta_agent tests`; test `.venv/Scripts/python.exe -m pytest -q`.
- Map 600×600, `CHUNK=100` → 6 chunks/row, `chunk_id = cy*6 + cx`, origin `(cx*100, cy*100)`, `index = y*600 + x`.
- BitReader is **MSB-first**; decoders exactly as spike-verified (see spec §2).
- Route `game/HD_GetMapChunk` with `{"chunkId": int}`; `cells` keyed by playerUid.
- Fetch is the cost, not decode: scan only when `player.landCount` changed; only territory chunks. Loop never blocks on scan failure.
- Fort cap = `config.max_count(2102)`; radius metric Chebyshev, radius 6.
- Golden fixture: `tests/fixtures/mapchunk_real.json` (chunk 11, origin (500,100), main 109726, land_count 23, base64 `indexs1/indexs2/cities`).
- Commit proactively per green task; finish flow = push → PR → merge.

---

### Task 1: `mapchunk.py` — decode packed cells (+ golden)

**Files:** Create `nta_agent/execution/mapchunk.py`; Test `tests/test_mapchunk.py`

**Interfaces:**
- `chunk_id(index, map_width=600, chunk=100) -> int`; `chunk_origin(cid, map_width=600, chunk=100) -> tuple[int,int]`.
- `decode_player_cells(info: dict, origin_x: int, origin_y: int, map_width=600) -> tuple[list[int], dict[int,int]]` — `info` has `indexs1`/`indexs2`/`cities` (bytes); returns (owned indices, {index: cityType}).

- [ ] **Step 1: Write the golden + unit tests**

```python
# tests/test_mapchunk.py
import base64
import json
from pathlib import Path

from nta_agent.execution.mapchunk import chunk_id, chunk_origin, decode_player_cells

FX = json.loads(Path("tests/fixtures/mapchunk_real.json").read_text(encoding="utf-8"))


def test_chunk_id_and_origin_for_main_city():
    assert chunk_id(109726) == FX["chunk_id"] == 11
    assert chunk_origin(11) == tuple(FX["origin"]) == (500, 100)


def test_decode_real_chunk_matches_land_count():
    info = {k: base64.b64decode(FX[k]) for k in ("indexs1", "indexs2", "cities")}
    ox, oy = FX["origin"]
    owned, cities = decode_player_cells(info, ox, oy)
    assert len(owned) == FX["land_count"] == 23
    assert FX["main_city"] in owned
    assert cities.get(FX["main_city"]) == 1   # main-city cityType
```

- [ ] **Step 2: Run** → FAIL (module missing).
- [ ] **Step 3: Implement** (bit reader + decoders exactly as spike-verified)

```python
# nta_agent/execution/mapchunk.py
"""Decode packed GetMapChunk PlayerCellBytes -> owned cell indices + cities.

Reimplements the engine's MSB-first bit reader + the indexs1 (run-length rects),
indexs2 (zig-zag delta points), and cities decoders. Verified against a real
chunk (23 owned cells == landCount)."""
from __future__ import annotations

MAP_WIDTH = 600
CHUNK = 100


def chunk_id(index: int, map_width: int = MAP_WIDTH, chunk: int = CHUNK) -> int:
    x, y = index % map_width, index // map_width
    per_row = -(-map_width // chunk)
    return (y // chunk) * per_row + (x // chunk)


def chunk_origin(cid: int, map_width: int = MAP_WIDTH, chunk: int = CHUNK) -> tuple[int, int]:
    per_row = -(-map_width // chunk)
    return ((cid % per_row) * chunk, (cid // per_row) * chunk)


def _idx(x, y, w):
    return -1 if (x < 0 or x >= w or y < 0 or y >= w) else y * w + x


class _BR:
    def __init__(self, data: bytes):
        self.d, self.bi, self.bo, self.total = data, 0, 0, 8 * len(data)

    def read(self, n: int) -> int:
        t = 0
        while n > 0:
            if self.bi >= len(self.d):
                return 0
            r = min(8 - self.bo, n)
            o = 8 - self.bo - r
            t = (t << r) | ((self.d[self.bi] >> o) & ((1 << r) - 1))
            self.bo += r
            n -= r
            if self.bo >= 8:
                self.bo = 0
                self.bi += 1
        return t

    def has(self, n: int) -> bool:
        return 8 * self.bi + self.bo + n <= self.total


def _dec_indexs1(b, t, n, w):
    br, out = _BR(b), []

    def s():
        if br.read(1) == 0:
            return br.read(3)
        if br.read(1) == 0:
            return 8 + br.read(5)
        return 32 + br.read(7)

    while br.has(18):
        l = t + br.read(7); c = n + br.read(7)
        u = l + s(); p = c + s()
        for d in range(c, p + 1):
            for h in range(l, u + 1):
                i = _idx(h, d, w)
                if i >= 0:
                    out.append(i)
    return out


def _dec_indexs2(b, t, n, w):
    br, out = _BR(b), []

    def s():
        e = (br.read(4) if br.read(1) == 0
             else (16 + br.read(6) if br.read(1) == 0 else 64 + br.read(8)))
        v = e >> 1
        return -v - 1 if e & 1 else v

    if not br.has(14):
        return out
    h = br.read(7); f = br.read(7)
    i = _idx(t + h, n + f, w)
    if i >= 0:
        out.append(i)
    while br.has(10):
        h += s(); f += s()
        i = _idx(t + h, n + f, w)
        if i >= 0:
            out.append(i)
    return out


def _dec_cities(b, t, n, w):
    br, o = _BR(b), {}
    while br.has(22):
        s = br.read(7); l = br.read(7); c = br.read(8)
        i = _idx(t + s, n + l, w)
        if i >= 0:
            o[i] = c
    return o


def decode_player_cells(info: dict, origin_x: int, origin_y: int, map_width: int = MAP_WIDTH):
    i1 = info.get("indexs1") or b""
    i2 = info.get("indexs2") or b""
    ci = info.get("cities") or b""
    owned = _dec_indexs1(i1, origin_x, origin_y, map_width) + _dec_indexs2(i2, origin_x, origin_y, map_width)
    cities = _dec_cities(ci, origin_x, origin_y, map_width)
    return owned, cities
```

- [ ] **Step 4: Run** → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/execution/mapchunk.py tests/test_mapchunk.py && git commit -m "execution: decode packed map-chunk cells (golden vs real chunk)"`

---

### Task 2: `get_map_chunk` action + fort cityType constant

**Files:** Modify `nta_agent/execution/actions.py`; Test `tests/test_actions_mapchunk.py`

**Interfaces:** `Actions.get_map_chunk(chunk_id) -> dict` → `game/HD_GetMapChunk {"chunkId": int}` (returns the raw reply; caller reads `cells`).

- [ ] **Step 1: Write failing test**

```python
# tests/test_actions_mapchunk.py
from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self, reply=None):
        self.state = GameState(source="api"); self.state.raw = {}
        self._reply = reply or {"cells": {}}
        self.sent = []
    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params)); return self._reply


def test_get_map_chunk_sends_route():
    s = FakeSession({"cells": {"1": {}}})
    out = Actions(s).get_map_chunk(11)
    assert s.sent[0] == ("game/HD_GetMapChunk", {"chunkId": 11})
    assert out == {"cells": {"1": {}}}
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — near `get_area` in `actions.py`:

```python
    def get_map_chunk(self, chunk_id: int) -> dict:
        """Fetch a packed map chunk (GAME_HD_GetMapChunk); caller decodes cells."""
        return self.session.request("game/HD_GetMapChunk", {"chunkId": int(chunk_id)})
```

- [ ] **Step 4: Run** → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/execution/actions.py tests/test_actions_mapchunk.py && git commit -m "execution: get_map_chunk action"`

---

### Task 3: `territory.scan_owned` — fetch + decode territory chunks

**Files:** Modify `nta_agent/execution/territory.py`; Test `tests/test_territory_scan.py`

**Interfaces:** `scan_owned(actions, main_index, uid, map_width=600) -> tuple[set[int], dict[int,int]]` — fetch the main chunk; if any owned cell sits on a chunk border, also fetch the adjacent chunk(s); decode + union. Returns (owned set, cities map). Uses `mapchunk`.

- [ ] **Step 1: Write failing test** (fake actions returns a chunk with real fixture bytes)

```python
# tests/test_territory_scan.py
import base64
import json
from pathlib import Path
from types import SimpleNamespace

from nta_agent.execution.territory import scan_owned

FX = json.loads(Path("tests/fixtures/mapchunk_real.json").read_text(encoding="utf-8"))


def test_scan_owned_decodes_city_chunk():
    info = {k: base64.b64decode(FX[k]) for k in ("indexs1", "indexs2", "cities")}
    uid = FX["uid"]; main = FX["main_city"]
    calls = []
    def get_map_chunk(cid):
        calls.append(cid)
        return {"cells": {uid: info}} if cid == FX["chunk_id"] else {"cells": {}}
    owned, cities = scan_owned(SimpleNamespace(get_map_chunk=get_map_chunk), main, uid)
    assert len(owned) == FX["land_count"] and main in owned
    assert FX["chunk_id"] in calls
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** in `territory.py`:

```python
def scan_owned(actions, main_index, uid, map_width=600):
    from nta_agent.execution.mapchunk import (CHUNK, chunk_id, chunk_origin,
                                              decode_player_cells)
    uid = str(uid)
    to_fetch = {chunk_id(main_index, map_width)}
    seen, owned, cities = set(), set(), {}
    while to_fetch:
        cid = to_fetch.pop()
        if cid in seen:
            continue
        seen.add(cid)
        reply = actions.get_map_chunk(cid) or {}
        info = (reply.get("cells") or {}).get(uid)
        if not info:
            continue
        ox, oy = chunk_origin(cid, map_width)
        cells, cmap = decode_player_cells(info, ox, oy, map_width)
        owned.update(cells); cities.update(cmap)
        # expand to an adjacent chunk when owned cells touch this chunk's border
        per_row = -(-map_width // CHUNK)
        cx, cy = cid % per_row, cid // per_row
        for i in cells:
            x, y = i % map_width, i // map_width
            if x == ox and cx > 0:
                to_fetch.add(cid - 1)
            if x == ox + CHUNK - 1 and cx < per_row - 1:
                to_fetch.add(cid + 1)
            if y == oy and cy > 0:
                to_fetch.add(cid - per_row)
            if y == oy + CHUNK - 1 and cy < per_row - 1:
                to_fetch.add(cid + per_row)
    return owned, cities
```

- [ ] **Step 4: Run** → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/execution/territory.py tests/test_territory_scan.py && git commit -m "territory: scan_owned (fetch+decode territory chunks, border-adaptive)"`

---

### Task 4: `fort_advisor.recommend_forts` (border-expansion, pure)

**Files:** Create `nta_agent/execution/fort_advisor.py`; Test `tests/test_fort_advisor.py`

**Interfaces:** `recommend_forts(main, owned, forts, map_width=600, max_forts=1, radius=6) -> list[dict]` where `forts` = set of existing fort indices. Returns `[{index, x, y, reason}]`, up to `max_forts - len(forts)` items; candidates are owned cells outside `radius` (Chebyshev) and not forts; ranked by distance from main (frontier) with spread (each pick maximizes min-distance to already-chosen + existing forts).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_fort_advisor.py
from nta_agent.execution.fort_advisor import recommend_forts

W = 600
def idx(x, y): return y * W + x


def test_excludes_within_radius_and_recommends_frontier():
    main = idx(100, 100)
    owned = {main, idx(103, 100), idx(110, 100), idx(112, 100)}  # 3,10,12 away
    recs = recommend_forts(main, owned, forts=set(), max_forts=1)
    assert len(recs) == 1
    # nearest (within radius 6) excluded; frontier-most (12 away) chosen
    assert recs[0]["index"] == idx(112, 100)


def test_respects_cap_and_spreads():
    main = idx(100, 100)
    owned = {main, idx(110, 100), idx(111, 100), idx(100, 110)}
    recs = recommend_forts(main, owned, forts=set(), max_forts=2)
    got = {r["index"] for r in recs}
    assert len(recs) == 2
    # spread: not the two adjacent (110,111) together; includes the other direction
    assert idx(100, 110) in got


def test_no_recs_when_cap_reached_or_all_near():
    main = idx(100, 100)
    assert recommend_forts(main, {main, idx(103, 100)}, forts=set(), max_forts=1) == []  # all within 6
    assert recommend_forts(main, {main, idx(120, 100)}, forts={idx(120, 100)}, max_forts=1) == []  # cap
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**

```python
# nta_agent/execution/fort_advisor.py
"""Deterministic Cứ Điểm placement recommendations (border expansion).

Forts give x3 speed + healing on all city/fort routes, so recommend owned cells
on the territory frontier (outside the main-city speed radius), spread across
directions so you can build one while farming another way."""
from __future__ import annotations


def _pos(i, w):
    return (i % w, i // w)


def _cheb(a, b, w):
    ax, ay = _pos(a, w); bx, by = _pos(b, w)
    return max(abs(ax - bx), abs(ay - by))


def recommend_forts(main, owned, forts, map_width=600, max_forts=1, radius=6):
    forts = set(forts or ())
    slots = max_forts - len(forts)
    if slots <= 0:
        return []
    cands = [i for i in owned
             if i != main and i not in forts and _cheb(main, i, map_width) > radius]
    if not cands:
        return []
    anchors = list(forts) + [main]
    picks = []
    while cands and len(picks) < slots:
        # frontier + spread: maximize (dist from main) + (min dist to anchors/picks)
        def score(i):
            spread = min(_cheb(i, a, map_width) for a in (anchors + picks))
            return (_cheb(main, i, map_width) + spread, _cheb(main, i, map_width))
        best = max(cands, key=score)
        cands.remove(best)
        picks.append(best)
    return [{"index": i, "x": i % map_width, "y": i // map_width,
             "reason": "frontier @dist %d from main" % _cheb(main, i, map_width)}
            for i in picks]
```

- [ ] **Step 4: Run** → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/execution/fort_advisor.py tests/test_fort_advisor.py && git commit -m "execution: fort placement advisor (frontier + spread)"`

---

### Task 5: runtime scan step (landCount-triggered) + config path

**Files:** Modify `nta_agent/runtime/config.py`, `nta_agent/runtime/runner.py`; Create `nta_agent/runtime/fort_service.py`; Test `tests/test_fort_service.py`

**Interfaces:** `RuntimeConfig.forts_path` = `log_dir/forts.json`. `FortService(actions, cfg, config=None, on_event=None)` with `tick(state)`: only when `state.raw.player.landCount` differs from the last scan → `scan_owned` + `recommend_forts` (cap from `config.max_count(2102)`) → write `forts.json {owned_count, recommendations}`. Swallows errors.

- [ ] **Step 1: Write failing test**

```python
# tests/test_fort_service.py
import base64, json
from pathlib import Path
from types import SimpleNamespace

from nta_agent.runtime.fort_service import FortService

FX = json.loads(Path("tests/fixtures/mapchunk_real.json").read_text(encoding="utf-8"))


def _state(land_count):
    return SimpleNamespace(main_city_index=FX["main_city"],
                           user=SimpleNamespace(uid=FX["uid"]),
                           raw={"player": {"landCount": land_count}})


def test_scans_only_when_landcount_changes(tmp_path):
    info = {k: base64.b64decode(FX[k]) for k in ("indexs1", "indexs2", "cities")}
    calls = []
    actions = SimpleNamespace(get_map_chunk=lambda cid: (calls.append(cid) or
                              ({"cells": {FX["uid"]: info}} if cid == FX["chunk_id"] else {"cells": {}})))
    cfg = SimpleNamespace(forts_path=tmp_path / "forts.json")
    config = SimpleNamespace(max_count=lambda _id: 3)
    svc = FortService(actions, cfg, config=config)
    svc.tick(_state(23))                       # first scan
    assert calls, "should scan on first landCount"
    n1 = len(calls)
    svc.tick(_state(23))                       # unchanged -> no scan
    assert len(calls) == n1
    svc.tick(_state(24))                       # changed -> scan again
    assert len(calls) > n1
    data = json.loads(Path(cfg.forts_path).read_text(encoding="utf-8"))
    assert data["owned_count"] == 23 and "recommendations" in data
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**
  - `config.py`: add `forts_path` property → `self.log_dir / "forts.json"`.
  - `fort_service.py`:
```python
"""Sparse territory scan -> fort recommendations (only when landCount changes)."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

FORT_BUILD_ID = 2102


class FortService:
    def __init__(self, actions, cfg, config=None, on_event=None):
        self.actions = actions
        self.cfg = cfg
        self.config = config
        self._on_event = on_event or (lambda *a: None)
        self._last_land = None

    def tick(self, state) -> None:
        player = (getattr(state, "raw", None) or {}).get("player", {}) or {}
        land = player.get("landCount")
        if land is None or land == self._last_land:
            return
        try:
            from nta_agent.execution.fort_advisor import recommend_forts
            from nta_agent.execution.territory import build_territory, scan_owned
            uid = state.user.uid
            main = state.main_city_index
            owned, cities = scan_owned(self.actions, main, uid)
            terr = build_territory(state)
            forts = {f.index for f in terr.forts}
            cap = self.config.max_count(FORT_BUILD_ID) if self.config else 1
            recs = recommend_forts(main, owned, forts, max_forts=cap)
            self._write({"owned_count": len(owned), "forts": sorted(forts),
                         "recommendations": recs})
            self._last_land = land
            self._on_event("fort_scan", {"owned": len(owned), "recs": len(recs)})
        except Exception as e:  # never block the loop
            sys.stderr.write(f"[fort] scan failed: {e}\n")

    def _write(self, data):
        p = Path(self.cfg.forts_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
```
  - `runner.py`: build `FortService(agent.actions, cfg, config=config, on_event=log.append)` and call `_safe(fort.tick, state)` in `on_tick` (after brain).

- [ ] **Step 4: Run** `pytest tests/test_fort_service.py -q` → PASS; full suite + ruff.
- [ ] **Step 5: Commit** `git add nta_agent/runtime/config.py nta_agent/runtime/fort_service.py nta_agent/runtime/runner.py tests/test_fort_service.py && git commit -m "runtime: FortService (landCount-triggered territory scan + fort recs)"`

---

### Task 6: dashboard `/api/forts` + "Cứ Điểm — gợi ý" panel

**Files:** Modify `nta_agent/dashboard/server.py`, `nta_agent/dashboard/page.py`; Test `tests/test_dashboard_forts.py`, `tests/test_dashboard_page.py` (extend)

**Interfaces:** `GET /api/forts` returns `forts.json` (or `{owned_count:0, recommendations:[]}` when absent). Page has a "Cứ Điểm — gợi ý" panel listing recs (index/pos/reason) + owned count.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dashboard_forts.py
import json
from pathlib import Path
from nta_agent.dashboard.server import read_forts_view
from nta_agent.runtime.config import RuntimeConfig


def test_read_forts_view(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    Path(cfg.forts_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.forts_path).write_text(json.dumps({
        "owned_count": 23, "forts": [], "recommendations": [
            {"index": 112300, "x": 100, "y": 187, "reason": "frontier @dist 12 from main"}]}),
        encoding="utf-8")
    v = read_forts_view(cfg)
    assert v["owned_count"] == 23 and v["recommendations"][0]["index"] == 112300


def test_read_forts_view_missing(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    assert read_forts_view(cfg) == {"owned_count": 0, "forts": [], "recommendations": []}
```

```python
# tests/test_dashboard_page.py (add)
def test_page_has_forts_panel():
    from nta_agent.dashboard.page import INDEX_HTML
    assert "/api/forts" in INDEX_HTML
    assert 'id="forts"' in INDEX_HTML
    assert "Cứ Điểm" in INDEX_HTML
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**
  - `server.py`: `read_forts_view(cfg)`:
```python
def read_forts_view(cfg) -> dict:
    from nta_agent.dashboard.data import read_state  # reuse the tolerant JSON reader
    try:
        import json
        from pathlib import Path
        return json.loads(Path(cfg.forts_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"owned_count": 0, "forts": [], "recommendations": []}
```
  and `do_GET`: `elif parsed.path == "/api/forts": self._json(200, read_forts_view(cfg))`.
  - `page.py`: add card `<div class="card full"><h2>Cứ Điểm — gợi ý</h2><div id="forts" class="muted">—</div></div>` and JS `async function renderForts(){const f=await j("/api/forts");if(!f)return;const recs=(f.recommendations||[]).map(r=>`Xây @${r.index} (${r.x},${r.y}) — ${r.reason}`).join("<br>")||"(chưa có gợi ý)";document.getElementById("forts").innerHTML=`Ô sở hữu: <b>${f.owned_count||0}</b> · Fort: <b>${(f.forts||[]).length}</b><div style=margin-top:6px>${recs}</div>`;}` + call on load + inside refresh.

- [ ] **Step 4: Run** both test files → PASS; full suite + ruff.
- [ ] **Step 5: Commit** `git add nta_agent/dashboard/server.py nta_agent/dashboard/page.py tests/test_dashboard_forts.py tests/test_dashboard_page.py && git commit -m "dashboard: /api/forts + Cứ Điểm gợi ý panel"`

---

## Self-Review

**Spec coverage:** §2 decode → Task 1 (golden); get_map_chunk → Task 2; §3 sparse scan → Tasks 3,5; advisor → Task 4; surface → Task 6. §6 edge (empty bytes, unchanged landCount, cap, no candidates) → Tasks 1,3,4,5 tests. Non-goals (auto-build, relay range, full crawl, brain) excluded. Covered.

**Placeholder scan:** No TBD; every step has runnable code/tests. Decoders are the spike-verified implementation. Task 5/6 give concrete wiring.

**Type consistency:** `decode_player_cells(info, ox, oy, w) -> (list, dict)` (T1) used by `scan_owned` (T3). `scan_owned(actions, main, uid, w) -> (set, dict)` (T3) used by FortService (T5). `recommend_forts(main, owned, forts, map_width, max_forts, radius) -> [{index,x,y,reason}]` (T4) used by T5. `forts_path` (T5) read by T6. `get_map_chunk(cid) -> {cells}` (T2) used by T3. Chunk math (`chunk_id`/`chunk_origin`) consistent (T1) across T3.
