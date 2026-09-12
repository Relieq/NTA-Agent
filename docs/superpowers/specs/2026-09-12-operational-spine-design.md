# Operational Spine (Chặng 2A) — Design

Date: 2026-09-12
Status: Approved (brainstorming) → ready for implementation plan
Parent: Chặng 2 (operational spine + dashboard + decision-queue + captcha), sub-project 2A

## 1. Problem

The agent loop (`nta_agent/execution/agent.py` — `Agent.run`) already does
observe→decide→act with connection/token recovery and exposes `on_event(kind,
detail)` and `on_tick(i, fired, state)` hooks. What is missing is a **production
entrypoint** that:

- wires bootstrap (device + rotating token) → `GameSession` → `Agent` → `run`,
- is configurable without editing code,
- logs in a structured, machine-readable way, and
- **exports live `GameState`** so a separate dashboard process (sub-project 2B)
  can read it.

`scripts/smoke_agent.py` is the throwaway minimal version (hardcoded token path
and distinct id, 3 ticks, prints). 2A turns that into a real, unattended runtime.

## 2. Chosen approach (decisions locked)

- **State-export seam:** each tick the spine writes an **atomic JSON snapshot** of
  `GameState` and appends structured events to a **JSONL** log. The dashboard (2B)
  is a **separate process** that reads these files. This keeps the spine free of
  any web dependency, decouples lifecycles (dashboard up/down is irrelevant to the
  agent), and survives restarts. Slight polling lag is acceptable for monitoring.
- **Config:** environment variables with the existing `NTA_` prefix convention
  (see `nta_agent/config.py`), parsed into a `RuntimeConfig` dataclass. Secrets
  (distinct id, account token) come from env or a gitignored file, never committed.
- **Isolation:** operational concerns live in a new `nta_agent/runtime/` package,
  separate from `execution/` (hands) and `io/` (adapters).

## 3. Architecture

New package `nta_agent/runtime/`, four small focused units + a `__main__`.

### 3.1 `runtime/config.py`
`RuntimeConfig` dataclass, built by `RuntimeConfig.from_env()`:

- `host: str` — MQTT server host (`NTA_SERVER_HOST`, default `nine-hk.twomiles.cn`).
- `distinct_id: str` — device/account distinct id (`NTA_DISTINCT_ID`, required).
- `token_path: Path` — rotating account token file (`NTA_TOKEN_PATH`, default `build/nta_token.txt`).
- `interval: float` — seconds between ticks (`NTA_TICK_INTERVAL`, default `5.0`).
- `max_backoff: float` — recovery backoff cap (`NTA_MAX_BACKOFF`, default `60.0`).
- `log_dir: Path` — where snapshot + event log live (`NTA_LOG_DIR`, default `build/run`).
- `snapshot_path: Path` — derived `log_dir/state.json`.
- `event_log_path: Path` — derived `log_dir/events.jsonl`.
- Device/adb config is reused from `nta_agent/config.py` (not duplicated).

`from_env()` raises a clear `ConfigError` naming the missing variable when a
required value (distinct id) is absent.

### 3.2 `runtime/snapshot.py`
- `state_to_dict(state: GameState) -> dict` — a **stable** serializable view:
  `resources` (all fields), `main_city_index`, `builds` (id/uid/lv/index),
  `marches` (count + summaries), `areas` (count), `build_queue`,
  `build_queue_slots`, `production`, `granary_cap`, `warehouse_cap`, `source`,
  `updated_at`, and a small `player` subset (guide/other/today task counts,
  pawnSlots ids). Never dumps the whole `raw` (may be large / non-serializable).
- `write_snapshot(state, path)` — serialize + write **atomically** (`path.tmp`
  then `os.replace`). Creates parent dirs. Returns the dict written.

### 3.3 `runtime/eventlog.py`
- `EventLog(path)` with `append(kind: str, detail=None)` writing one JSON object
  per line: `{"ts": <epoch>, "kind": ..., "detail": <json-safe>}`. Non-json-safe
  details are `str()`-coerced. Opens in append mode; creates parent dirs.
- `tick(i, fired, state)` convenience → appends a compact tick summary
  (`{"ts", "kind":"tick", "i", "fired", "cereal","timber","stone"}`).

### 3.4 `runtime/runner.py`
- `build_session(cfg) -> GameSession` — construct `DeviceManager` (from
  `nta_agent/config.py`), `make_token_refresher(dm, cfg.token_path)`, then
  `GameSession(server=ServerConfig(host=cfg.host), token_path=cfg.token_path,
  token_refresher=refresher)`; `connect()`, `login(distinct_id)`,
  `enter_game(distinct_id)`.
- `run(cfg, *, ticks=0)` — build the session, an `EventLog`, and an `Agent`
  wired with `on_event=eventlog.append`; then `agent.run(ticks=ticks,
  interval=cfg.interval, on_tick=<write snapshot + eventlog.tick>)`. Installs a
  SIGINT handler for **graceful shutdown**: stop the loop, write a final
  snapshot, `session.close()`. Snapshot/log write errors are caught and logged
  to the event log + stderr, never propagated into the loop.

### 3.5 `nta_agent/__main__.py`
Thin CLI: `--ticks N` (0 = forever), `--once` (ticks=1). Loads
`RuntimeConfig.from_env()`, calls `runner.run(cfg, ticks=...)`, maps
`ConfigError`/`TokenChainBroken` to a clear message + non-zero exit. Runnable as
`python -m nta_agent`.

## 4. Data flow

```
env → RuntimeConfig.from_env()
    → runner.build_session (DeviceManager + token refresher → GameSession
      → connect → login → enter_game)
    → Agent(session, on_event=eventlog.append)
    → agent.run(interval, on_tick):
          each tick: session.sync() + engine.tick()  (existing)
          on_tick → write_snapshot(state, cfg.snapshot_path)  [atomic]
                  → eventlog.tick(i, fired, state)
          on_event(kind, detail) → eventlog.append(kind, detail)
    → SIGINT → stop loop → final snapshot → session.close()
```
Dashboard (2B, separate process) polls `cfg.snapshot_path` + tails
`cfg.event_log_path`.

## 5. Error handling

- **Recovery:** unchanged — `Agent` handles transient errors with backoff and
  token refresh; `TokenChainBroken` with no refresher propagates out of `run`.
- **Fatal at startup:** missing config → `ConfigError` → message + exit 2.
  Bootstrap/login failure → surfaced with context → exit 1.
- **Fatal at runtime:** `TokenChainBroken` (refresher absent or failed) → log
  `fatal` event, write final snapshot, exit 1.
- **Non-fatal:** snapshot/eventlog write failures are caught, logged to stderr,
  and the loop continues — observability must never take down the agent.

## 6. Testing (TDD, no live network)

- **snapshot:** `state_to_dict` returns the documented keys for a populated
  `GameState`; is JSON-serializable; omits `raw`. `write_snapshot` writes atomically
  (result file parses back equal; no leftover `.tmp`).
- **eventlog:** `append`/`tick` produce one parseable JSON object per line;
  non-serializable detail is coerced; file is created with parents.
- **runner:** with a **fake session** (stub `sync`/`state`/`close`) and a **fake
  Agent** (or the real `Agent` over a fake session) — `run(cfg, ticks=3)` writes a
  snapshot each tick and N tick events, and calls `session.close()` on completion;
  a simulated SIGINT writes a final snapshot and closes. `build_session` wiring is
  tested with monkeypatched bootstrap (no device).
- **config:** `from_env` reads overrides and raises `ConfigError` when
  `distinct_id` is missing.
- Live execution stays in `scripts/` (extend `smoke_agent.py`) / the `--once` path.

## 7. Out of scope (later 2B–2D sub-projects)

- The dashboard web server and UI (2B) — only the file seam is built here.
- Human-decision queue (2C) and captcha handling (2D).
- Log rotation policy beyond a single appended file (revisit if it grows).
