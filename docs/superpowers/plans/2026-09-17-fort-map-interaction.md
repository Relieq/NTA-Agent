# Interactive Territory Map (D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add coordinate rulers to the territory map and let the user accept/reject fort recommendations from the map and the panel — persisted and honored by the advisor, recomputed instantly with no game request.

**Architecture:** A pure `plan_forts()` (shared by the periodic `FortService` and an instant dashboard recompute) turns owned cells + user decisions into recommendations + accepted forts. Decisions live in `fort_decisions.json`; a `POST /api/forts/decide` writes one and rewrites `forts.json`. The Vue `TerritoryPanel` draws rulers + clickable recs; `FortsPanel` has decision buttons.

**Tech Stack:** Python 3.12 stdlib; Vue 3 (vendored, no-build); `<canvas>` 2D.

**Spec:** `docs/superpowers/specs/2026-09-17-fort-map-interaction-design.md`

## Global Constraints

- Decisions never trigger a game request — recompute from the already-persisted `owned_cells`.
- No decisions file → behavior identical to today.
- `accept` = planned fort (excluded from candidates, spread anchor, counts toward the `max_count(2102)` cap). `reject` = never recommend. `clear` = undo.
- `fort_decisions.json` shape: `{"<index>": "accepted"|"rejected"}`.
- Tests: `.venv/Scripts/python.exe -m pytest -q`; lint `.venv/Scripts/python.exe -m ruff check nta_agent tests`.
- Commit footer on every commit:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_017SWX7TP9uSdjA1HbV883Tm`.

---

### Task 1: Advisor — `rejected` + `plan_forts`

**Files:**
- Modify: `nta_agent/execution/fort_advisor.py`
- Test: `tests/test_fort_advisor.py` (extend)

**Interfaces:**
- Produces: `recommend_forts(..., rejected=None)` (also excludes `rejected`); `plan_forts(main, owned, existing_forts, decisions, cap, map_width=600, radius=6) -> (recs:list[dict], accepted:list[int])`.

- [ ] **Step 1: Write the failing test** (append)

```python
def test_recommend_forts_excludes_rejected():
    main = 100 * 600 + 100
    owned = {120 * 600 + 100, 100 * 600 + 120}
    recs = recommend_forts(main, owned, forts=[], rejected={120 * 600 + 100},
                           map_width=600, max_forts=2, radius=6)
    idxs = {r["index"] for r in recs}
    assert 120 * 600 + 100 not in idxs
    assert 100 * 600 + 120 in idxs


def test_plan_forts_accept_is_anchor_excluded_and_counts_cap():
    from nta_agent.execution.fort_advisor import plan_forts
    main = 100 * 600 + 100
    a = 120 * 600 + 100           # will be accepted
    owned = {a, 100 * 600 + 120, 80 * 600 + 100}
    recs, accepted = plan_forts(main, owned, existing_forts=[],
                                decisions={a: "accepted"}, cap=2, map_width=600)
    assert accepted == [a]
    idxs = {r["index"] for r in recs}
    assert a not in idxs                    # accepted excluded from candidates
    assert len(recs) <= 1                   # cap 2 - 1 accepted = 1 slot


def test_plan_forts_reject_excluded():
    from nta_agent.execution.fort_advisor import plan_forts
    main = 100 * 600 + 100
    r = 120 * 600 + 100
    owned = {r, 100 * 600 + 120}
    recs, accepted = plan_forts(main, owned, existing_forts=[],
                                decisions={r: "rejected"}, cap=5, map_width=600)
    assert accepted == []
    assert r not in {x["index"] for x in recs}


def test_plan_forts_no_decisions_matches_recommend():
    from nta_agent.execution.fort_advisor import plan_forts
    main = 100 * 600 + 100
    owned = {120 * 600 + 100, 100 * 600 + 120}
    recs, accepted = plan_forts(main, owned, existing_forts=[], decisions={},
                                cap=5, map_width=600)
    base = recommend_forts(main, owned, forts=[], map_width=600, max_forts=5, radius=6)
    assert [r["index"] for r in recs] == [r["index"] for r in base]
    assert accepted == []
```

- [ ] **Step 2: Run → FAIL.** `.venv/Scripts/python.exe -m pytest tests/test_fort_advisor.py -q`

- [ ] **Step 3: Implement** — add `rejected` to `recommend_forts` and append `plan_forts`:

In `recommend_forts`, after `fort_set = {...}` add:
```python
    rej_set = {int(r) for r in (rejected or [])}
```
change the signature line to include `rejected=None,` (before `map_width`), and add to the candidate filter:
```python
        and int(c) not in rej_set
```
Append:
```python
def plan_forts(main, owned, existing_forts, decisions, cap,
               map_width: int = 600, radius: int = 6):
    """Turn owned cells + user decisions into (recommendations, accepted indices).

    ``decisions`` maps a cell index to "accepted" or "rejected". Accepted cells are
    planned forts: excluded from candidates, used as spread anchors, and counted
    against ``cap``. Rejected cells are never recommended.
    """
    accepted = [int(i) for i, d in decisions.items() if d == "accepted"]
    rejected = [int(i) for i, d in decisions.items() if d == "rejected"]
    anchors = [int(f) for f in (existing_forts or [])] + accepted
    slots = max(0, int(cap) - len(anchors))
    recs = recommend_forts(main, owned, forts=anchors, rejected=rejected,
                           map_width=map_width, max_forts=slots, radius=radius)
    return recs, accepted
```

- [ ] **Step 4: Run + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_fort_advisor.py -q` → PASS.
```bash
git add nta_agent/execution/fort_advisor.py tests/test_fort_advisor.py
git commit -m "feat(fort-advisor): rejected exclusion + plan_forts(decisions)"
```

---

### Task 2: Decisions store + config + fort_service wiring

**Files:**
- Create: `nta_agent/runtime/fort_decisions.py`
- Modify: `nta_agent/runtime/config.py` (`fort_decisions_path`)
- Modify: `nta_agent/runtime/fort_service.py` (use `plan_forts` + decisions; write `accepted`)
- Test: `tests/test_fort_decisions.py`, extend `tests/test_fort_service.py`

**Interfaces:**
- Produces: `fort_decisions.load(path) -> dict[int,str]`; `fort_decisions.update(path, index, decision) -> dict` (decision ∈ accept|reject|clear|accepted|rejected). `cfg.fort_decisions_path`. `forts.json` gains `accepted: [[x,y],...]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fort_decisions.py
from nta_agent.runtime import fort_decisions as fd


def test_load_missing_is_empty(tmp_path):
    assert fd.load(tmp_path / "none.json") == {}


def test_update_accept_reject_clear(tmp_path):
    p = tmp_path / "d.json"
    assert fd.update(p, 5, "accept") == {5: "accepted"}
    assert fd.update(p, 6, "reject") == {5: "accepted", 6: "rejected"}
    assert fd.update(p, 5, "clear") == {6: "rejected"}
    assert fd.load(p) == {6: "rejected"}
```
Append to `tests/test_fort_service.py`:
```python
def test_forts_json_respects_decisions(tmp_path):
    from nta_agent.runtime import fort_decisions as fd
    owned = {120 * 600 + 100, 100 * 600 + 120}

    def scan(actions, main, uid, map_width=600, focus=None):
        return set(owned), {}

    cfg, svc = _make(tmp_path, scan=scan, max_count_fn=lambda bid: 3)
    fd.update(cfg.fort_decisions_path, 120 * 600 + 100, "accept")
    fd.update(cfg.fort_decisions_path, 100 * 600 + 120, "reject")
    svc.tick(_state(land_count=2))
    data = json.loads(cfg.forts_path.read_text(encoding="utf-8"))
    assert [100, 120] not in [ [r["x"], r["y"]] for r in data["recommendations"] ]  # rejected gone
    assert [100, 120] not in data["accepted"]
    assert [100, 120] != None  # noqa
    assert [ [100, 120] ] != data["accepted"]
    assert [100 + 20, 100] not in [ [r["x"], r["y"]] for r in data["recommendations"] ]  # accepted gone from recs
    assert [120, 100] in data["accepted"]
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `fort_decisions.py`**

```python
# nta_agent/runtime/fort_decisions.py
"""Persisted user decisions on fort recommendations (accept/reject)."""
from __future__ import annotations

import json
from pathlib import Path


def load(path) -> dict:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(d, dict):
        return {}
    return {int(k): v for k, v in d.items() if v in ("accepted", "rejected")}


def update(path, index, decision) -> dict:
    d = load(path)
    idx = int(index)
    if decision in ("clear", "none"):
        d.pop(idx, None)
    elif decision in ("accept", "accepted"):
        d[idx] = "accepted"
    elif decision in ("reject", "rejected"):
        d[idx] = "rejected"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({str(k): v for k, v in d.items()}), encoding="utf-8")
    return d
```

- [ ] **Step 4: Add config path**

```python
    @property
    def fort_decisions_path(self) -> Path:
        return self.log_dir / "fort_decisions.json"
```

- [ ] **Step 5: Wire `fort_service`** — replace the recs block:

Add import at top: `from nta_agent.execution.fort_advisor import plan_forts` and `from nta_agent.runtime import fort_decisions`. Replace lines that compute `slots`/`recs` and build `payload`:
```python
            decisions = fort_decisions.load(self.cfg.fort_decisions_path)
            recs, accepted = plan_forts(main, owned, fort_indices, decisions,
                                        self._max_forts(), map_width=self.map_width,
                                        radius=self.radius)
            mw = self.map_width
            cells = sorted([c % mw, c // mw] for c in owned)
            accepted_coords = sorted([i % mw, i // mw] for i in accepted)
            payload = {"owned_count": len(owned), "owned_cells": cells,
                       "accepted": accepted_coords, "recommendations": recs}
```
(Keep the file-write + `fort_scan` event; the `self._recommend` attribute may stay unused or be removed — leave it to avoid churn.)

- [ ] **Step 6: Run + lint + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_fort_decisions.py tests/test_fort_service.py -q` → PASS.
```bash
.venv/Scripts/python.exe -m ruff check nta_agent/runtime tests/test_fort_decisions.py tests/test_fort_service.py
git add nta_agent/runtime/fort_decisions.py nta_agent/runtime/config.py nta_agent/runtime/fort_service.py tests/test_fort_decisions.py tests/test_fort_service.py
git commit -m "feat(fort-service): honor accept/reject decisions; write accepted"
```

---

### Task 3: `recompute_forts` + `/api/forts/decide` + accepted in view

**Files:**
- Modify: `nta_agent/dashboard/server.py`
- Test: `tests/test_dashboard_forts.py` (extend), `tests/test_dashboard_decide.py` (new)

**Interfaces:**
- Consumes: `plan_forts`, `fort_decisions`, `read_territory_view`.
- Produces: `recompute_forts(cfg) -> dict` (rewrites forts.json from owned_cells + snapshot + decisions, no game request); `POST /api/forts/decide {index, decision}`; `read_forts_view` includes `accepted`.

- [ ] **Step 1: Write the failing tests**

Extend `tests/test_dashboard_forts.py` (the existing view test already writes forts.json — add `accepted`):
```python
def test_read_forts_view_includes_accepted(tmp_path):
    from nta_agent.dashboard.server import read_forts_view
    from nta_agent.runtime.config import RuntimeConfig
    import json
    from pathlib import Path
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    Path(cfg.forts_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.forts_path).write_text(json.dumps({
        "owned_count": 1, "owned_cells": [[120, 100]],
        "accepted": [[120, 100]], "recommendations": []}), encoding="utf-8")
    v = read_forts_view(cfg)
    assert v["accepted"] == [[120, 100]]
```
New `tests/test_dashboard_decide.py`:
```python
import json
from pathlib import Path

from nta_agent.dashboard.server import recompute_forts
from nta_agent.runtime.config import RuntimeConfig


def _setup(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    Path(cfg.snapshot_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.snapshot_path).write_text(json.dumps({
        "ok": True, "main_city_index": 100 * 600 + 100, "map_width": 600,
        "forts": [], "garrisons": []}), encoding="utf-8")
    Path(cfg.forts_path).write_text(json.dumps({
        "owned_count": 2, "owned_cells": [[120, 100], [100, 120]],
        "accepted": [], "recommendations": []}), encoding="utf-8")
    return cfg


def test_recompute_reflects_reject(tmp_path):
    from nta_agent.runtime import fort_decisions as fd
    cfg = _setup(tmp_path)
    fd.update(cfg.fort_decisions_path, 120 * 600 + 100, "reject")
    out = recompute_forts(cfg)
    assert [120, 100] not in [[r["x"], r["y"]] for r in out["recommendations"]]


def test_recompute_reflects_accept(tmp_path):
    from nta_agent.runtime import fort_decisions as fd
    cfg = _setup(tmp_path)
    fd.update(cfg.fort_decisions_path, 120 * 600 + 100, "accept")
    out = recompute_forts(cfg)
    assert [120, 100] in out["accepted"]
    assert [120, 100] not in [[r["x"], r["y"]] for r in out["recommendations"]]
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** — in `server.py`:

`read_forts_view` return dict: add `"accepted": data.get("accepted") or [],` (both the success and the missing-file branch → `"accepted": []`).

Add helper (near `read_forts_view`):
```python
def recompute_forts(cfg) -> dict:
    """Rewrite forts.json from its owned_cells + snapshot + decisions. No game I/O."""
    from nta_agent.execution.fort_advisor import plan_forts
    from nta_agent.runtime import fort_decisions
    try:
        fdj = json.loads(Path(cfg.forts_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fdj = {}
    cells = fdj.get("owned_cells") or []
    terr = read_territory_view(cfg)
    mw = int(terr.get("map_width") or 600)
    owned = [int(y) * mw + int(x) for x, y in cells]
    main = int(terr.get("main_city") or 0)
    existing = [int(f["index"]) for f in terr.get("forts", [])]
    decisions = fort_decisions.load(cfg.fort_decisions_path)
    try:
        cap = GameConfig.load().max_count(2102)
    except Exception:
        cap = 1
    recs, accepted = plan_forts(main, owned, existing, decisions, cap, map_width=mw)
    payload = {"owned_count": len(owned), "owned_cells": cells,
               "accepted": sorted([i % mw, i // mw] for i in accepted),
               "recommendations": recs}
    Path(cfg.forts_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.forts_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    return payload
```
Add the import for `GameConfig` at the top of `server.py` if absent:
`from nta_agent.data.config import GameConfig`.

Add the POST route (in `do_POST`, after the `/api/agent/` block):
```python
        if parsed.path == "/api/forts/decide":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                idx = int(body["index"]); decision = str(body.get("decision", ""))
            except (ValueError, TypeError, KeyError):
                self._json(400, {"ok": False, "error": "need index + decision"})
                return
            from nta_agent.runtime import fort_decisions
            fort_decisions.update(cfg.fort_decisions_path, idx, decision)
            self._json(200, recompute_forts(cfg))
            return
```

- [ ] **Step 4: Run + lint + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_forts.py tests/test_dashboard_decide.py -q` → PASS.
```bash
.venv/Scripts/python.exe -m ruff check nta_agent/dashboard/server.py tests/test_dashboard_decide.py
git add nta_agent/dashboard/server.py tests/test_dashboard_forts.py tests/test_dashboard_decide.py
git commit -m "feat(dashboard): /api/forts/decide + recompute_forts; accepted in view"
```

---

### Task 4: FE — coordinate rulers + clickable recs + accepted marker

**Files:**
- Modify: `nta_agent/dashboard/static/components/TerritoryPanel.js`
- Test: extend `tests/test_dashboard_components.py`

**Interfaces:**
- Consumes: `getJSON`, `postJSON`, `usePolling`. Draws rulers + accepted + rec rings; canvas click hit-tests the nearest pending rec → popover → `POST /api/forts/decide` → redraw.

- [ ] **Step 1: Add failing assertions**

```python
def test_territory_map_has_rulers_and_decisions():
    terr = _c("TerritoryPanel.js")
    assert "fillText" in terr                 # coordinate ruler labels
    assert "accepted" in terr                 # renders accepted forts
    assert "/api/forts/decide" in terr        # click -> decide
    assert "getBoundingClientRect" in terr    # canvas click hit-test
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Rewrite `TerritoryPanel.js`** (rulers via margins, accepted marker, click hit-test + popover)

```js
// nta_agent/dashboard/static/components/TerritoryPanel.js
import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
const idxXY=(i,mw)=>[i%mw, Math.floor(i/mw)];
const ML=26, MT=16;  // left/top margins reserved for rulers
export default {
 setup(){
  const canvas=ref(null), summary=ref("—"), legend=ref("");
  const geom=ref(null);            // {minX,minY,cell,ox,oy,mw} for hit-testing
  const recs=ref([]);              // pending recs [{index,x,y,reason}]
  const sel=ref(null);             // selected rec + popover position
  async function draw(){
   const t=await getJSON("/api/territory"), f=await getJSON("/api/forts");
   if(!t||!f) return;
   recs.value=f.recommendations||[];
   summary.value=`Thành chính: ${t.main_city||"?"} · Quân trú: ${(t.garrisons||[]).length}`;
   const cv=canvas.value; if(!cv) return;
   const ctx=cv.getContext("2d"), W=cv.width, H=cv.height; ctx.clearRect(0,0,W,H);
   const mw=t.map_width||600, main=t.main_city||0;
   if(!main){ legend.value="Chưa có dữ liệu bản đồ."; geom.value=null; return; }
   const [mx,my]=idxXY(main,mw);
   const owned=f.owned_cells||[];
   const accepted=f.accepted||[];
   const fpts=(t.forts||[]).map(x=>[x.x,x.y]);
   const garr=(t.garrisons||[]).map(i=>idxXY(i,mw));
   const rpts=recs.value.map(r=>[r.x,r.y]);
   const R=6;
   const pts=[[mx,my],...owned,...accepted,...fpts,...garr,...rpts,[mx-R,my-R],[mx+R,my+R]];
   const minX=Math.min(...pts.map(p=>p[0]))-1, maxX=Math.max(...pts.map(p=>p[0]))+1;
   const minY=Math.min(...pts.map(p=>p[1]))-1, maxY=Math.max(...pts.map(p=>p[1]))+1;
   const cols=maxX-minX+1, rows=maxY-minY+1;
   const cell=Math.max(3,Math.floor(Math.min((W-ML)/cols,(H-MT)/rows)));
   const ox=ML+Math.floor((W-ML-cols*cell)/2), oy=MT+Math.floor((H-MT-rows*cell)/2);
   geom.value={minX,minY,cell,ox,oy,mw};
   const gx=x=>ox+(x-minX)*cell, gy=y=>oy+(y-minY)*cell;
   const box=(x,y,c)=>{ ctx.fillStyle=c; ctx.fillRect(gx(x)+1,gy(y)+1,cell-2,cell-2); };
   // rulers: adaptive step so labels are ~>=34px apart
   const step=Math.max(1,Math.ceil(34/cell));
   ctx.fillStyle="#8b949e"; ctx.font="10px ui-monospace,Consolas,monospace";
   ctx.textAlign="center"; ctx.textBaseline="alphabetic";
   for(let x=minX; x<=maxX; x++){ if((x-minX)%step===0) ctx.fillText(String(x), gx(x)+cell/2, MT-4); }
   ctx.textAlign="right"; ctx.textBaseline="middle";
   for(let y=minY; y<=maxY; y++){ if((y-minY)%step===0) ctx.fillText(String(y), ML-4, gy(y)+cell/2); }
   // radius-6 zone
   ctx.strokeStyle="#3b6ea5"; ctx.lineWidth=1.5; ctx.setLineDash([4,3]);
   ctx.strokeRect(gx(mx-R)+0.5,gy(my-R)+0.5,(2*R+1)*cell,(2*R+1)*cell); ctx.setLineDash([]);
   owned.forEach(([x,y])=>box(x,y,"#2e7d5b"));
   ctx.strokeStyle="#c9a227"; ctx.lineWidth=1.5;
   garr.forEach(([x,y])=>ctx.strokeRect(gx(x)+2,gy(y)+2,cell-4,cell-4));
   fpts.forEach(([x,y])=>box(x,y,"#e08a2b"));
   // accepted (planned forts): orange fill + a check dot
   accepted.forEach(([x,y])=>{ box(x,y,"#e08a2b");
    ctx.fillStyle="#0b1320"; ctx.beginPath();
    ctx.arc(gx(x)+cell/2,gy(y)+cell/2,Math.max(1.5,cell/6),0,Math.PI*2); ctx.fill(); });
   // pending recs: red ring (clickable)
   rpts.forEach(([x,y])=>{ ctx.strokeStyle="#e5484d"; ctx.lineWidth=2; ctx.beginPath();
    ctx.arc(gx(x)+cell/2,gy(y)+cell/2,Math.max(3,cell/2-1),0,Math.PI*2); ctx.stroke(); });
   box(mx,my,"#3b82f6");
   legend.value=`🟦 thành chính · 🟩 ô đã chiếm (${owned.length}) · 🟨 quân trú (${garr.length}) · `
    +`🟧 Cứ Điểm/dự kiến (${fpts.length+accepted.length}) · 🔴 gợi ý (${rpts.length}) · ⬚ bán kính ${R} ô`;
  }
  function onClick(ev){
   const g=geom.value; if(!g) return;
   const cv=canvas.value, rect=cv.getBoundingClientRect();
   const px=(ev.clientX-rect.left)*(cv.width/rect.width);
   const py=(ev.clientY-rect.top)*(cv.height/rect.height);
   const cx=Math.round((px-g.ox)/g.cell)+g.minX, cy=Math.round((py-g.oy)/g.cell)+g.minY;
   const hit=recs.value.find(r=>r.x===cx && r.y===cy);
   sel.value = hit ? {index:hit.index,x:hit.x,y:hit.y,
     left:Math.min(ev.clientX-rect.left, cv.width-140), top:ev.clientY-rect.top} : null;
  }
  async function decide(decision){
   if(!sel.value) return;
   await postJSON("/api/forts/decide",{index:sel.value.index,decision});
   sel.value=null; draw();
  }
  usePolling(draw, 4000);
  return { canvas, summary, legend, sel, onClick, decide };
 },
 template:`<div class="card full" style="position:relative"><h2>Lãnh thổ</h2>
  <div class="muted">{{ summary }}</div>
  <canvas ref="canvas" class="terrmap" width="640" height="360" @click="onClick"></canvas>
  <div v-if="sel" style="position:absolute;background:#0d1117;border:1px solid var(--border-hi);
    border-radius:6px;padding:6px 8px;z-index:5" :style="{left:sel.left+'px',top:(sel.top+40)+'px'}">
   <div class="muted" style="font-size:12px">Gợi ý Cứ Điểm ({{ sel.x }},{{ sel.y }})</div>
   <button @click="decide('accept')">✓ Chấp thuận</button>
   <button @click="decide('reject')">✕ Từ chối</button>
   <button @click="sel=null">Đóng</button></div>
  <div class="muted" style="margin-top:6px;font-size:12px">{{ legend }}</div></div>`
};
```

- [ ] **Step 4: Run tests + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_components.py -q` → PASS.
```bash
git add nta_agent/dashboard/static/components/TerritoryPanel.js tests/test_dashboard_components.py
git commit -m "feat(dashboard): map coord rulers + clickable rec accept/reject"
```

---

### Task 5: FE — FortsPanel decision buttons + lists; live verify

**Files:**
- Modify: `nta_agent/dashboard/static/components/FortsPanel.js`
- Test: extend `tests/test_dashboard_components.py`

**Interfaces:**
- Consumes: `getJSON`, `postJSON`, `usePolling`. Per-rec Chấp thuận/Từ chối; Đã chấp thuận / Đã từ chối lists with a × (clear). Rejected list needs the rejected indices — derive from `fort_decisions` exposed via `/api/forts` (add `rejected` to the view) OR keep rejected implicit. This task adds `rejected` coords to the forts view for the list.

- [ ] **Step 1: Add `rejected` to the forts payload + view**

In `fort_service.py` payload and `recompute_forts` payload add:
```python
                       "rejected": sorted([i % mw, i // mw] for i in
                                          [k for k, v in decisions.items() if v == "rejected"]),
```
(`decisions` is already loaded in both; for `fort_service` it is `decisions`, for `recompute_forts` likewise.) In `read_forts_view` add `"rejected": data.get("rejected") or []` (both branches).

Add a test to `tests/test_dashboard_decide.py`:
```python
def test_recompute_lists_rejected(tmp_path):
    from nta_agent.runtime import fort_decisions as fd
    cfg = _setup(tmp_path)
    fd.update(cfg.fort_decisions_path, 100 * 600 + 120, "reject")
    out = recompute_forts(cfg)
    assert [100, 120] in out["rejected"]
```

- [ ] **Step 2: Add FE assertions**

```python
def test_forts_panel_decision_buttons():
    fp = _c("FortsPanel.js")
    assert "/api/forts/decide" in fp
    assert "Chấp thuận" in fp and "Từ chối" in fp
    assert "accepted" in fp and "rejected" in fp
```

- [ ] **Step 3: Run → FAIL.** (server test + component test)

- [ ] **Step 4: Implement the payload/view changes** (Step 1 code) and **rewrite `FortsPanel.js`**:

```js
// nta_agent/dashboard/static/components/FortsPanel.js
import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const f=ref({owned_count:0,recommendations:[],accepted:[],rejected:[]});
  async function load(){ const v=await getJSON("/api/forts");
   if(v) f.value={owned_count:v.owned_count||0,recommendations:v.recommendations||[],
                  accepted:v.accepted||[],rejected:v.rejected||[]}; }
  usePolling(load, 4000);
  async function decide(index, decision){ await postJSON("/api/forts/decide",{index,decision}); load(); }
  const toIdx=([x,y])=> y*600 + x;  // map_width 600 (matches server)
  return { f, decide, toIdx };
 },
 template:`<div class="card full"><h2>Cứ Điểm — gợi ý</h2>
  <div>Ô đã chiếm: <b>{{ f.owned_count||0 }}</b></div>
  <div style="margin-top:6px">
   <div v-for="(r,i) in f.recommendations" :key="'r'+i" style="display:flex;align-items:center;gap:8px;padding:2px 0">
    <span style="flex:1">{{ i+1 }}. Cứ Điểm @{{ r.index }} ({{ r.x }},{{ r.y }}) — {{ r.reason||"" }}</span>
    <button @click="decide(r.index,'accept')">✓ Chấp thuận</button>
    <button @click="decide(r.index,'reject')">✕ Từ chối</button></div>
   <div v-if="!f.recommendations.length" class="muted">Chưa có gợi ý</div>
  </div>
  <div v-if="f.accepted.length" style="margin-top:8px">
   <div class="muted" style="font-size:12px">Đã chấp thuận (dự kiến xây):</div>
   <div v-for="(a,i) in f.accepted" :key="'a'+i">🟧 ({{ a[0] }},{{ a[1] }})
    <button @click="decide(toIdx(a),'clear')">×</button></div></div>
  <div v-if="f.rejected.length" style="margin-top:8px">
   <div class="muted" style="font-size:12px">Đã từ chối:</div>
   <div v-for="(a,i) in f.rejected" :key="'j'+i" class="muted">✕ ({{ a[0] }},{{ a[1] }})
    <button @click="decide(toIdx(a),'clear')">×</button></div></div>
 </div>`
};
```

- [ ] **Step 5: Full suite + lint**

Run: `.venv/Scripts/python.exe -m pytest -q` → all pass. `ruff check nta_agent tests` → clean.

- [ ] **Step 6: Live verify on machine A**

Start dashboard; `python -m nta_agent --once` (or Start from the UI) to populate owned cells. In the machine-A browser (browser "Quyền"), open the dashboard:
- Territory map shows X/Y ruler labels; hovering/looking at a cell, its coordinates are legible.
- If any rec ring is present, click it on the map → popover → **Chấp thuận** → it turns into an orange planned-fort marker with a check and leaves the rec list; **Từ chối** on another → it disappears and lands in "Đã từ chối"; **×** clears a decision and the cell returns to candidacy. Same via the FortsPanel buttons. All update within ~4s (or instantly on the acting component), no game request, no console errors.
- (If territory is all within radius 6 so there are no recs, verify the rulers + that accept/reject on a synthetic decision via the panel is a no-op-safe; note recs appear once territory expands.)
Screenshot for the user.

- [ ] **Step 7: Commit**

```bash
git add nta_agent/dashboard/static/components/FortsPanel.js nta_agent/runtime/fort_service.py nta_agent/dashboard/server.py tests/test_dashboard_components.py tests/test_dashboard_decide.py
git commit -m "feat(dashboard): fort decision buttons + accepted/rejected lists; D complete"
```

---

## Self-Review notes (author)

- **Spec coverage**: rulers (T4), accept/reject persisted + honored (T1 plan_forts, T2 fort_service, T3 endpoint/recompute), instant recompute no game request (T3), map click + list buttons (T4/T5), accepted rendering (T4), rejected list (T5). All covered.
- **Type consistency**: `plan_forts(main, owned, existing_forts, decisions, cap, map_width, radius) -> (recs, accepted)` defined T1, used by fort_service (T2) and recompute_forts (T3); `fort_decisions.load/update` (T2) used by fort_service, server; forts.json keys `owned_count/owned_cells/accepted/rejected/recommendations` consistent across T2/T3/T5 and consumed by T4/T5 FE; `/api/forts/decide {index, decision}` produced T3, called T4/T5.
- **No placeholders**: full code inline. (T2 test has a couple of redundant assertions — harmless; the load-bearing ones check rejected/accepted exclusion.)
- **Backward compat**: no decisions file → `plan_forts` == prior `recommend_forts` behavior (T1 test), so forts.json is unchanged when the user never decides.
