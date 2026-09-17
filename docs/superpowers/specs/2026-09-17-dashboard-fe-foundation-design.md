# Dashboard FE foundation — Vue 3 (no-build) migration — Design

Date: 2026-09-17
Status: Approved (brainstorming) → pending user review of this spec
Owner: NTA-Agent dashboard (server.py, page.py, new static assets)

## 1. Problem

The dashboard UI lives in one ~450-line inline HTML+CSS+JS string (`page.py`
`INDEX_HTML`), rendered by hand with `document.getElementById(...).innerHTML`.
It works but does not scale: upcoming interaction features (bot control, runtime
status, an interactive territory map, and later a brain "tactics library") will
pile more imperative DOM code into one string that is hard to structure, style
consistently, and reason about. We want a component-based frontend and a small
design system as the foundation for those features — **without** adding a Node
build toolchain to this Python-first, single-operator project.

This spec covers **only** the migration to that foundation at feature parity.
Bot control + status (A+B) and the interactive map (D) are separate specs built
on top of it.

## 2. Goals / non-goals

**Goals**
- Replace the imperative page with a **Vue 3** component app, **vendored** (the
  official global build shipped as a static file) — no npm, no bundler, no build
  step. `python -m nta_agent.dashboard` remains the only command.
- A small **design system**: CSS custom properties (color, spacing, radius,
  typography) in one stylesheet, replacing scattered inline styles.
- **Feature parity**: every current panel and interaction behaves the same.
- Serve JS/CSS/vendor as static files from the existing stdlib HTTP server.

**Non-goals**
- No A/B/D features (separate specs).
- No build toolchain (Vite/webpack/npm), no TypeScript, no SFC `.vue` compiler.
- No light/dark theming (dashboard stays dark-only).
- No changes to backend `/api/*` endpoints or their JSON shapes.
- No new runtime dependency fetched from the internet at page load (vendored).

## 3. Current surface (parity checklist)

Panels in `INDEX_HTML` + their data source (all must survive):

| Panel (id) | Source | Interaction |
|---|---|---|
| status header (`#status`) | `/api/state` freshness | dot + text |
| Tài nguyên (`#res`) | `/api/state` | — |
| Thành chính & công trình (`#city`) | `/api/state` | — |
| Quân & nhiệm vụ (`#misc`) | `/api/state` | — |
| Đội quân (`#armies`) | `/api/armies` | — |
| Quyết định đang chờ (`#decisions`) | `/api/decisions` | equip buttons → POST `/api/command` |
| Trang bị lính (`#equipment`) | `/api/equipment` | — |
| Lãnh thổ (`#territory` + `#terrmap` canvas + `#terrlegend`) | `/api/territory` + `/api/forts` | canvas mini-map |
| Cứ Điểm — gợi ý (`#forts`) | `/api/forts` | — |
| Xây dựng (`#buildorder`) | `/api/profile` | drag-drop + ▲▼ + skip checkbox → POST `/api/profile` |
| Chiến thuật / chat (`#chatlog`,`#chatin`) | POST `/api/chat` | send message |
| Sự kiện (`#feed`) | `/api/events` | — |

Polling today: `refresh` every 2s; territory/forts every 4s. Preserve cadence.

## 4. Architecture

### 4.1 Serving
- New package dir `nta_agent/dashboard/static/` holding:
  - `vendor/vue.global.prod.js` — the pinned Vue 3 global build (committed; it
    defines the global `Vue`). Record the exact version in a comment header.
  - `app.css` — design system + component styles.
  - `app.js` — ES module entry: `import`s component modules, creates the app.
  - `components/*.js` — one ES module per component (template string + logic).
- `INDEX_HTML` becomes a thin shell: `<div id="app"></div>`, a `<script
  src="/static/vendor/vue.global.prod.js">`, `<link rel=stylesheet
  href="/static/app.css">`, and `<script type="module" src="/static/app.js">`.
- `server.py`: add a `GET /static/<path>` branch → `serve_static(cfg-independent
  dir, path)`:
  - Resolve against `Path(__file__).parent / "static"`; **reject traversal**
    (resolved path must stay within the static dir) → 404.
  - Whitelist content-types by extension: `.js`→`text/javascript`,
    `.css`→`text/css`, `.mjs`→`text/javascript`. Unknown ext → 404.
  - Read bytes, send 200 with `Content-Type; charset=utf-8`.

### 4.2 App structure (no build)
- Vue global build via plain `<script>` (exposes `window.Vue`).
- `app.js` (ES module) uses `const { createApp, ref, onMounted, ... } = Vue;`
  and imports component definitions from `./components/*.js` (native ES modules,
  served static — browsers load them directly, no bundler).
- Components (one per file), each an object `{ props, setup()/data, template }`:
  `StatusHeader`, `ResourcePanel`, `CityPanel`, `MiscPanel`, `ArmiesPanel`,
  `DecisionsPanel`, `EquipmentPanel`, `TerritoryPanel` (owns the `<canvas>` map
  draw logic ported verbatim), `FortsPanel`, `BuildOrderPanel` (drag-drop+▲▼+skip
  ported), `BrainChatPanel`, `EventsPanel`.
- A shared `api.js` module: `getJSON(url)`, `postJSON(url, body)` (try/catch →
  null / error object, matching today's `j()` helper) + a `usePolling(fn, ms)`
  helper (setInterval + immediate call + onUnmounted clear).
- Root `App` component composes the panels in the current grid order.

### 4.3 Design system (`app.css`)
- `:root` tokens: `--bg:#0f1216; --panel:#171b21; --border:#262c34;
  --border-hi:#3a4450; --text:#e6e6e6; --muted:#8b949e; --accent:#58a6ff;
  --ok:#3fb950; --warn:#d29922; --danger:#f85149;` spacing `--sp-1..--sp-4`,
  `--radius:8px`, mono/system font stacks.
- Component classes (`.card`, `.kv`, `.feed`, `.bolist`, `button`, `.dot`) moved
  here verbatim in behavior but expressed via tokens. No inline styles in
  templates except dynamic (canvas sizing).

## 5. Data flow

Unchanged: components fetch `/api/*` on mount + on their polling interval and
render reactively. POSTs (`/api/chat`, `/api/profile`, `/api/command`) unchanged.
The canvas map keeps its current combine-two-endpoints logic, now inside
`TerritoryPanel`.

## 6. Error handling

- `getJSON` returns `null` on network/parse failure; panels render their muted
  placeholder (parity with today).
- Static handler: traversal or unknown extension → 404; missing file → 404.
- Vendored Vue means no dependence on browser internet access.

## 7. Testing

- **Static serving**: `GET /static/app.js` → 200 `text/javascript`;
  `GET /static/vendor/vue.global.prod.js` → 200; `GET /static/../server.py` (and
  encoded variants) → 404; unknown extension → 404.
- **Shell**: `INDEX_HTML` contains `id="app"`, the vendor script, `app.css`, and
  the module `app.js` reference.
- **Parity markers**: assert served component/app files contain each panel's key
  markers + endpoints (`/api/state`, `/api/forts`, `renderTerritoryMap` logic,
  `buildorder`, `/api/chat`, `owned_cells`, drag-drop handlers). Move the current
  `test_dashboard_page.py` assertions to read the served static files.
- **Endpoint tests**: unchanged (server behavior identical).
- Full `pytest -q` + `ruff`.
- **Live verify** on the real emulator via the browser on machine A: every panel
  renders with real data, build-order drag-drop + save works, chat works, the
  territory map + legend render, no console errors.

## 8. Migration approach

Port panel-by-panel to keep diffs reviewable, but land as one coherent change
(the page is replaced atomically). Keep the exact grid order and copy. Vue
version pinned and vendored in the first task; note the version in the file
header and in this spec on completion.
