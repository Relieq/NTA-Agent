# Territory map viewport — pan / zoom / hover / click — Design

Date: 2026-09-17
Status: Brainstorming approved (grounded in the old bot's HardDigGridCanvas) → pending user review
Owner: NTA-Agent dashboard FE (`TerritoryPanel.js`)

## 1. Problem

The territory map auto-fits the current bounding box and is only "interactive" on
fort-recommendation rings — so when there are no recs (territory inside radius 6)
it feels dead, and it won't work once the map grows large (no way to move the
view). The old bot's `HardDigGridCanvas` (`D:\NTA-AutoBot\core\gui_app.py:46-307`)
already solved this: a fixed grid with **zoom** (`cell_size` 6-60px), **pan**
(canvas inside a scroll area), **adaptive round-number axis rulers**
(`_label_step`, lines 93-99), a **hover tooltip** `(x, y) | STATE` (214-232), a
**hover highlight**, **game-y-up orientation** (`_display_row_to_game_y`, 87-91),
and **"Về thành chính"** recenter (1526). This spec ports that viewport model to
our Vue `<canvas>`, adapted to modern **drag-to-pan** + **wheel-zoom-at-cursor**.

## 2. Goals / non-goals

**Goals**
- **Drag to pan** the view; **wheel to zoom** centred on the cursor; **+ / −**
  buttons; a **"Về thành chính"** recenter button.
- **Zoom range** `cell` 6-60px (as the old canvas), initial view auto-fits the
  content once (not on every poll).
- **Game-y-up** orientation: y increases upward (`row = (map_width-1) - y`),
  matching the game and the old bot.
- **Adaptive round-number rulers** (X top, Y left) using the old `_label_step`
  ([1,2,5,10,20,25,50,100], first step with `step*cell ≥ 56`), drawn only for the
  visible range; Y labels read game-y.
- **Hover** any cell → highlight + a tooltip `(x, y)` + its state (thành chính /
  đã chiếm / Cứ Điểm / dự kiến / gợi ý / quân trú / trống).
- **Click** any cell → select it: show `(x, y)` + state in a popover; if it is a
  pending rec, the popover also offers Chấp thuận / Từ chối (existing decide flow).
- Only draw cells within the viewport (map may be up to 600×600) for performance.

**Non-goals**
- No shell/layout redesign (separate spec, next).
- No painting/drawing cells (the old canvas was a dig planner; we only view +
  decide on recs).
- No change to `/api/*` endpoints (reuse territory/forts + `/api/forts/decide`).

## 3. Viewport model

State held in the component: `scale` (px/cell, 6-60), `originX`, `originY`
(screen px where world cell (x=0, row=0) is drawn), and margins `ML=28`, `MT=18`
reserved for rulers. Mapping (row is the display row, game-y-up):

```
row(y)      = (MAPW-1) - y                 # MAPW = map_width (600)
screenX(x)  = originX + x*scale
screenY(y)  = originY + row(y)*scale
cellAt(px,py) = { x: floor((px-originX)/scale),
                  y: (MAPW-1) - floor((py-originY)/scale) }
```

- **Pan**: on drag, `originX += dx; originY += dy`.
- **Zoom at cursor** (px,py): `s2 = clamp(scale*f, 6, 60)`; keep the world point
  under the cursor fixed → `originX = px - (px-originX)*s2/scale` (same for Y);
  `scale = s2`.
- **Auto-fit** (initial + recenter-to-fit): compute the content bounding box
  (owned+forts+accepted+recs+main+radius box), pick `scale` and `origin` so it
  fits inside (W-ML)×(H-MT) with a 1-cell margin. Done **once** on first data (or
  when the user hasn't panned/zoomed yet); afterwards data redraws under the
  user-controlled transform without snapping back.
- **"Về thành chính"**: set `scale` to a comfortable value (e.g. 16) and center
  `origin` on the main city.

Data polling (4s) refreshes owned/forts/recs and redraws with the **current**
transform — it never resets the view once the user has interacted.

## 4. Rendering (canvas 2D, ported from the old paintEvent)

- Compute the visible world range from the viewport rect; clamp to [0, MAPW-1];
  iterate only those cells.
- Draw order: radius-6 zone (dashed) → owned (green) → garrisons (outline) →
  forts (orange) → accepted (orange + dark check dot) → rec rings (red) → main
  (blue) → hover highlight (2px ring). Colors reuse the current scheme; the
  categorical set (owned/fort/rec/main/garrison) is validated once with the
  dataviz `scripts/validate_palette.js` and adjusted if any pair FAILs.
- Rulers: fill `ML`/`MT` margins with the surface color; draw tick labels at the
  round-number `step` for visible columns/rows in `--muted`; X labels centered on
  columns along the top, Y labels right-aligned along the left (game-y).
- Everything clipped to the plot area (so marks don't overrun the rulers).

## 5. Interaction

- **Drag vs click**: on mousedown record the point; on mouseup, if the pointer
  moved < 4px total it is a **click** (select the cell under it), else it was a
  **pan** (no selection). Mousemove with button down pans; without button updates
  hover.
- **Hover**: throttle to animation frames; set `hover=(x,y)`; draw the highlight;
  render an absolutely-positioned tooltip near the cursor with `(x,y)` + state.
- **Click select**: set `sel={x,y,index,state, left,top}`; render a popover with
  the coordinate + state; if `state==="gợi ý"` (a pending rec) show Chấp thuận /
  Từ chối → `POST /api/forts/decide` → redraw. Otherwise just an info popover
  with a Đóng button. (This satisfies "clicking a cell shows its coordinates".)
- **Wheel**: `preventDefault`; zoom at cursor. **+ / −** buttons: zoom at center.
- **"Về thành chính"** + **"Vừa khung"** (fit) buttons in a small toolbar above
  the canvas.

## 6. Cell-state lookup

Build a `Map` from cell index → state each draw: main city, forts (auto-support),
accepted, recs, garrisons, owned; first match wins in that priority. Used by both
hover tooltip and click popover so they always agree with what's drawn.

## 7. Error handling / edge

- No data yet (no main) → message, no grid; controls disabled.
- Zoom clamped 6-60; pan unclamped but auto-fit/recenter always brings content
  back. Empty content (only main) still fits on main + radius box.
- Wheel zoom must not scroll the page (`preventDefault`, passive:false listener).
- Resizing the window: canvas is fixed 640×360 backing store shown responsively
  via CSS (as today); pointer math converts client→canvas px via
  `getBoundingClientRect` (already used).

## 8. Testing

- Marker tests in `tests/test_dashboard_components.py` for `TerritoryPanel.js`:
  contains pan handlers (`mousedown`/`mousemove`), `wheel`, zoom clamp (`6`/`60`),
  `_label_step`-style round steps, `getBoundingClientRect`, hover tooltip, click
  coordinate/select, y-flip (`map_width-1` / `599`), and the recenter control.
- Palette: run `node scripts/validate_palette.js "<map hex set>" --mode dark`
  (dataviz) and record PASS (adjust colors if needed).
- Full `pytest` + `ruff`.
- **Live verify on machine A**: drag pans; wheel zooms at cursor; +/−/recenter/fit
  work; hovering shows `(x,y)`+state and a highlight; clicking a cell shows its
  coordinates (and Accept/Reject on a rec); y-axis increases upward; no console
  errors. Screenshot.

## 9. Notes

Pure viewport math (`screenX/screenY/cellAt/labelStep/fit`) is written as small
functions inside the component; if a JS test runner is added later they can be
extracted to a module and unit-tested. For now the Python marker tests + the live
verify are the gate, consistent with the other FE tasks.
