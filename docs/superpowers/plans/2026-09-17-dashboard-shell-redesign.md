# Dashboard Shell Redesign (sidebar + tabs + design system) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single long-scroll layout with a persistent top bar + left sidebar that switches between 5 grouped tabs, plus a small design system (reusable StatTile, resources as tiles), reusing all existing panels at feature parity.

**Architecture:** `App.js` becomes the shell (reactive `activeTab`, persisted to localStorage): top bar (existing `StatusHeader` = title + status + ControlBar) spanning the top, a `Sidebar` nav on the left, and the active tab's panels in the content area. New `Sidebar.js` + `StatTile.js`; `ResourcePanel` reworked to tiles. Territory map stays mounted via `v-show`; other tabs use `v-if`.

**Tech Stack:** Vue 3 (vendored, no-build); CSS.

**Spec:** `docs/superpowers/specs/2026-09-17-dashboard-shell-redesign-design.md`

## Global Constraints

- No backend/`/api` changes; reuse every existing panel component unchanged (except `ResourcePanel`, reworked to tiles).
- Feature parity: armies, decisions+equip, territory map (pan/zoom/decide), forts decide, build-order drag-drop, brain chat, events all still work. Vietnamese copy preserved.
- Dark-only; reuse existing CSS tokens.
- Territory map: `v-show` (preserve pan/zoom state across tab switches); other tab contents: `v-if`.
- ControlBar + status stay in the persistent top bar (reachable from every tab).
- Reuse the existing dashboard browser tab for live verify — do not spawn new tabs.
- Tests: `.venv/Scripts/python.exe -m pytest -q`; lint `.venv/Scripts/python.exe -m ruff check nta_agent tests`.
- Commit footer on every commit:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_017SWX7TP9uSdjA1HbV883Tm`.

---

### Task 1: StatTile component + resources as tiles + tile CSS

**Files:**
- Create: `nta_agent/dashboard/static/components/StatTile.js`
- Modify: `nta_agent/dashboard/static/components/ResourcePanel.js`
- Modify: `nta_agent/dashboard/static/app.css`
- Test: `tests/test_dashboard_components.py`

**Interfaces:**
- Produces: `StatTile` component (props `label`, `value`, `sub`), CSS classes `.tiles` (grid) + `.tile`.

- [ ] **Step 1: Add failing assertions**

```python
def test_stat_tile_and_resource_tiles():
    st = _c("StatTile.js")
    assert "label" in st and "value" in st
    rp = _c("ResourcePanel.js")
    assert "StatTile" in rp and "/api/state" in rp
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert ".tile" in css
```
(`STATIC` is already defined at the top of the test file.)

- [ ] **Step 2: Run → FAIL.** `.venv/Scripts/python.exe -m pytest tests/test_dashboard_components.py::test_stat_tile_and_resource_tiles -q`

- [ ] **Step 3: Create `StatTile.js`**

```js
// nta_agent/dashboard/static/components/StatTile.js
export default {
 props:{ label:String, value:[String,Number], sub:{type:String, default:"" } },
 template:`<div class="tile"><div class="tlabel">{{ label }}</div>
  <div class="tval">{{ value }}</div><div v-if="sub" class="muted tsub">{{ sub }}</div></div>`
};
```

- [ ] **Step 4: Rework `ResourcePanel.js` to tiles**

```js
// nta_agent/dashboard/static/components/ResourcePanel.js
import { getJSON, usePolling } from "../api.js";
import StatTile from "./StatTile.js";
const { ref } = window.Vue;
const RES=[["cereal","L.Thực"],["timber","Gỗ"],["stone","Đá"],["iron","Sắt"],
 ["gold","Vàng"],["exp_book","Sách EXP"],["up_scroll","Quyển Trục"],["fixator","Máy Cố Định"]];
export default {
 components:{ StatTile },
 setup(){
  const res=ref({});
  usePolling(async ()=>{ const s=await getJSON("/api/state"); res.value=(s&&s.ok&&s.resources)||{}; },2000);
  return { RES, res };
 },
 template:`<div class="card"><h2>Tài nguyên</h2>
  <div class="tiles"><StatTile v-for="[k,l] in RES" :key="k" :label="l" :value="res[k]??0"/></div></div>`
};
```

- [ ] **Step 5: Add tile CSS to `app.css`**

Append:
```css
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:var(--sp-2)}
.tile{background:#0d1117;border:1px solid var(--border);border-radius:6px;padding:var(--sp-2) var(--sp-3)}
.tile .tlabel{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.tile .tval{font-size:22px;color:var(--text);font-variant-numeric:tabular-nums;line-height:1.2}
.tile .tsub{font-size:11px}
```

- [ ] **Step 6: Run + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_components.py -q` → PASS.
```bash
git add nta_agent/dashboard/static/components/StatTile.js nta_agent/dashboard/static/components/ResourcePanel.js nta_agent/dashboard/static/app.css tests/test_dashboard_components.py
git commit -m "feat(dashboard): StatTile + resources as tiles"
```

---

### Task 2: Sidebar + App shell (tabs) + layout CSS

**Files:**
- Create: `nta_agent/dashboard/static/components/Sidebar.js`
- Modify: `nta_agent/dashboard/static/components/App.js`
- Modify: `nta_agent/dashboard/static/app.css`
- Test: `tests/test_dashboard_components.py`, `tests/test_dashboard_page.py`

**Interfaces:**
- Consumes: `StatusHeader` (top bar), all panel components, `StatTile` (via ResourcePanel).
- Produces: `Sidebar` (props `tabs` [{id,label,icon}], `active`; emits `select`); `App` shell with `activeTab` (localStorage-persisted), top bar + sidebar + tabbed content.

- [ ] **Step 1: Add failing assertions**

```python
def test_shell_sidebar_and_tabs():
    app = _c("App.js")
    assert "activeTab" in app and "Sidebar" in app
    assert "localStorage" in app
    # territory kept mounted across tab switches
    assert 'v-show' in app
    sb = _c("Sidebar.js")
    for label in ("Tổng quan", "Quân đội", "Lãnh thổ", "Xây dựng", "Nhật ký"):
        assert label in sb
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert ".shell" in css and ".sidebar" in css
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Create `Sidebar.js`**

```js
// nta_agent/dashboard/static/components/Sidebar.js
export default {
 props:{ tabs:Array, active:String },
 emits:["select"],
 template:`<nav class="sidebar">
  <button v-for="t in tabs" :key="t.id" class="tabbtn" :class="{on:t.id===active}"
    @click="$emit('select', t.id)" :title="t.label">
   <span class="ticon">{{ t.icon }}</span><span class="tlbl">{{ t.label }}</span></button>
 </nav>`
};
```

- [ ] **Step 4: Rewrite `App.js` as the shell**

```js
// nta_agent/dashboard/static/components/App.js
import StatusHeader from "./StatusHeader.js";
import Sidebar from "./Sidebar.js";
import ResourcePanel from "./ResourcePanel.js";
import CityPanel from "./CityPanel.js";
import MiscPanel from "./MiscPanel.js";
import ArmiesPanel from "./ArmiesPanel.js";
import DecisionsPanel from "./DecisionsPanel.js";
import EquipmentPanel from "./EquipmentPanel.js";
import TerritoryPanel from "./TerritoryPanel.js";
import FortsPanel from "./FortsPanel.js";
import BuildOrderPanel from "./BuildOrderPanel.js";
import BrainChatPanel from "./BrainChatPanel.js";
import EventsPanel from "./EventsPanel.js";
const { ref } = window.Vue;
const TABS=[
 {id:"overview", label:"Tổng quan", icon:"▦"},
 {id:"army",     label:"Quân đội",  icon:"⚔"},
 {id:"territory",label:"Lãnh thổ",  icon:"🗺"},
 {id:"build",    label:"Xây dựng & Chiến thuật", icon:"🛠"},
 {id:"log",      label:"Nhật ký",   icon:"📜"},
];
function loadTab(){ try{ return localStorage.getItem("nta.tab")||"overview"; }catch(e){ return "overview"; } }
export default {
 components:{ StatusHeader, Sidebar, ResourcePanel, CityPanel, MiscPanel, ArmiesPanel,
  DecisionsPanel, EquipmentPanel, TerritoryPanel, FortsPanel, BuildOrderPanel, BrainChatPanel, EventsPanel },
 setup(){
  const activeTab=ref(loadTab());
  function select(id){ activeTab.value=id; try{ localStorage.setItem("nta.tab", id); }catch(e){} }
  return { TABS, activeTab, select };
 },
 template:`<div><StatusHeader/>
  <div class="shell">
   <Sidebar :tabs="TABS" :active="activeTab" @select="select"/>
   <main class="content">
    <div v-if="activeTab==='overview'" class="grid">
     <ResourcePanel/><CityPanel/><MiscPanel/></div>
    <div v-if="activeTab==='army'" class="grid">
     <ArmiesPanel/><DecisionsPanel/><EquipmentPanel/></div>
    <div v-show="activeTab==='territory'" class="grid">
     <TerritoryPanel/><FortsPanel/></div>
    <div v-if="activeTab==='build'" class="grid">
     <BuildOrderPanel/><BrainChatPanel/></div>
    <div v-if="activeTab==='log'" class="grid">
     <EventsPanel/></div>
   </main>
  </div></div>`
};
```
Note: the territory block uses `v-show` so the map keeps its pan/zoom state; all
others use `v-if`.

- [ ] **Step 5: Add shell/sidebar CSS to `app.css`**

Append:
```css
.shell{display:grid;grid-template-columns:var(--sidebar-w,180px) 1fr;align-items:start}
.sidebar{display:flex;flex-direction:column;gap:2px;padding:var(--sp-3) var(--sp-2);
 border-right:1px solid var(--border);position:sticky;top:0}
.tabbtn{display:flex;align-items:center;gap:var(--sp-2);width:100%;text-align:left;margin:0;
 background:transparent;border:1px solid transparent;border-radius:6px;padding:8px 10px;color:var(--text)}
.tabbtn:hover{background:#161b22}
.tabbtn.on{background:#161b22;border-color:var(--border-hi);border-left:3px solid var(--accent)}
.tabbtn .ticon{width:18px;text-align:center}
.content{padding:var(--sp-4);min-width:0}
.content .grid{max-width:960px}
@media (max-width:760px){
 .shell{grid-template-columns:52px 1fr}
 .tabbtn .tlbl{display:none}
 .content .grid{grid-template-columns:1fr}
}
```

- [ ] **Step 6: Update `test_dashboard_page.py` if it references old header markup**

The shell keeps `StatusHeader` (with `id`/`ControlBar`) mounted; only adjust any
assertion that assumed the old flat `<main class="grid">` with all panels. Run the
page test and fix only what breaks:
Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_page.py tests/test_dashboard_components.py -q`
Expected: PASS (adjust assertions that hard-coded the old single-grid layout).

- [ ] **Step 7: Commit**

```bash
git add nta_agent/dashboard/static/components/Sidebar.js nta_agent/dashboard/static/components/App.js nta_agent/dashboard/static/app.css tests/test_dashboard_components.py tests/test_dashboard_page.py
git commit -m "feat(dashboard): sidebar + tabbed shell layout"
```

---

### Task 3: Full suite + live verify + responsive polish

**Files:** none expected (tweaks to `app.css`/components only if issues found).

- [ ] **Step 1: Full suite + lint**

Run: `.venv/Scripts/python.exe -m pytest -q` → all pass. `ruff check nta_agent tests` → clean.

- [ ] **Step 2: Live verify on machine A (reuse the existing tab)**

Start/refresh the dashboard in the existing browser tab (browser "Quyền"); do NOT
open new tabs. Verify:
- Sidebar switches between the 5 tabs; only the active tab's panels show.
- ControlBar + snapshot status visible on every tab; Start/Pause/Stop work.
- **Tổng quan**: resources render as tiles; City + Misc present.
- **Quân đội**: armies, decisions (equip), equipment.
- **Lãnh thổ**: map viewport (pan/zoom/hover/click), forts decide; switching away and back **preserves the map view** (v-show).
- **Xây dựng & Chiến thuật**: build-order drag-drop + save; brain chat send.
- **Nhật ký**: events feed.
- Narrow the window → sidebar collapses to icons, content becomes single column.
- No console errors. Screenshot for the user.

- [ ] **Step 3: Fix any issues found, then commit**

```bash
git add -A
git commit -m "polish(dashboard): shell responsive + fixes from live verify"
```
(Skip if nothing needed.)

---

## Self-Review notes (author)

- **Spec coverage**: top bar (reuse StatusHeader), sidebar + 5 tabs (T2), StatTile + resource tiles (T1), design-system CSS (T1/T2), territory `v-show` preservation (T2), localStorage tab (T2), responsive (T2 CSS), parity via reused panels, live verify (T3). All covered.
- **Type consistency**: `Sidebar` props `{tabs,active}` + `select` event match `App`'s `TABS`/`activeTab`/`select`; `StatTile` props `{label,value,sub}` match ResourcePanel usage.
- **No placeholders**: full code inline.
- **Parity**: all existing panels imported and rendered unchanged; only ResourcePanel restyled.
