# Territory model (Tier A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pure Territory model (main city, forts, garrisons + geometry helpers) built from player state fields, surfaced on the dashboard — the foundation for the C2 fort-placement advisor.

**Architecture:** `territory.build_territory(state)` reads `player.{mainCityIndex,fortAutoSupports,armyDists,buildCitys}` into a `Territory` with `pos/dist/near_main` helpers. The snapshot carries forts/garrisons/map_width; the dashboard adds a "Lãnh thổ" panel + `/api/territory`. Deterministic; no chunk decode.

**Tech Stack:** Python 3.12 (`.venv/Scripts/python.exe`), pytest, ruff. Touches execution/territory (new), runtime/snapshot, dashboard/server + page.

**Spec:** `docs/superpowers/specs/2026-09-16-territory-model-design.md`

## Global Constraints

- Lint `ruff check nta_agent tests`; test `.venv/Scripts/python.exe -m pytest -q`.
- Cell position: `x = index % map_width`, `y = index // map_width`; default `map_width = 600`.
- Distance metric: **Chebyshev** (`max(|dx|,|dy|)`); `near_main(index, radius=6)` = `dist(main, index) <= radius`.
- Forts = `player.fortAutoSupports` (`[{index, val}]`); garrisons = `player.armyDists` indices; main = `player.mainCityIndex`.
- Pure model (no network); reads `state.raw`. Snapshot stays JSON-safe.
- Commit proactively per green task; finish flow = push → PR → merge.

---

### Task 1: `territory.py` — Territory model + geometry

**Files:** Create `nta_agent/execution/territory.py`; Test `tests/test_territory.py`

**Interfaces:**
- `Fort` dataclass: `index: int`, `auto_support: bool`.
- `Territory` dataclass: `main_city: int`, `forts: list[Fort]`, `garrisons: list[int]`, `map_width: int`; methods `pos(index) -> tuple[int,int]`, `dist(a, b) -> int` (Chebyshev), `near_main(index, radius=6) -> bool`, `nodes() -> list[int]` (main + fort indices).
- `build_territory(state, map_width=600) -> Territory` — reads `state.raw["player"]`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_territory.py
from nta_agent.execution.territory import Fort, Territory, build_territory
from nta_agent.state.schema import GameState


def _state(player):
    st = GameState(source="api")
    st.raw = {"player": player}
    st.main_city_index = player.get("mainCityIndex", 0)
    return st


def test_build_territory_from_player_fields():
    W = 600
    main = 100 * W + 100
    st = _state({
        "mainCityIndex": main,
        "fortAutoSupports": [{"index": main + 10, "val": True},
                             {"index": main + 20, "val": False}],
        "armyDists": [{"index": main, "armys": []},
                      {"index": main + 10, "armys": [{"uid": "a"}]}],
        "buildCitys": {str(main): {}},
    })
    t = build_territory(st, map_width=W)
    assert t.main_city == main and t.map_width == W
    assert Fort(index=main + 10, auto_support=True) in t.forts
    assert Fort(index=main + 20, auto_support=False) in t.forts
    assert main in t.garrisons and (main + 10) in t.garrisons
    assert set(t.nodes()) == {main, main + 10, main + 20}


def test_geometry_pos_dist_near_main():
    W = 600
    main = 100 * W + 100
    t = Territory(main_city=main, forts=[], garrisons=[], map_width=W)
    assert t.pos(main) == (100, 100)
    # cell 5 right, 3 down -> Chebyshev dist 5
    other = (103) * W + 105
    assert t.dist(main, other) == 5
    assert t.near_main(other, radius=6) is True
    far = (110) * W + 100  # 10 down -> dist 10
    assert t.near_main(far, radius=6) is False


def test_empty_player_builds_empty_territory():
    t = build_territory(_state({}), map_width=600)
    assert t.forts == [] and t.garrisons == [] and t.main_city == 0
```

- [ ] **Step 2: Run** → FAIL (`.venv/Scripts/python.exe -m pytest tests/test_territory.py -q`).
- [ ] **Step 3: Implement**

```python
# nta_agent/execution/territory.py
"""Own-territory model (main city, forts, garrisons) + geometry — Tier A.

Built cheaply from player state fields (no packed-chunk decode). Foundation for
the fort-placement advisor (C2)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Fort:
    index: int
    auto_support: bool


@dataclass
class Territory:
    main_city: int
    forts: list = field(default_factory=list)
    garrisons: list = field(default_factory=list)
    map_width: int = 600

    def pos(self, index: int) -> tuple[int, int]:
        return (index % self.map_width, index // self.map_width)

    def dist(self, a: int, b: int) -> int:
        ax, ay = self.pos(a)
        bx, by = self.pos(b)
        return max(abs(ax - bx), abs(ay - by))  # Chebyshev

    def near_main(self, index: int, radius: int = 6) -> bool:
        return self.dist(self.main_city, index) <= radius

    def nodes(self) -> list:
        return [self.main_city] + [f.index for f in self.forts]


def build_territory(state, map_width: int = 600) -> Territory:
    player = (getattr(state, "raw", None) or {}).get("player", {}) or {}
    main = int(player.get("mainCityIndex", 0) or 0)
    forts = [Fort(index=int(f.get("index", 0)), auto_support=bool(f.get("val")))
             for f in (player.get("fortAutoSupports") or []) if isinstance(f, dict)]
    garrisons = [int(d.get("index", 0)) for d in (player.get("armyDists") or [])
                 if isinstance(d, dict)]
    return Territory(main_city=main, forts=forts, garrisons=garrisons, map_width=map_width)
```

- [ ] **Step 4: Run** → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/execution/territory.py tests/test_territory.py && git commit -m "execution: Territory model (own forts/garrisons + geometry)"`

---

### Task 2: snapshot carries forts / garrisons / map_width

**Files:** Modify `nta_agent/runtime/snapshot.py`; Test `tests/test_snapshot_territory.py` (create)

**Interfaces:** `state_to_dict` adds `forts: [{index, auto_support}]`, `garrisons: [int]`, `map_width: int` (from the world map size when available, else 600). Reuses `build_territory`.

- [ ] **Step 1: Write failing test**

```python
# tests/test_snapshot_territory.py
from nta_agent.runtime.snapshot import state_to_dict
from nta_agent.state.schema import GameState


def test_snapshot_includes_territory():
    st = GameState(source="api")
    st.main_city_index = 60100
    st.raw = {"player": {"mainCityIndex": 60100,
                         "fortAutoSupports": [{"index": 60110, "val": True}],
                         "armyDists": [{"index": 60100, "armys": []}]}}
    d = state_to_dict(st)
    assert d["forts"] == [{"index": 60110, "auto_support": True}]
    assert d["garrisons"] == [60100]
    assert d["map_width"] >= 1
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — in `snapshot.py`, import `build_territory`; in `state_to_dict`, after building the base dict, add:

```python
    from nta_agent.execution.territory import build_territory
    mw = int(getattr(state, "map_width", 0) or 0) or 600
    terr = build_territory(state, map_width=mw)
    d["forts"] = [{"index": f.index, "auto_support": f.auto_support} for f in terr.forts]
    d["garrisons"] = terr.garrisons
    d["map_width"] = terr.map_width
    return d
```
(`GameState` has no `map_width` field; `getattr(..., 0)` → 600 fallback. If a real map width is later stored on the state, this picks it up.)

- [ ] **Step 4: Run** → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/runtime/snapshot.py tests/test_snapshot_territory.py && git commit -m "snapshot: carry forts/garrisons/map_width"`

---

### Task 3: dashboard `/api/territory` + panel

**Files:** Modify `nta_agent/dashboard/server.py`, `nta_agent/dashboard/page.py`; Test `tests/test_dashboard_territory.py` (create), `tests/test_dashboard_page.py` (extend)

**Interfaces:** `read_territory_view(cfg) -> dict` = `{main_city, forts:[{index,auto_support,x,y}], garrisons:[int], map_width}` from the snapshot. `GET /api/territory` returns it. Page has a "Lãnh thổ" panel.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dashboard_territory.py
import json
from pathlib import Path
from nta_agent.dashboard.server import read_territory_view
from nta_agent.runtime.config import RuntimeConfig


def test_read_territory_view_from_snapshot(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    Path(cfg.snapshot_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.snapshot_path).write_text(json.dumps({
        "ok": True, "main_city_index": 60100, "map_width": 600,
        "forts": [{"index": 60110, "auto_support": True}], "garrisons": [60100]}),
        encoding="utf-8")
    v = read_territory_view(cfg)
    assert v["main_city"] == 60100
    assert v["forts"][0]["index"] == 60110 and v["forts"][0]["auto_support"] is True
    assert v["forts"][0]["x"] == 60110 % 600 and v["forts"][0]["y"] == 60110 // 600
    assert v["garrisons"] == [60100]
```

```python
# tests/test_dashboard_page.py (add)
def test_page_has_territory_panel():
    from nta_agent.dashboard.page import INDEX_HTML
    assert "/api/territory" in INDEX_HTML
    assert 'id="territory"' in INDEX_HTML
    assert "Lãnh thổ" in INDEX_HTML
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**
  - `server.py` `read_territory_view`:
```python
def read_territory_view(cfg) -> dict:
    st = read_state(cfg.snapshot_path)
    mw = int(st.get("map_width") or 600)
    forts = [{"index": f["index"], "auto_support": f.get("auto_support", False),
              "x": f["index"] % mw, "y": f["index"] // mw}
             for f in (st.get("forts") or [])]
    return {"main_city": st.get("main_city_index", 0), "forts": forts,
            "garrisons": st.get("garrisons") or [], "map_width": mw}
```
  - `do_GET`: add `elif parsed.path == "/api/territory": self._json(200, read_territory_view(cfg))`.
  - `page.py`: add a card `<div class="card full"><h2>Lãnh thổ</h2><div id="territory" class="muted">—</div></div>` (near the build-order card) and JS: `async function renderTerritory(){const t=await j("/api/territory");if(!t)return;const forts=(t.forts||[]).map(f=>`Cứ Điểm @${f.index} (${f.x},${f.y})${f.auto_support?" ⛨":""}`).join("<br>")||"—";document.getElementById("territory").innerHTML=`Thành chính: <b>${t.main_city||"?"}</b> · Quân trú: <b>${(t.garrisons||[]).length}</b><div style=margin-top:6px>${forts}</div>`;}` and call `renderTerritory()` on load + inside `refresh()`.

- [ ] **Step 4: Run** both test files → PASS; full suite + ruff.
- [ ] **Step 5: Commit** `git add nta_agent/dashboard/server.py nta_agent/dashboard/page.py tests/test_dashboard_territory.py tests/test_dashboard_page.py && git commit -m "dashboard: /api/territory + Lãnh thổ panel"`

---

## Self-Review

**Spec coverage:** §4 territory.py → Task 1; snapshot fields → Task 2; /api/territory + panel → Task 3. §8 tests → each task. Geometry (Chebyshev, radius-6) → Task 1 tests. Non-goals (Tier B, advisor, auto-build) excluded. Covered.

**Placeholder scan:** No TBD; all steps have runnable code. Task 2 notes the `map_width` fallback rationale. Task 3 gives concrete server + page edits.

**Type consistency:** `Territory{main_city,forts:list[Fort],garrisons,map_width}` + `Fort{index,auto_support}` (Task 1) used by snapshot (Task 2) and view (Task 3). `build_territory(state, map_width)` signature consistent. `/api/territory` payload keys (`main_city/forts/garrisons/map_width`) consistent between `read_territory_view` and the page JS.
