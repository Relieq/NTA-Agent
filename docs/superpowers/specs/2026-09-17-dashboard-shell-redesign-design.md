# Dashboard shell redesign — sidebar + tabs + design system — Design

Date: 2026-09-17
Status: Approved (brainstorming) → pending user review of this spec
Owner: NTA-Agent dashboard FE (static components + design system)

## 1. Problem

The dashboard is one long vertical scroll of ~11 stacked cards. After the Vue
migration the structure is componentised but the *presentation* is unchanged —
it still reads as the old page and requires a lot of scrolling. We want a real
shell: a persistent top bar (title + controls + runtime status), a left sidebar
that switches between grouped sections (tabs), and a small design system (stat
tiles, consistent spacing/typography) informed by the `dataviz` skill. No
backend or data changes — all existing panel components are reused, only
regrouped and restyled.

## 2. Goals / non-goals

**Goals**
- **Top bar** (persistent): title + `ControlBar` (engine + Start/Pause/Stop) +
  a compact runtime status line (snapshot age).
- **Left sidebar** nav switching between **5 tabs**; only the active tab's panels
  render. Sidebar collapses to icons on narrow widths.
- **5 tabs** grouping the existing panels (see §4).
- **Design system**: a reusable **StatTile** for key numbers, consistent card /
  spacing scale / type hierarchy, dark-only, colours kept as tokens (validated
  where categorical). Resource readout becomes a row of stat tiles.
- **Parity**: every existing panel/interaction still works (armies, decisions +
  equip, territory map, forts decide, build-order drag-drop, brain chat, events).

**Non-goals**
- No backend/`/api` changes; no new data.
- No light theme, no routing library (a reactive `activeTab` ref is enough).
- No change to the territory map viewport itself (just where it lives).
- No new gameplay features.

## 3. Architecture

- `App.js` becomes the shell: holds `activeTab` (ref, persisted to
  `localStorage` best-effort), renders `<TopBar/>`, `<Sidebar/>`, and the active
  tab's panel set in a content area (CSS grid). Layout: `grid-template-columns:
  <sidebar> 1fr;` with the top bar spanning full width above.
- New components:
  - `TopBar.js` — title + `ControlBar` (moved out of `StatusHeader`) + runtime
    status line. `StatusHeader.js` is retired/folded in.
  - `Sidebar.js` — nav list (icon glyph + label) bound to `activeTab`; emits tab
    changes; collapses (icons-only) under a width breakpoint.
  - `StatTile.js` — props `{label, value, sub?}`; renders a compact tile (label
    in `--muted`, big value in `--text`). Used for resources + a few KPIs.
- Existing panels are imported and placed into the active tab's template; their
  internals are unchanged. `ResourcePanel` is reworked to render `StatTile`s.
- Polling/behaviour unchanged: panels still fetch on their own intervals. Panels
  in a hidden tab may be unmounted (v-if) — acceptable (they refetch on mount);
  or kept mounted with `v-show` to preserve state. Decision: **`v-if`** (simpler,
  panels are cheap and self-refresh) except the territory map (see §6).

## 4. Tabs (grouping the existing panels)

| Tab | Vietnamese | Panels |
|---|---|---|
| overview | **Tổng quan** | Resource (as stat tiles), City, Misc |
| army | **Quân đội** | Armies, Equipment, Decisions |
| territory | **Lãnh thổ** | Territory map viewport, Forts |
| build | **Xây dựng & Chiến thuật** | BuildOrder, BrainChat |
| log | **Nhật ký** | Events (full height) |

Default tab: `overview`. The top bar's ControlBar + status are visible on every
tab.

## 5. Design system (dataviz-informed)

- Reuse the existing CSS tokens (`--bg/--panel/--border/--accent/--muted/--ok/
  --warn/--danger`, spacing, radius). Add: `--sidebar-w`, a `--tile-*` set if
  needed.
- **StatTile**: label (12px, `--muted`, uppercase-tracked) + value (20-24px,
  `--text`, tabular). Tiles laid out in a responsive `grid` (auto-fit,
  minmax(120px,1fr)). Resources become 8 tiles.
- Type hierarchy: page/tab title, card `h2` (as now), body. Values never wear a
  series colour (dataviz rule); coloured marks (dots) sit beside text.
- Cards keep the current look but spacing is normalised via the scale.
- Sidebar: active item highlighted (accent left-border + tint); hover state.
- Responsive: at ≤ ~760px the sidebar collapses to an icon rail; the content
  grid becomes single-column; stat tiles wrap. Keep the ≥16px side gutter.

## 6. Interaction / edge cases

- Switching tabs sets `activeTab`; content swaps. Restore last tab from
  `localStorage` on load (try/catch; default `overview`).
- **Territory map**: keep it mounted with `v-show` (not `v-if`) so its
  pan/zoom/view state survives tab switches; other tabs use `v-if`.
- ControlBar/status live in the top bar so bot control is always reachable.
- No data/behaviour regressions: same endpoints, same polling.

## 7. Testing

- Component marker tests (served static files): `App.js` defines `activeTab` +
  imports `TopBar`, `Sidebar`, `StatTile` and every existing panel; `Sidebar.js`
  lists the 5 tab labels; `TopBar.js` hosts `ControlBar`; `StatTile.js` renders
  `label`/`value`; `ResourcePanel.js` uses `StatTile`.
- Existing endpoint/panel tests unchanged.
- Full `pytest` + `ruff`.
- **Live verify on machine A** (reuse the existing dashboard tab, don't spawn new
  tabs): each tab shows its panels; ControlBar works from every tab; resources
  render as tiles; territory map keeps its view across tab switches; build-order
  drag-drop, chat, forts decide still work; responsive collapse at narrow width;
  no console errors.

## 8. Migration approach

Introduce `TopBar`/`Sidebar`/`StatTile`, refactor `App.js` into the shell, move
panels into tabs, rework `ResourcePanel` to tiles — landed as one coherent change
(the page is replaced atomically) but built component-by-component. Keep the exact
Vietnamese copy.
