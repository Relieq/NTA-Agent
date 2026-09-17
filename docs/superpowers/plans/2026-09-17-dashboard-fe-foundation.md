# Dashboard FE Foundation (Vue 3 no-build) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard's monolithic inline HTML/JS page with a Vue 3 (vendored, no-build) component app + a small CSS design system, served as static files by the existing Python server, at full feature parity.

**Architecture:** The stdlib HTTP server gains a `/static/<path>` route (traversal-guarded, extension-whitelisted) that serves a vendored `vue.global.prod.js`, `app.css`, and ES-module JS. `INDEX_HTML` becomes a thin shell mounting a Vue app whose panels (one component each) fetch the unchanged `/api/*` endpoints. No npm, no bundler.

**Tech Stack:** Python 3.12 stdlib `http.server`; Vue 3 global build (vendored); native ES modules; `<canvas>` 2D.

**Spec:** `docs/superpowers/specs/2026-09-17-dashboard-fe-foundation-design.md`

## Global Constraints

- **No build toolchain**: no npm, bundler, TypeScript, or `.vue` SFCs. Components are plain JS objects with string `template`s; the vendored **global** Vue build (includes the template compiler) is required — not the runtime-only build.
- **Vendored, offline**: no CDN/`import` from the internet at page load. Vue ships as a committed file under `nta_agent/dashboard/static/vendor/`.
- **Parity**: no change to `/api/*` endpoints or JSON shapes; every existing panel/interaction behaves identically. Vietnamese copy preserved verbatim.
- **Dark-only** palette; reuse the exact current colors as CSS tokens (`--bg:#0f1216 --panel:#171b21 --border:#262c34 --border-hi:#3a4450 --text:#e6e6e6 --muted:#8b949e --accent:#58a6ff --ok:#3fb950 --warn:#d29922 --danger:#f85149`).
- Global Vue is exposed as `window.Vue`; ES modules read `const { ... } = window.Vue`. Component modules import each other by relative path (`./components/x.js`).
- Test strategy (no JS runner): Python tests assert served static files contain required markers + that `app.js` imports each component; server behavior tested via the existing handler tests. Plus a final live browser verify on machine A.
- Run tests with `.venv/Scripts/python.exe -m pytest -q` and lint `.venv/Scripts/python.exe -m ruff check nta_agent tests`.
- Commit attribution footer on every commit:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_017SWX7TP9uSdjA1HbV883Tm`.

---

### Task 1: Static file serving + vendored Vue

**Files:**
- Modify: `nta_agent/dashboard/server.py` (add `/static/<path>` GET branch + `serve_static`)
- Create: `nta_agent/dashboard/static/vendor/vue.global.prod.js` (downloaded, committed)
- Create: `nta_agent/dashboard/static/README.md` (note the pinned Vue version)
- Test: `tests/test_dashboard_static.py`

**Interfaces:**
- Produces: `GET /static/<relpath>` serves files under `nta_agent/dashboard/static/` with a content-type whitelist; traversal/unknown-ext → 404. Later tasks put `app.css`, `app.js`, `api.js`, `components/*.js` here.

- [ ] **Step 1: Download + commit the vendored Vue build**

Run (from repo root; fall back to jsdelivr/unpkg if cdnjs 404s):
```bash
mkdir -p nta_agent/dashboard/static/vendor
curl -fL https://cdnjs.cloudflare.com/ajax/libs/vue/3.5.13/vue.global.prod.min.js \
  -o nta_agent/dashboard/static/vendor/vue.global.prod.js
# fallback: curl -fL https://cdn.jsdelivr.net/npm/vue@3.5.13/dist/vue.global.prod.js -o <same>
head -c 200 nta_agent/dashboard/static/vendor/vue.global.prod.js   # sanity: JS, defines Vue
```
Write `nta_agent/dashboard/static/README.md`:
```markdown
# Dashboard static assets
Vendored, no-build frontend served by `nta_agent/dashboard/server.py` at `/static/`.
- `vendor/vue.global.prod.js` — Vue 3.5.13 global build (includes template compiler). Do not edit.
- `app.css` — design system + component styles.
- `app.js` / `api.js` / `components/*.js` — ES modules.
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_dashboard_static.py
from nta_agent.dashboard.server import serve_static


def test_serve_static_returns_js_and_type():
    code, ctype, body = serve_static("vendor/vue.global.prod.js")
    assert code == 200
    assert ctype.startswith("text/javascript")
    assert b"Vue" in body


def test_serve_static_blocks_traversal():
    for p in ("../server.py", "..%2fserver.py", "vendor/../../server.py", "/etc/passwd"):
        code, _ctype, _body = serve_static(p)
        assert code == 404


def test_serve_static_rejects_unknown_extension():
    code, _ctype, _body = serve_static("../server.py")  # .py not whitelisted anyway
    assert code == 404


def test_serve_static_missing_file_404():
    code, _ctype, _body = serve_static("app.js")  # not created until Task 2
    assert code == 404
```

- [ ] **Step 3: Run it to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_static.py -q`
Expected: FAIL (`ImportError: cannot import name 'serve_static'`).

- [ ] **Step 4: Implement `serve_static` + wire the route**

Add to `nta_agent/dashboard/server.py` (near the other read_* helpers):
```python
from pathlib import Path

_STATIC_DIR = (Path(__file__).parent / "static").resolve()
_STATIC_TYPES = {".js": "text/javascript", ".mjs": "text/javascript",
                 ".css": "text/css", ".map": "application/json"}


def serve_static(relpath: str):
    """Return (status, content_type, body_bytes) for a file under the static dir.

    Guards against path traversal and non-whitelisted extensions. 404 on any miss.
    """
    ext = ("." + relpath.rsplit(".", 1)[-1]).lower() if "." in relpath else ""
    ctype = _STATIC_TYPES.get(ext)
    if not ctype:
        return 404, "text/plain", b"not found"
    try:
        target = (_STATIC_DIR / relpath).resolve()
        target.relative_to(_STATIC_DIR)  # raises if traversal escaped the dir
        body = target.read_bytes()
    except (ValueError, OSError):
        return 404, "text/plain", b"not found"
    return 200, ctype + "; charset=utf-8", body
```
In `Handler.do_GET`, add before the final `else`:
```python
        elif parsed.path.startswith("/static/"):
            code, ctype, body = serve_static(parsed.path[len("/static/"):])
            self._send(code, body, ctype)
```

- [ ] **Step 5: Run tests to verify pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_static.py -q`
Expected: 3 pass; `test_serve_static_missing_file_404` passes (app.js absent). All 4 pass.

- [ ] **Step 6: Lint + commit**

```bash
.venv/Scripts/python.exe -m ruff check nta_agent/dashboard/server.py tests/test_dashboard_static.py
git add nta_agent/dashboard/server.py nta_agent/dashboard/static tests/test_dashboard_static.py
git commit -m "feat(dashboard): static file serving + vendored Vue 3"
```

---

### Task 2: App shell + design system + api helpers + root App (StatusHeader)

**Files:**
- Modify: `nta_agent/dashboard/page.py` (`INDEX_HTML` → thin shell)
- Create: `nta_agent/dashboard/static/app.css`
- Create: `nta_agent/dashboard/static/api.js`
- Create: `nta_agent/dashboard/static/app.js`
- Create: `nta_agent/dashboard/static/components/App.js`
- Create: `nta_agent/dashboard/static/components/StatusHeader.js`
- Test: `tests/test_dashboard_page.py` (rewrite for the shell + static markers)

**Interfaces:**
- Consumes: `serve_static` (Task 1).
- Produces:
  - `api.js` exports `getJSON(url)->obj|null`, `postJSON(url,body)->obj|null`, `usePolling(fn, ms)` (calls `fn` on mount + every `ms`, clears on unmount).
  - `components/App.js` default-exports the root component; it renders `<StatusHeader/>` then a `<main class="grid">` of panels (added task by task).
  - Shell exposes mount point `id="app"`, loads `/static/vendor/vue.global.prod.js`, `/static/app.css`, and `type="module" /static/app.js`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_page.py  (replace file)
from pathlib import Path

from nta_agent.dashboard.page import INDEX_HTML

STATIC = Path("nta_agent/dashboard/static")


def _read(rel):
    return (STATIC / rel).read_text(encoding="utf-8")


def test_shell_mounts_vue_app():
    assert 'id="app"' in INDEX_HTML
    assert "/static/vendor/vue.global.prod.js" in INDEX_HTML
    assert "/static/app.css" in INDEX_HTML
    assert 'type="module"' in INDEX_HTML and "/static/app.js" in INDEX_HTML


def test_app_module_imports_components():
    app = _read("app.js")
    assert "./components/App.js" in app
    assert "createApp" in app


def test_design_system_defines_tokens():
    css = _read("app.css")
    for tok in ("--bg", "--panel", "--border", "--accent", "--muted"):
        assert tok in css


def test_status_header_component_present():
    hdr = _read("components/StatusHeader.js")
    assert "/api/state" in hdr
    assert "NTA Agent" in hdr
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_page.py -q`
Expected: FAIL (shell markers absent / static files missing).

- [ ] **Step 3: Write `app.css` (design system)**

```css
/* nta_agent/dashboard/static/app.css */
:root{
 --bg:#0f1216; --panel:#171b21; --border:#262c34; --border-hi:#3a4450;
 --text:#e6e6e6; --muted:#8b949e; --accent:#58a6ff;
 --ok:#3fb950; --warn:#d29922; --danger:#f85149;
 --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --radius:8px;
 --mono:ui-monospace,Consolas,monospace;
}
*{box-sizing:border-box}
body{margin:0;font:14px system-ui,Segoe UI,Arial;background:var(--bg);color:var(--text)}
header{display:flex;justify-content:space-between;align-items:center;
 padding:var(--sp-3) var(--sp-4);background:var(--panel);border-bottom:1px solid var(--border)}
header h1{font-size:16px;margin:0}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;background:#666}
.dot.on{background:var(--ok)}.dot.wait{background:var(--warn)}
main.grid{padding:var(--sp-4);display:grid;gap:var(--sp-3);grid-template-columns:1fr 1fr;max-width:960px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);
 padding:var(--sp-3);transition:border-color .15s}
.card:hover{border-color:var(--border-hi)}
.card h2{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--accent);margin:0 0 var(--sp-2)}
.full{grid-column:1/-1}
.kv{display:flex;flex-wrap:wrap;gap:var(--sp-2) var(--sp-4)}.kv b{color:#fff}
ul{list-style:none;margin:0;padding:0}li{padding:3px 0;border-bottom:1px solid #21262d}
.feed{max-height:320px;overflow:auto;font-family:var(--mono);font-size:12px}
.muted{color:var(--muted)}
button{background:#21262d;color:var(--text);border:1px solid var(--border-hi);
 border-radius:6px;padding:4px 10px;margin:2px;cursor:pointer}
button:hover:not(:disabled){border-color:var(--accent)}button:disabled{opacity:.5;cursor:default}
input{background:#0d1117;color:var(--text);border:1px solid var(--border-hi);border-radius:6px;padding:4px 8px}
.bolist{list-style:none;padding:0;margin:var(--sp-2) 0;max-width:520px}
.bolist li{display:flex;align-items:center;gap:var(--sp-2);padding:5px 8px;margin:3px 0;
 background:#161b22;border:1px solid var(--border-hi);border-radius:6px;cursor:grab}
.bolist li.drag{opacity:.4}.bolist li.skip{opacity:.5;text-decoration:line-through}
.bolist .grip{color:var(--muted);cursor:grab}.bolist .nm{flex:1}
.bolist label{font-size:12px;color:var(--muted);cursor:pointer}
canvas.terrmap{width:100%;max-width:640px;margin-top:10px;border:1px solid #1e2a3a;
 border-radius:var(--radius);background:#0b1320;display:block}
```

- [ ] **Step 4: Write `api.js`**

```js
// nta_agent/dashboard/static/api.js
export async function getJSON(u){ try{ const r=await fetch(u); return await r.json(); }catch(e){ return null; } }
export async function postJSON(u, body){
 try{ const r=await fetch(u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      return await r.json(); }catch(e){ return null; }
}
export function usePolling(fn, ms){
 const { onMounted, onUnmounted } = window.Vue;
 onMounted(()=>{ fn(); const id=setInterval(fn, ms); onUnmounted(()=>clearInterval(id)); });
}
export function ago(ts){ if(!ts) return ""; const s=Math.max(0,Math.round(Date.now()/1000-ts)); return s+"s trước"; }
export function hms(ts){ return new Date((ts||0)*1000).toLocaleTimeString(); }
```

- [ ] **Step 5: Write `components/StatusHeader.js`**

```js
// nta_agent/dashboard/static/components/StatusHeader.js
import { getJSON, usePolling, ago } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const ok=ref(false), text=ref("…");
  usePolling(async ()=>{
   const s=await getJSON("/api/state");
   if(!s||!s.ok){ ok.value=false; text.value="Đang chờ agent…"; }
   else{ ok.value=true; text.value="đang chạy · "+ago(s.updated_at); }
  }, 2000);
  return { ok, text };
 },
 template:`<header><h1>NTA Agent</h1>
  <div><span class="dot" :class="ok?'on':'wait'"></span><span>{{ text }}</span></div></header>`
};
```

- [ ] **Step 6: Write `components/App.js` + `app.js`**

```js
// nta_agent/dashboard/static/components/App.js
import StatusHeader from "./StatusHeader.js";
export default {
 components:{ StatusHeader },
 // panels are added to <main> in later tasks
 template:`<div><StatusHeader/><main class="grid"></main></div>`
};
```
```js
// nta_agent/dashboard/static/app.js
import App from "./components/App.js";
const { createApp } = window.Vue;
createApp(App).mount("#app");
```

- [ ] **Step 7: Replace `INDEX_HTML` with the shell**

```python
# nta_agent/dashboard/page.py  (replace file contents)
"""The dashboard shell: mounts the vendored Vue app from /static."""

INDEX_HTML = """<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NTA Agent</title>
<link rel="stylesheet" href="/static/app.css">
</head><body>
<div id="app"></div>
<script src="/static/vendor/vue.global.prod.js"></script>
<script type="module" src="/static/app.js"></script>
</body></html>"""
```

- [ ] **Step 8: Run tests + lint**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_page.py tests/test_dashboard_static.py -q`
Expected: PASS.
Run: `.venv/Scripts/python.exe -m ruff check nta_agent tests` → clean.

- [ ] **Step 9: Commit**

```bash
git add nta_agent/dashboard/page.py nta_agent/dashboard/static tests/test_dashboard_page.py
git commit -m "feat(dashboard): Vue shell + design system + status header"
```

---

### Task 3: State panels — Resource, City, Misc

**Files:**
- Create: `nta_agent/dashboard/static/components/ResourcePanel.js`, `CityPanel.js`, `MiscPanel.js`
- Modify: `components/App.js` (mount the three)
- Test: `tests/test_dashboard_components.py` (new; grows each task)

**Interfaces:**
- Consumes: `getJSON`, `usePolling`. All three poll `/api/state` at 2000ms.
- Produces: three components registered in `App`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_components.py
from pathlib import Path
STATIC = Path("nta_agent/dashboard/static")
def _c(name): return (STATIC / "components" / name).read_text(encoding="utf-8")
def _app(): return (STATIC / "components" / "App.js").read_text(encoding="utf-8")


def test_state_panels_read_state_and_are_mounted():
    assert "/api/state" in _c("ResourcePanel.js")
    assert "hàng đợi" in _c("CityPanel.js")           # queue label
    assert "Đội hành quân" in _c("MiscPanel.js")
    app = _app()
    for comp in ("ResourcePanel", "CityPanel", "MiscPanel"):
        assert comp in app
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_components.py -q` → FAIL.

- [ ] **Step 3: Implement the three components**

```js
// components/ResourcePanel.js
import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
const RES=[["cereal","L.Thực"],["timber","Gỗ"],["stone","Đá"],["iron","Sắt"],
 ["gold","Vàng"],["exp_book","Sách EXP"],["up_scroll","Quyển Trục"],["fixator","Máy Cố Định"]];
export default {
 setup(){
  const res=ref({});
  usePolling(async ()=>{ const s=await getJSON("/api/state"); res.value=(s&&s.ok&&s.resources)||{}; },2000);
  return { RES, res };
 },
 template:`<div class="card"><h2>Tài nguyên</h2>
  <div class="kv"><span v-for="[k,l] in RES" :key="k">{{ l }} <b>{{ res[k]??0 }}</b></span></div></div>`
};
```
```js
// components/CityPanel.js
import { getJSON, usePolling } from "../api.js";
const { ref, computed } = window.Vue;
export default {
 setup(){
  const s=ref(null);
  usePolling(async ()=>{ const v=await getJSON("/api/state"); s.value=(v&&v.ok)?v:null; },2000);
  const builds=computed(()=> (s.value&&s.value.builds)||[]);
  const q=computed(()=> s.value&&s.value.build_queue? s.value.build_queue.length : 0);
  return { s, builds, q };
 },
 template:`<div class="card"><h2>Thành chính &amp; công trình</h2>
  <div class="muted">@{{ (s&&s.main_city_index)||"?" }} · hàng đợi {{ q }}/{{ (s&&s.build_queue_slots)||0 }}</div>
  <ul><li v-for="b in builds" :key="b.uid">{{ b.name||("#"+b.id) }} <b>Lv{{ b.lv }}</b></li>
   <li v-if="!builds.length" class="muted">—</li></ul></div>`
};
```
```js
// components/MiscPanel.js
import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const s=ref({}), p=ref({});
  usePolling(async ()=>{ const v=await getJSON("/api/state"); s.value=(v&&v.ok)?v:{}; p.value=(v&&v.player)||{}; },2000);
  return { s, p };
 },
 template:`<div class="card"><h2>Quân &amp; nhiệm vụ</h2>
  <div class="kv">Đội hành quân <b>{{ s.marches??0 }}</b> · Ô đã biết <b>{{ s.areas??0 }}</b></div>
  <div class="kv" style="margin-top:8px">Guide <b>{{ p.guide_tasks??0 }}</b> · Other <b>{{ p.other_tasks??0 }}</b> · Today <b>{{ p.today_tasks??0 }}</b></div></div>`
};
```

- [ ] **Step 4: Mount them in `App.js`**

```js
// components/App.js
import StatusHeader from "./StatusHeader.js";
import ResourcePanel from "./ResourcePanel.js";
import CityPanel from "./CityPanel.js";
import MiscPanel from "./MiscPanel.js";
export default {
 components:{ StatusHeader, ResourcePanel, CityPanel, MiscPanel },
 template:`<div><StatusHeader/><main class="grid">
  <ResourcePanel/><CityPanel/><MiscPanel/>
 </main></div>`
};
```

- [ ] **Step 5: Run tests + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_components.py -q` → PASS.
```bash
git add nta_agent/dashboard/static/components tests/test_dashboard_components.py
git commit -m "feat(dashboard): Resource/City/Misc panels (Vue)"
```

---

### Task 4: Armies + Events panels

**Files:**
- Create: `components/ArmiesPanel.js`, `EventsPanel.js`
- Modify: `components/App.js`
- Test: extend `tests/test_dashboard_components.py`

**Interfaces:**
- Consumes: `getJSON`, `usePolling`, `hms`. Armies polls `/api/armies` (2000ms); Events polls `/api/events?n=50` (2000ms).

- [ ] **Step 1: Add failing assertions**

Append to `tests/test_dashboard_components.py`:
```python
def test_armies_and_events_panels():
    assert "/api/armies" in _c("ArmiesPanel.js")
    assert "tốc hành quân" in _c("ArmiesPanel.js")
    ev = _c("EventsPanel.js")
    assert "/api/events" in ev
    assert "[object Object]" not in ev and "rationale" in ev  # object detail formatting preserved
    app = _app()
    assert "ArmiesPanel" in app and "EventsPanel" in app
```

- [ ] **Step 2: Run → FAIL.** `.venv/Scripts/python.exe -m pytest tests/test_dashboard_components.py -q`

- [ ] **Step 3: Implement**

```js
// components/ArmiesPanel.js
import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){ const armies=ref([]);
  usePolling(async ()=>{ armies.value=(await getJSON("/api/armies"))||[]; },2000);
  return { armies }; },
 template:`<div class="card full"><h2>Đội quân</h2>
  <span v-if="!armies.length" class="muted">—</span>
  <div v-for="a in armies" :key="a.uid" style="margin:8px 0">
   <b>{{ a.name||a.uid }}</b> <span class="muted">· {{ a.state_label }} · tốc hành quân {{ a.march_speed }}</span>
   <ul><li v-for="(p,i) in (a.pawns||[])" :key="i">{{ i+1 }}. {{ p.name }} <b>Lv{{ p.lv }}</b> · tốc {{ p.attack_speed }} · {{ p.equip_name||"—" }}</li>
    <li v-if="!(a.pawns||[]).length" class="muted">trống</li></ul></div></div>`
};
```
```js
// components/EventsPanel.js
import { getJSON, usePolling, hms } from "../api.js";
const { ref } = window.Vue;
function fmt(d){ return d==null? "" : (typeof d==="object" ? (d.rationale||JSON.stringify(d)) : String(d)); }
function line(e){
 return e.kind==="tick"
  ? ("tick "+e.i+" · "+((e.fired||[]).join(", ")||"—"))
  : (e.kind+(e.detail?(" · "+fmt(e.detail)):""));
}
export default {
 setup(){ const evs=ref([]);
  usePolling(async ()=>{ evs.value=((await getJSON("/api/events?n=50"))||[]).slice().reverse(); },2000);
  return { evs, hms, line }; },
 template:`<div class="card full"><h2>Sự kiện gần đây</h2>
  <ul class="feed"><li v-for="(e,i) in evs" :key="i"><span class="muted">{{ hms(e.ts) }}</span> {{ line(e) }}</li>
   <li v-if="!evs.length" class="muted">—</li></ul></div>`
};
```

- [ ] **Step 4: Mount in `App.js`** (add imports + tags; Events goes last in the grid to match current order — but place it after all other panels; for now append both, Events last):

```js
import ArmiesPanel from "./ArmiesPanel.js";
import EventsPanel from "./EventsPanel.js";
// ...components:{ ..., ArmiesPanel, EventsPanel }
// template main: <ResourcePanel/><CityPanel/><MiscPanel/><ArmiesPanel/><EventsPanel/>
```

- [ ] **Step 5: Run + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_components.py -q` → PASS.
```bash
git add nta_agent/dashboard/static/components tests/test_dashboard_components.py
git commit -m "feat(dashboard): Armies + Events panels (Vue)"
```

---

### Task 5: Decisions (+equip action) + Equipment panels

**Files:**
- Create: `components/DecisionsPanel.js`, `EquipmentPanel.js`
- Modify: `components/App.js`
- Test: extend `tests/test_dashboard_components.py`

**Interfaces:**
- Consumes: `getJSON`, `postJSON`, `usePolling`. Decisions polls `/api/decisions`; Equipment polls `/api/equipment`; both POST `/api/command`.

- [ ] **Step 1: Add failing assertions**

```python
def test_decisions_and_equipment_panels():
    dec = _c("DecisionsPanel.js")
    assert "/api/decisions" in dec and "/api/command" in dec and "reroll" in dec
    eq = _c("EquipmentPanel.js")
    assert "/api/equipment" in eq and "equip" in eq
    app = _app()
    assert "DecisionsPanel" in app and "EquipmentPanel" in app
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement**

```js
// components/DecisionsPanel.js
import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const ds=ref([]);
  usePolling(async ()=>{ ds.value=(await getJSON("/api/decisions"))||[]; },2000);
  const sending=ref({});
  async function act(d, o){
   const key=d.track+":"+d.lv+":"+(o?o.ceri_id:"reroll");
   sending.value={...sending.value,[key]:true};
   const cmd=o? {action:"select",track:d.track,lv:d.lv,ceri_id:o.ceri_id}
             : {action:"reroll",track:d.track,lv:d.lv};
   await postJSON("/api/command", cmd);
  }
  const skey=(d,o)=> d.track+":"+d.lv+":"+(o?o.ceri_id:"reroll");
  return { ds, act, sending, skey };
 },
 template:`<div class="card full"><h2>Quyết định đang chờ</h2>
  <span v-if="!ds.length" class="muted">—</span>
  <div v-for="d in ds" :key="d.track+d.lv" style="margin:6px 0">
   <span class="muted">{{ d.track }} · Lv{{ d.lv }}</span><br>
   <template v-for="o in (d.options||[])" :key="o.ceri_id">
    <button :disabled="sending[skey(d,o)]" @click="act(d,o)">{{ sending[skey(d,o)]?"đã gửi…":o.name }}</button>
    <span v-if="o.desc" class="muted">{{ o.desc }}</span><br></template>
   <button :disabled="sending[skey(d,null)]" @click="act(d,null)">{{ sending[skey(d,null)]?"đã gửi…":("Làm mới"+(d.reset_count?(" ("+d.reset_count+")"):" (free)")) }}</button>
  </div></div>`
};
```
```js
// components/EquipmentPanel.js
import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const ps=ref([]); const sending=ref({});
  usePolling(async ()=>{ ps.value=(await getJSON("/api/equipment"))||[]; },2000);
  async function equip(p, o){
   const key=p.pawn_id+":"+o.uid; sending.value={...sending.value,[key]:true};
   await postJSON("/api/command",{action:"equip",pawn_id:p.pawn_id,equip_uid:o.uid,
    skin_id:p.skin_id,attack_speed:p.attack_speed});
  }
  return { ps, equip, sending };
 },
 template:`<div class="card full"><h2>Trang bị lính</h2>
  <span v-if="!ps.length" class="muted">—</span>
  <div v-for="p in ps" :key="p.pawn_id" style="margin:6px 0">
   <span class="muted">{{ p.pawn_name }}</span> — hiện: <b>{{ p.current_equip_name||"—" }}</b><br>
   <template v-for="o in (p.options||[])" :key="o.uid">
    <button :disabled="o.uid===p.current_equip_uid||sending[p.pawn_id+':'+o.uid]" @click="equip(p,o)">{{ sending[p.pawn_id+':'+o.uid]?"đã gửi…":o.name }}</button>
   </template>
   <span v-if="!(p.options||[]).length" class="muted">không có trang bị phù hợp</span>
  </div></div>`
};
```

- [ ] **Step 4: Mount in `App.js`** (order: Resource, City, Misc, Armies, Decisions, Equipment, then Events remains last).

- [ ] **Step 5: Run + commit**

```bash
git add nta_agent/dashboard/static/components tests/test_dashboard_components.py
git commit -m "feat(dashboard): Decisions + Equipment panels (Vue)"
```

---

### Task 6: Territory (canvas map) + Forts panels

**Files:**
- Create: `components/TerritoryPanel.js`, `FortsPanel.js`
- Modify: `components/App.js`
- Test: extend `tests/test_dashboard_components.py`

**Interfaces:**
- Consumes: `getJSON`, `usePolling`. Both poll `/api/territory` + `/api/forts` at 4000ms. Territory owns the `<canvas class="terrmap">` and ports the current `renderTerritoryMap` draw logic verbatim.

- [ ] **Step 1: Add failing assertions**

```python
def test_territory_and_forts_panels():
    terr = _c("TerritoryPanel.js")
    assert "/api/territory" in terr and "/api/forts" in terr
    assert "owned_cells" in terr and "getContext" in terr and "bán kính" in terr
    forts = _c("FortsPanel.js")
    assert "/api/forts" in forts and "Cứ Điểm" in forts
    app = _app()
    assert "TerritoryPanel" in app and "FortsPanel" in app
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement TerritoryPanel** (canvas draw ported from current `renderTerritory`+`renderTerritoryMap`)

```js
// components/TerritoryPanel.js
import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
const idxXY=(i,mw)=>[i%mw, Math.floor(i/mw)];
export default {
 setup(){
  const canvas=ref(null), summary=ref("—"), legend=ref("");
  async function draw(){
   const t=await getJSON("/api/territory"), f=await getJSON("/api/forts");
   if(!t||!f) return;
   const forts=(t.forts||[]);
   summary.value=`Thành chính: ${t.main_city||"?"} · Quân trú: ${(t.garrisons||[]).length}`;
   const cv=canvas.value; if(!cv) return;
   const ctx=cv.getContext("2d"), W=cv.width, H=cv.height; ctx.clearRect(0,0,W,H);
   const mw=t.map_width||600, main=t.main_city||0;
   if(!main){ legend.value="Chưa có dữ liệu bản đồ."; return; }
   const [mx,my]=idxXY(main,mw);
   const owned=f.owned_cells||[];
   const fpts=forts.map(x=>[x.x,x.y]);
   const garr=(t.garrisons||[]).map(i=>idxXY(i,mw));
   const recs=(f.recommendations||[]).map(r=>[r.x,r.y]);
   const R=6;
   const pts=[[mx,my],...owned,...fpts,...garr,...recs,[mx-R,my-R],[mx+R,my+R]];
   const minX=Math.min(...pts.map(p=>p[0]))-1, maxX=Math.max(...pts.map(p=>p[0]))+1;
   const minY=Math.min(...pts.map(p=>p[1]))-1, maxY=Math.max(...pts.map(p=>p[1]))+1;
   const cols=maxX-minX+1, rows=maxY-minY+1;
   const cell=Math.max(3,Math.floor(Math.min(W/cols,H/rows)));
   const ox=Math.floor((W-cols*cell)/2), oy=Math.floor((H-rows*cell)/2);
   const gx=x=>ox+(x-minX)*cell, gy=y=>oy+(y-minY)*cell;
   const box=(x,y,c)=>{ ctx.fillStyle=c; ctx.fillRect(gx(x)+1,gy(y)+1,cell-2,cell-2); };
   ctx.strokeStyle="#3b6ea5"; ctx.lineWidth=1.5; ctx.setLineDash([4,3]);
   ctx.strokeRect(gx(mx-R)+0.5,gy(my-R)+0.5,(2*R+1)*cell,(2*R+1)*cell); ctx.setLineDash([]);
   owned.forEach(([x,y])=>box(x,y,"#2e7d5b"));
   ctx.strokeStyle="#c9a227"; ctx.lineWidth=1.5;
   garr.forEach(([x,y])=>ctx.strokeRect(gx(x)+2,gy(y)+2,cell-4,cell-4));
   fpts.forEach(([x,y])=>box(x,y,"#e08a2b"));
   recs.forEach(([x,y])=>{ ctx.strokeStyle="#e5484d"; ctx.lineWidth=2; ctx.beginPath();
    ctx.arc(gx(x)+cell/2,gy(y)+cell/2,Math.max(3,cell/2-1),0,Math.PI*2); ctx.stroke(); });
   box(mx,my,"#3b82f6");
   legend.value=`🟦 thành chính · 🟩 ô đã chiếm (${owned.length}) · 🟨 quân trú (${garr.length}) · `
    +`🟧 Cứ Điểm (${fpts.length}) · 🔴 gợi ý (${recs.length}) · ⬚ nét đứt = bán kính ${R} ô (đã tăng tốc)`;
  }
  usePolling(draw, 4000);
  return { canvas, summary, legend };
 },
 template:`<div class="card full"><h2>Lãnh thổ</h2>
  <div class="muted">{{ summary }}</div>
  <canvas ref="canvas" class="terrmap" width="640" height="360"></canvas>
  <div class="muted" style="margin-top:6px;font-size:12px">{{ legend }}</div></div>`
};
```
```js
// components/FortsPanel.js
import { getJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){ const f=ref({owned_count:0,recommendations:[]});
  usePolling(async ()=>{ f.value=(await getJSON("/api/forts"))||{owned_count:0,recommendations:[]}; },4000);
  return { f }; },
 template:`<div class="card full"><h2>Cứ Điểm — gợi ý</h2>
  <div>Ô đã chiếm: <b>{{ f.owned_count||0 }}</b></div>
  <div style="margin-top:6px">
   <div v-for="(r,i) in (f.recommendations||[])" :key="i">{{ i+1 }}. Xây Cứ Điểm @{{ r.index }} ({{ r.x }},{{ r.y }}) — {{ r.reason||"" }}</div>
   <div v-if="!(f.recommendations||[]).length">Chưa có gợi ý</div></div></div>`
};
```

- [ ] **Step 4: Mount in `App.js`** (order: …Equipment, TerritoryPanel, FortsPanel, then Events last).

- [ ] **Step 5: Run + commit**

```bash
git add nta_agent/dashboard/static/components tests/test_dashboard_components.py
git commit -m "feat(dashboard): Territory map + Forts panels (Vue)"
```

---

### Task 7: BuildOrder panel (drag-drop + ▲▼ + skip + save)

**Files:**
- Create: `components/BuildOrderPanel.js`
- Modify: `components/App.js`
- Test: extend `tests/test_dashboard_components.py`

**Interfaces:**
- Consumes: `getJSON`, `postJSON`, `usePolling`. Loads `/api/profile`; POSTs `/api/profile` `{order:[ids], skip:[ids]}`. Reorder via native drag-drop + ▲▼; skip via checkbox.

- [ ] **Step 1: Add failing assertions**

```python
def test_build_order_panel():
    bo = _c("BuildOrderPanel.js")
    assert "/api/profile" in bo
    assert "draggable" in bo and "Lưu thứ tự xây" in bo and "bỏ qua" in bo
    assert "BuildOrderPanel" in _app()
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement** (reactive rows; drag handlers reorder the `rows` array)

```js
// components/BuildOrderPanel.js
import { getJSON, postJSON } from "../api.js";
const { ref, onMounted } = window.Vue;
export default {
 setup(){
  const rows=ref([]);   // [{id, name, skip}]
  const names=ref({}); const msg=ref(""); const dragId=ref(null);
  async function load(){
   const p=await getJSON("/api/profile"); if(!p) return;
   names.value=p.names||{};
   const b=p.build||{order:[],skip:[]};
   const skip=new Set((b.skip||[]).map(Number));
   const cat=(p.catalogue||[]).map(c=>c.id);
   const order=(b.order||[]).map(Number).filter(i=>cat.includes(i));
   const ids=order.concat(cat.filter(i=>!order.includes(i)));
   rows.value=ids.map(id=>({id, name:(names.value[id]||("#"+id)), skip:skip.has(id)}));
  }
  onMounted(load);
  const idxOf=id=>rows.value.findIndex(r=>r.id===id);
  function move(id,dir){ const i=idxOf(id), j=i+dir;
   if(i<0||j<0||j>=rows.value.length) return;
   const a=[...rows.value]; [a[i],a[j]]=[a[j],a[i]]; rows.value=a; }
  function onDragStart(id){ dragId.value=id; }
  function onDragOver(id,ev){ ev.preventDefault();
   if(dragId.value==null||dragId.value===id) return;
   const from=idxOf(dragId.value), to=idxOf(id);
   const a=[...rows.value]; const [m]=a.splice(from,1); a.splice(to,0,m); rows.value=a; }
  function onDragEnd(){ dragId.value=null; }
  async function save(){
   msg.value=" đang lưu…";
   const order=rows.value.map(r=>r.id);
   const skip=rows.value.filter(r=>r.skip).map(r=>r.id);
   const o=await postJSON("/api/profile",{order,skip});
   msg.value=(o&&o.ok)?" ✓ đã lưu":(" ⚠️ "+((o&&o.error)||"lỗi"));
   load();
  }
  return { rows, msg, dragId, move, onDragStart, onDragOver, onDragEnd, save };
 },
 template:`<div class="card full"><h2>Xây dựng — Thứ tự xây &amp; Bỏ qua</h2>
  <div class="muted">Kéo-thả hoặc ▲▼ để đổi ưu tiên; tick "bỏ qua" để agent không tự đụng.</div>
  <ul class="bolist">
   <li v-for="r in rows" :key="r.id" draggable="true" :class="{drag:dragId===r.id, skip:r.skip}"
    @dragstart="onDragStart(r.id)" @dragover="onDragOver(r.id,$event)" @dragend="onDragEnd">
    <span class="grip">⠿</span>
    <span class="nm">{{ r.name }} <span class="muted">({{ r.id }})</span></span>
    <button title="Lên" @click="move(r.id,-1)">▲</button>
    <button title="Xuống" @click="move(r.id,1)">▼</button>
    <label><input type="checkbox" v-model="r.skip"> bỏ qua</label>
   </li></ul>
  <button style="margin-top:6px" @click="save">Lưu thứ tự xây</button>
  <span class="muted">{{ msg }}</span></div>`
};
```

- [ ] **Step 4: Mount in `App.js`** (order: …Forts, BuildOrderPanel, then Events last).

- [ ] **Step 5: Run + commit**

```bash
git add nta_agent/dashboard/static/components tests/test_dashboard_components.py
git commit -m "feat(dashboard): BuildOrder panel with drag-drop (Vue)"
```

---

### Task 8: Brain chat panel + parity sweep + live verify + cleanup

**Files:**
- Create: `components/BrainChatPanel.js`
- Modify: `components/App.js` (final panel order matching the original page)
- Test: extend `tests/test_dashboard_components.py`; full suite

**Interfaces:**
- Consumes: `getJSON`, `postJSON`. POSTs `/api/chat` `{message}`; renders the reply + a tactics summary from the response (`active`, `presets`, `notes`).

- [ ] **Step 1: Add failing assertions**

```python
def test_brain_chat_panel_and_final_order():
    ch = _c("BrainChatPanel.js")
    assert "/api/chat" in ch and "Chiến thuật" in ch and "Gửi" in ch
    app = _app()
    # final grid order (Events last)
    order = [app.index(c) for c in ("ResourcePanel","CityPanel","MiscPanel","ArmiesPanel",
        "DecisionsPanel","EquipmentPanel","TerritoryPanel","FortsPanel","BuildOrderPanel",
        "BrainChatPanel","EventsPanel")]
    assert order == sorted(order)  # appear in this order in the template
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement BrainChatPanel** (ports `renderTactics`+`sendChat`)

```js
// components/BrainChatPanel.js
import { postJSON } from "../api.js";
const { ref } = window.Vue;
export default {
 setup(){
  const tactics=ref(null), log=ref([]), input=ref(""), busy=ref(false);
  function say(who,text){ log.value=[...log.value,{who,text}]; }
  async function send(){
   const msg=input.value.trim(); if(!msg) return;
   input.value=""; say("Bạn",msg); busy.value=true;
   const o=await postJSON("/api/chat",{message:msg});
   if(!o){ say("Brain","⚠️ lỗi mạng"); }
   else if(!o.ok){ say("Brain","⚠️ "+(o.error||"lỗi")); }
   else{ say("Brain",(o.rationale||"đã cập nhật")+" — "+JSON.stringify(o.applied));
    tactics.value={active:o.active,presets:o.presets,notes:o.notes}; }
   busy.value=false;
  }
  return { tactics, log, input, busy, send };
 },
 template:`<div class="card full"><h2>Chiến thuật (brain)</h2>
  <div v-if="tactics" class="muted">Đội hình đang dùng: <b>{{ tactics.active||"(mặc định)" }}</b> · Presets: {{ (tactics.presets||[]).join(", ")||"—" }}
   <ul><li v-for="(n,i) in (tactics.notes||[])" :key="i">{{ n }}</li><li v-if="!(tactics.notes||[]).length" class="muted">—</li></ul></div>
  <div v-else class="muted">—</div>
  <div class="feed" style="max-height:200px;overflow:auto;margin:8px 0">
   <div v-for="(l,i) in log" :key="i"><b>{{ l.who }}:</b> {{ l.text }}</div></div>
  <div style="display:flex;gap:6px">
   <input v-model="input" @keydown.enter="send" style="flex:1"
    placeholder="Ra chỉ thị cho brain (vd: tạo đội hình 'rùa' 1 khiên 4 IMP)…"/>
   <button :disabled="busy" @click="send">Gửi</button></div></div>`
};
```

- [ ] **Step 4: Finalize `App.js` panel order** (match the original page exactly):

```js
// components/App.js
import StatusHeader from "./StatusHeader.js";
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
export default {
 components:{ StatusHeader, ResourcePanel, CityPanel, MiscPanel, ArmiesPanel, DecisionsPanel,
  EquipmentPanel, TerritoryPanel, FortsPanel, BuildOrderPanel, BrainChatPanel, EventsPanel },
 template:`<div><StatusHeader/><main class="grid">
  <ResourcePanel/><CityPanel/><MiscPanel/><ArmiesPanel/><DecisionsPanel/><EquipmentPanel/>
  <TerritoryPanel/><FortsPanel/><BuildOrderPanel/><BrainChatPanel/><EventsPanel/>
 </main></div>`
};
```

- [ ] **Step 5: Full suite + lint**

Run: `.venv/Scripts/python.exe -m pytest -q` → all pass.
Run: `.venv/Scripts/python.exe -m ruff check nta_agent tests` → clean.

- [ ] **Step 6: Live verify on machine A**

Start dashboard (`python -m nta_agent.dashboard`), run one agent tick if needed for data (`python -m nta_agent --once`), open `http://127.0.0.1:8787` in the machine-A browser (select browser "Quyền"), and confirm: all panels render with real data; build-order drag-drop + save works; chat sends; territory map + legend draw; **no console errors**. Screenshot for the user.

- [ ] **Step 7: Commit**

```bash
git add nta_agent/dashboard/static/components tests/test_dashboard_components.py
git commit -m "feat(dashboard): Brain chat panel; complete Vue migration at parity"
```

---

## Self-Review notes (author)

- **Spec coverage**: static serving (T1), shell+design system+api (T2), every panel from §3 parity table (T3-T8), tests + live verify (T8). All covered.
- **Type consistency**: `getJSON`/`postJSON`/`usePolling`/`ago`/`hms` defined in T2 `api.js` and imported unchanged by every later component. Panels registered in `App.js` are added cumulatively; T8 fixes the final order.
- **No placeholders**: every component's full code is inline and is a faithful port of the current `page.py` render functions (verified against `page.py` lines 63-249).
