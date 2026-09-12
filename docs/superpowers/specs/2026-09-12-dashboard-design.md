# Web Dashboard (Chặng 2B) — Design

Date: 2026-09-12
Status: Approved (brainstorming) → ready for implementation plan
Parent: Chặng 2, sub-project 2B (depends on 2A operational spine)

## 1. Problem

The operational spine (2A) writes two seam files each tick: an atomic
`state.json` (a `GameState` snapshot) and an append-only `events.jsonl`. There is
no way to watch a running agent without tailing logs. 2B is a **dependency-free,
read-only local web dashboard** — a separate process that reads those files and
shows, auto-refreshing, what the agent is doing: connection status, resources,
main city + buildings, marching armies, task counts, and a recent-events feed.

Interaction (resolving human decisions) is explicitly **out of scope** — that is
sub-project 2C, which will add POST endpoints to this same server later.

## 2. Chosen approach (decisions locked)

- **Web stack: Python stdlib `http.server`** — no new dependencies, matching the
  project's stdlib-lean ethos; sufficient for a single-user local dashboard.
- **Separate process, read-only:** the dashboard never imports the agent loop; it
  only reads the seam files. It reuses `RuntimeConfig` for their paths.
- **Friendly Vietnamese building names:** builds are shown by their Vietnamese
  name resolved from config (`buildText.json` `.vi`, e.g. 2001→"Thành Chính",
  2004→"Binh Doanh"), falling back to English then `#<id>`. This mapping is a
  **presentation concern done in 2B**; the 2A snapshot keeps raw ids untouched.
- **Bind 127.0.0.1 only** — never exposed off the machine.

## 3. Architecture

New package `nta_agent/dashboard/`, split so the file-reading logic is pure and
testable, the HTTP layer is thin, and the HTML is static.

### 3.1 `dashboard/data.py` (pure, tested)
- `read_state(path: Path) -> dict` — parse the snapshot JSON. Returns
  `{"ok": True, **snapshot}` on success; `{"ok": False}` when the file is missing
  or unparseable (never raises). Guards against a half-written file (returns
  `{"ok": False}` on `JSONDecodeError`).
- `tail_events(path: Path, n: int = 50) -> list[dict]` — return the last `n`
  parseable JSON lines of `events.jsonl` (oldest→newest), skipping blank/corrupt
  lines; `[]` when the file is missing.

### 3.2 `dashboard/names.py` (pure, tested)
- `load_build_names(config_dir: Path | None = None) -> dict[int, str]` — read
  `buildText.json` from the config dir (default `nta_agent/data/config`), return
  `{build_id: vi_name}` using `.vi` (fallback `.en`). Returns `{}` if config is
  absent (dashboard still works, unlabeled).
- `build_label(names: dict[int, str], build_id: int) -> str` — `names.get(id)` or
  `f"#{id}"`.

### 3.3 `dashboard/page.py` (static)
- `INDEX_HTML: str` — one self-contained HTML page: inline CSS + vanilla JS, **no
  external assets** (CSP-safe, offline). The JS polls `/api/state` and
  `/api/events?n=50` every 2s and renders:
  - header: agent status (● running / ○ waiting) + "updated Ns ago" from
    `state.updated_at`;
  - resources (cereal/timber/stone/iron/gold/stamina, with caps where known);
  - main city index + buildings (as `name Lv<lv>`), build queue `used/slots`;
  - marching armies count, areas count;
  - tasks summary (guide/other/today counts);
  - a scrolling recent-events feed (time · kind · fired[]).
  - "waiting for agent…" state when `/api/state` returns `{"ok": false}`.

### 3.4 `dashboard/server.py` (thin HTTP)
- `Handler(BaseHTTPRequestHandler)` with `do_GET`:
  - `/` → 200 `text/html`, `INDEX_HTML`.
  - `/api/state` → 200 `application/json` — `read_state(cfg.snapshot_path)`, and
    when `ok`, enrich each build with `"name": build_label(names, b["id"])`.
  - `/api/events` → 200 `application/json` — `tail_events(cfg.event_log_path, n)`
    (`n` from query, default 50, clamped 1..500).
  - anything else → 404. `log_message` silenced (no stderr spam).
- `serve(cfg: RuntimeConfig, port: int, *, host: str = "127.0.0.1") -> ThreadingHTTPServer`
  — build the server (handler closes over `cfg` + a names map loaded once), used
  by both `__main__` (serve_forever) and tests (started in a thread, on port 0).

### 3.5 `dashboard/__main__.py` (CLI)
- `main(argv=None) -> int`: `--port` (default `NTA_DASHBOARD_PORT` or 8787). Load
  `RuntimeConfig.from_env()`, start `serve`, print `http://127.0.0.1:<port>`,
  `serve_forever()` until Ctrl+C. `python -m nta_agent.dashboard`.

## 4. Data flow

```
2A agent (separate process) → writes state.json + events.jsonl each tick
2B dashboard process:
  browser GET /            → INDEX_HTML
  browser GET /api/state   → read_state(snapshot_path) + build names  → JSON
  browser GET /api/events  → tail_events(event_log_path, n)           → JSON
  page JS polls every 2s and re-renders
```

## 5. Error handling

- Missing/partial seam files → `read_state` `{"ok": false}` / `tail_events` `[]`;
  page shows "waiting for agent…". Never 500 on a missing file.
- Config absent → `load_build_names` `{}` → builds shown as `#<id>`.
- Corrupt JSON lines in events → skipped individually.
- Server binds `127.0.0.1`; handler never raises out (each branch writes a
  response; unexpected errors → 500 with an empty body, logged to stderr only).

## 6. Testing (no browser)

- **data.py:** `read_state` returns the parsed snapshot for a written file;
  `{"ok": false}` for missing and for a truncated/invalid file. `tail_events`
  returns the last N in order, skips blank/corrupt lines, `[]` when missing.
- **names.py:** `load_build_names` maps 2001→"Thành Chính", 2004→"Binh Doanh"
  from the real config (skip if config absent); `build_label` falls back to
  `#<id>` for unknown ids and when the map is empty.
- **server.py:** start `serve(cfg, 0)` in a thread; `urllib` GET `/` (200, HTML
  contains a known title marker), `/api/state` (200, JSON with `ok` and, when a
  snapshot exists, builds carrying `name`), `/api/events?n=2` (200, ≤2 rows). A
  missing snapshot yields `{"ok": false}`.
- **CLI:** `main(["--port","0"])` wiring tested with a fake `serve` (monkeypatched)
  asserting it is called with the configured port; no real bind in unit tests.

## 7. Out of scope (2C/2D)

- Any write/interaction (decision resolution) — 2C adds POST endpoints here.
- Auth/remote exposure, TLS — local-only tool.
- Charts/history beyond the tail feed (revisit with the measurement phase).
