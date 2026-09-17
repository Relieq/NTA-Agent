# Territory Map Viewport (pan/zoom/hover/click) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the territory map as a pannable/zoomable viewport with game-y-up orientation, adaptive rulers, viewport culling, hover tooltips, and click-to-select (with accept/reject on recs) — porting the old bot's HardDigGridCanvas model.

**Architecture:** `TerritoryPanel.js` keeps a viewport transform (`scale`, `originX/Y`) instead of auto-fitting each poll. World→screen uses `row = (map_width-1) - y` (y-up). Drag pans, wheel zooms at the cursor, buttons zoom/fit/recenter. Only visible cells are drawn. Data (territory+forts) refreshes on the 4s poll and redraws under the current transform without snapping the view.

**Tech Stack:** Vue 3 (vendored, no-build); `<canvas>` 2D.

**Spec:** `docs/superpowers/specs/2026-09-17-map-viewport-design.md`

## Global Constraints

- Game-y-up: `row(y) = (map_width-1) - y`. Y ruler labels read game-y.
- Zoom clamped 6-60 px/cell. Auto-fit runs once on first data (and on the Fit button), never snapping back after the user pans/zooms.
- Only cells within the viewport are drawn (culling).
- Reuse endpoints only: `/api/territory`, `/api/forts`, `POST /api/forts/decide`.
- Wheel zoom must not scroll the page (`passive:false` listener + `preventDefault`).
- Tests: `.venv/Scripts/python.exe -m pytest -q`; lint `.venv/Scripts/python.exe -m ruff check nta_agent tests`.
- Commit footer on every commit:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_017SWX7TP9uSdjA1HbV883Tm`.

---

### Task 1: Rewrite TerritoryPanel as a pan/zoom viewport

**Files:**
- Rewrite: `nta_agent/dashboard/static/components/TerritoryPanel.js`
- Test: `tests/test_dashboard_components.py` (update the territory assertions)

**Interfaces:**
- Consumes: `getJSON`, `postJSON`, `usePolling`, `window.Vue` (`ref`, `onMounted`, `onUnmounted`).
- Produces: the same component id/mount (already in `App.js`); no API change.

- [ ] **Step 1: Update the marker test**

Replace `test_territory_map_has_rulers_and_decisions` in `tests/test_dashboard_components.py` with:
```python
def test_territory_map_viewport():
    terr = _c("TerritoryPanel.js")
    # rendering
    assert "fillText" in terr and "accepted" in terr
    assert "labelStep" in terr and "[1, 2, 5, 10, 20, 25, 50, 100]" in terr
    assert "map_width" in terr or "MAPW" in terr        # y-flip uses map width
    # interaction
    assert "@mousedown" in terr and "@mousemove" in terr and "@mouseup" in terr
    assert "wheel" in terr and "getBoundingClientRect" in terr
    assert "Về thành chính" in terr                      # recenter control
    assert "/api/forts/decide" in terr                   # accept/reject on a rec
    assert "Math.min(60" in terr and "Math.max(6" in terr  # zoom clamp
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_components.py -q`
Expected: FAIL on the new markers.

- [ ] **Step 3: Rewrite the component**

```js
// nta_agent/dashboard/static/components/TerritoryPanel.js
import { getJSON, postJSON, usePolling } from "../api.js";
const { ref, onMounted, onUnmounted } = window.Vue;
const MAPW = 600;
const STEPS = [1, 2, 5, 10, 20, 25, 50, 100];
const ML = 28, MT = 18;   // ruler margins

function labelStep(scale){ for(const s of STEPS){ if(s*scale >= 56) return s; } return 100; }

export default {
 setup(){
  const canvas=ref(null), tip=ref(null), sel=ref(null);
  let scale=16, originX=0, originY=0, fitted=false, hover=null;
  let data={main:0, mw:MAPW, owned:[], accepted:[], forts:[], garr:[], recs:[]};
  let stateMap=new Map();
  let dragging=false, moved=0, lastX=0, lastY=0;

  const rowOf=(y)=> (data.mw-1) - y;
  const sX=(x)=> originX + x*scale;
  const sY=(y)=> originY + rowOf(y)*scale;
  const idx=(x,y)=> y*data.mw + x;
  const cellAt=(px,py)=>({ x: Math.floor((px-originX)/scale),
                           y: (data.mw-1) - Math.floor((py-originY)/scale) });

  function buildStateMap(){
   stateMap=new Map();
   const put=(x,y,label,index)=>{ const k=idx(x,y); if(!stateMap.has(k)) stateMap.set(k,{label,index:index??k}); };
   const mx=data.main%data.mw, my=Math.floor(data.main/data.mw);
   put(mx,my,"thành chính");
   data.forts.forEach(([x,y])=>put(x,y,"Cứ Điểm"));
   data.accepted.forEach(([x,y])=>put(x,y,"dự kiến xây"));
   data.recs.forEach(r=>put(r.x,r.y,"gợi ý",r.index));
   data.garr.forEach(([x,y])=>put(x,y,"quân trú"));
   data.owned.forEach(([x,y])=>put(x,y,"đã chiếm"));
  }

  function fitView(cv){
   const mx=data.main%data.mw, my=Math.floor(data.main/data.mw), R=6;
   const pts=[[mx,my],...data.owned,...data.accepted,...data.forts,...data.garr,
              ...data.recs.map(r=>[r.x,r.y]),[mx-R,my-R],[mx+R,my+R]];
   const minX=Math.min(...pts.map(p=>p[0]))-1, maxX=Math.max(...pts.map(p=>p[0]))+1;
   const minY=Math.min(...pts.map(p=>p[1]))-1, maxY=Math.max(...pts.map(p=>p[1]))+1;
   const cols=maxX-minX+1, rows=maxY-minY+1;
   scale=Math.max(6, Math.min(60, Math.floor(Math.min((cv.width-ML)/cols,(cv.height-MT)/rows))));
   originX = ML + Math.floor((cv.width-ML - cols*scale)/2) - minX*scale;
   originY = MT + Math.floor((cv.height-MT - rows*scale)/2) - rowOf(maxY)*scale;
  }
  function recenter(cv){ scale=16;
   originX = cv.width/2 - (data.main%data.mw)*scale;
   originY = cv.height/2 - rowOf(Math.floor(data.main/data.mw))*scale; }
  function zoomAt(px,py,f){ const s2=Math.max(6, Math.min(60, scale*f));
   originX = px-(px-originX)*s2/scale; originY = py-(py-originY)*s2/scale; scale=s2; render(); }

  function render(){
   const cv=canvas.value; if(!cv) return;
   const ctx=cv.getContext("2d"), W=cv.width, H=cv.height;
   ctx.fillStyle="#0b1320"; ctx.fillRect(0,0,W,H);
   if(!data.main){ ctx.fillStyle="#8b949e"; ctx.font="12px system-ui";
    ctx.fillText("Chưa có dữ liệu bản đồ.", ML+8, MT+20); return; }
   const x0=Math.max(0,Math.floor((ML-originX)/scale)), x1=Math.min(data.mw-1,Math.ceil((W-originX)/scale));
   const rTop=Math.max(0,Math.floor((MT-originY)/scale)), rBot=Math.min(data.mw-1,Math.ceil((H-originY)/scale));
   const yHi=(data.mw-1)-rTop, yLo=(data.mw-1)-rBot;
   const inView=(x,y)=> x>=x0&&x<=x1&&y>=yLo&&y<=yHi;
   ctx.save(); ctx.beginPath(); ctx.rect(ML,MT,W-ML,H-MT); ctx.clip();
   const box=(x,y,c)=>{ ctx.fillStyle=c; ctx.fillRect(sX(x)+1,sY(y)+1,scale-2,scale-2); };
   const mx=data.main%data.mw, my=Math.floor(data.main/data.mw), R=6;
   ctx.strokeStyle="#3b6ea5"; ctx.lineWidth=1.5; ctx.setLineDash([4,3]);
   ctx.strokeRect(sX(mx-R)+0.5, sY(my+R)+0.5, (2*R+1)*scale, (2*R+1)*scale); ctx.setLineDash([]);
   data.owned.forEach(([x,y])=>{ if(inView(x,y)) box(x,y,"#2e7d5b"); });
   ctx.strokeStyle="#c9a227"; ctx.lineWidth=1.5;
   data.garr.forEach(([x,y])=>{ if(inView(x,y)) ctx.strokeRect(sX(x)+2,sY(y)+2,scale-4,scale-4); });
   data.forts.forEach(([x,y])=>{ if(inView(x,y)) box(x,y,"#e08a2b"); });
   data.accepted.forEach(([x,y])=>{ if(inView(x,y)){ box(x,y,"#e08a2b");
    ctx.fillStyle="#0b1320"; ctx.beginPath(); ctx.arc(sX(x)+scale/2,sY(y)+scale/2,Math.max(1.5,scale/6),0,7); ctx.fill(); } });
   data.recs.forEach(r=>{ if(inView(r.x,r.y)){ ctx.strokeStyle="#e5484d"; ctx.lineWidth=2; ctx.beginPath();
    ctx.arc(sX(r.x)+scale/2,sY(r.y)+scale/2,Math.max(3,scale/2-1),0,7); ctx.stroke(); } });
   if(inView(mx,my)) box(mx,my,"#3b82f6");
   if(hover && inView(hover.x,hover.y)){ ctx.strokeStyle="#58a6ff"; ctx.lineWidth=2;
    ctx.strokeRect(sX(hover.x)+1,sY(hover.y)+1,scale-2,scale-2); }
   ctx.restore();
   // rulers
   ctx.fillStyle="#0b1320"; ctx.fillRect(0,0,W,MT); ctx.fillRect(0,0,ML,H);
   ctx.fillStyle="#8b949e"; ctx.font="10px ui-monospace,Consolas,monospace";
   const step=labelStep(scale);
   ctx.textAlign="center"; ctx.textBaseline="alphabetic";
   for(let x=x0; x<=x1; x++){ if(x%step===0){ const px=sX(x)+scale/2; if(px>=ML) ctx.fillText(String(x), px, MT-4); } }
   ctx.textAlign="right"; ctx.textBaseline="middle";
   for(let y=yLo; y<=yHi; y++){ if(y%step===0){ const py=sY(y)+scale/2; if(py>=MT) ctx.fillText(String(y), ML-4, py); } }
  }

  async function load(){
   const t=await getJSON("/api/territory"), f=await getJSON("/api/forts");
   if(!t||!f) return;
   const mw=t.map_width||MAPW;
   data={ main:t.main_city||0, mw, owned:f.owned_cells||[], accepted:f.accepted||[],
    forts:(t.forts||[]).map(x=>[x.x,x.y]),
    garr:(t.garrisons||[]).map(i=>[i%mw, Math.floor(i/mw)]),
    recs:f.recommendations||[] };
   buildStateMap();
   const cv=canvas.value;
   if(cv && data.main && !fitted){ fitView(cv); fitted=true; }
   render();
  }
  usePolling(load, 4000);

  const toCanvas=(ev)=>{ const cv=canvas.value, r=cv.getBoundingClientRect();
   return [ (ev.clientX-r.left)*(cv.width/r.width), (ev.clientY-r.top)*(cv.height/r.height) ]; };
  function onDown(ev){ dragging=true; moved=0; lastX=ev.clientX; lastY=ev.clientY; }
  function onMove(ev){
   const cv=canvas.value, r=cv.getBoundingClientRect();
   if(dragging){ const dx=ev.clientX-lastX, dy=ev.clientY-lastY; moved+=Math.abs(dx)+Math.abs(dy);
    originX += dx*(cv.width/r.width); originY += dy*(cv.height/r.height);
    lastX=ev.clientX; lastY=ev.clientY; render(); return; }
   const [px,py]=toCanvas(ev);
   if(px<ML||py<MT){ if(hover){hover=null;render();} tip.value=null; return; }
   const c=cellAt(px,py); hover=c;
   const st=stateMap.get(idx(c.x,c.y));
   tip.value={ left:(ev.clientX-r.left)+12, top:(ev.clientY-r.top)+12,
     text:`(${c.x}, ${c.y})`+(st?` · ${st.label}`:" · trống") };
   render();
  }
  function onUp(ev){ dragging=false;
   if(moved<4){ const [px,py]=toCanvas(ev);
    if(px>=ML&&py>=MT){ const c=cellAt(px,py), st=stateMap.get(idx(c.x,c.y));
     const r=canvas.value.getBoundingClientRect();
     sel.value={ x:c.x, y:c.y, index: st?st.index:idx(c.x,c.y), state: st?st.label:"trống",
       left:Math.min(ev.clientX-r.left, r.width-170), top:(ev.clientY-r.top) }; } } }
  function onLeave(){ hover=null; tip.value=null; render(); }
  function onWheel(ev){ ev.preventDefault(); const [px,py]=toCanvas(ev); zoomAt(px,py, ev.deltaY<0?1.15:1/1.15); }
  function zoomBtn(f){ const cv=canvas.value; zoomAt(cv.width/2, cv.height/2, f); }
  function recenterBtn(){ recenter(canvas.value); render(); }
  function fitBtn(){ fitView(canvas.value); render(); }
  async function decide(decision){ if(!sel.value) return;
   await postJSON("/api/forts/decide",{index:sel.value.index,decision}); sel.value=null; load(); }

  onMounted(()=>{ const cv=canvas.value; if(cv) cv.addEventListener("wheel", onWheel, {passive:false}); });
  onUnmounted(()=>{ const cv=canvas.value; if(cv) cv.removeEventListener("wheel", onWheel); });

  return { canvas, tip, sel, onDown, onMove, onUp, onLeave, zoomBtn, recenterBtn, fitBtn, decide };
 },
 template:`<div class="card full"><h2>Lãnh thổ</h2>
  <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px;flex-wrap:wrap">
   <button @click="zoomBtn(1.25)">＋</button><button @click="zoomBtn(0.8)">－</button>
   <button @click="fitBtn">Vừa khung</button><button @click="recenterBtn">Về thành chính</button>
   <span class="muted" style="font-size:12px">Kéo để di chuyển · cuộn để phóng to · bấm ô để xem toạ độ</span></div>
  <div style="position:relative">
   <canvas ref="canvas" class="terrmap" width="640" height="360"
     @mousedown="onDown" @mousemove="onMove" @mouseup="onUp" @mouseleave="onLeave"
     style="cursor:grab"></canvas>
   <div v-if="tip" class="muted" style="position:absolute;background:#0d1117;border:1px solid var(--border-hi);
     border-radius:4px;padding:2px 6px;font-size:11px;pointer-events:none;z-index:6"
     :style="{left:tip.left+'px',top:tip.top+'px'}">{{ tip.text }}</div>
   <div v-if="sel" style="position:absolute;background:#0d1117;border:1px solid var(--border-hi);
     border-radius:6px;padding:6px 8px;z-index:7" :style="{left:sel.left+'px',top:(sel.top+16)+'px'}">
    <div class="muted" style="font-size:12px">Ô ({{ sel.x }}, {{ sel.y }}) · {{ sel.state }}</div>
    <template v-if="sel.state==='gợi ý'">
     <button @click="decide('accept')">✓ Chấp thuận</button>
     <button @click="decide('reject')">✕ Từ chối</button></template>
    <button @click="sel=null">Đóng</button></div>
  </div></div>`
};
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_components.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/dashboard/static/components/TerritoryPanel.js tests/test_dashboard_components.py
git commit -m "feat(dashboard): pannable/zoomable territory map (y-up, rulers, hover/click)"
```

---

### Task 2: Palette validation + full suite + live verify

**Files:** none (verification + optional color tweak in `TerritoryPanel.js`).

- [ ] **Step 1: Validate the map's categorical colors (dataviz)**

Run from the dataviz skill base dir:
```bash
node scripts/validate_palette.js "#2e7d5b,#e08a2b,#e5484d,#3b82f6,#c9a227" --mode dark
```
(owned, fort/accepted, rec, main, garrison). If any adjacent pair FAILs the CVD/normal-vision check, nudge the offending hex toward the dataviz ramps and re-run until PASS; update the colors in `TerritoryPanel.js` to match. Record the final PASS.

- [ ] **Step 2: Full suite + lint**

Run: `.venv/Scripts/python.exe -m pytest -q` → all pass. `ruff check nta_agent tests` → clean.

- [ ] **Step 3: Live verify on machine A**

Start the dashboard; `python -m nta_agent --once` (or Start from the UI) to populate owned cells. In the machine-A browser (browser "Quyền"), open the dashboard → Lãnh thổ:
- **Drag** the map → the view pans. **Wheel** over a spot → zooms centred there (page does not scroll). **＋/－**, **Vừa khung**, **Về thành chính** work.
- **Y axis increases upward** (larger y higher); ruler labels are round numbers and stay readable at different zooms.
- **Hover** a cell → highlight + tooltip `(x, y) · state`.
- **Click** a cell → popover shows its `(x, y)` + state; on a rec it offers Chấp thuận/Từ chối (which apply, as before).
- No console errors. Screenshot for the user.

- [ ] **Step 4: Commit any color tweak**

```bash
git add nta_agent/dashboard/static/components/TerritoryPanel.js
git commit -m "chore(dashboard): validate map palette (dataviz)"
```
(Skip if no color change was needed.)

---

## Self-Review notes (author)

- **Spec coverage**: drag-pan, wheel-zoom-at-cursor, +/-/fit/recenter, zoom clamp 6-60, y-up (`row=(mw-1)-y`), adaptive round rulers (`labelStep`), culling (visible range), hover tooltip+highlight, click select + coords + accept/reject, once-only auto-fit — all in Task 1. Palette validation + live verify in Task 2.
- **Type consistency**: reuses `/api/territory`, `/api/forts`, `/api/forts/decide` unchanged; component id/mount unchanged (App.js needs no edit).
- **No placeholders**: the full component is inline.
- **Perf**: culling limits drawn cells to the viewport; redraw only on interaction + the 4s poll.
