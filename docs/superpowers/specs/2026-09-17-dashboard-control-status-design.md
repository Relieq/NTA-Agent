# Dashboard bot control + runtime status (A+B) — Design

Date: 2026-09-17
Status: Approved (brainstorming: dashboard-supervisor model) → pending user review of this spec
Owner: NTA-Agent runtime (agent/runner/config/control) + dashboard (supervisor/server/FE)

## 1. Problem

The dashboard can observe the agent but cannot **control** it: starting,
pausing, resuming, and stopping the agent all happen from a terminal. And it
shows no clear **engine state** (running/paused/stopped/crashed) — only a
green dot derived from snapshot freshness, which stays "on" even when the agent
is dead. We want, from the dashboard: Start / Pause / Resume / Stop buttons
(A) and a clear runtime status row (B).

Built on the Vue FE foundation (already merged). The interactive map (D) is a
separate spec.

## 2. Chosen model (approved in brainstorming)

**Dashboard supervises the agent as a child process.** Rationale (single
operator, single account, API login kicks the client so only one agent may run
at a time, dashboard is the always-open home base): the dashboard is the one
place that starts/stops the agent, so it owns the child's lifecycle and can lock
out double-starts. The agent runs as a **separate child process** (not embedded)
so a crash never takes the dashboard down.

- Control channel: a small JSON file `build/run/control.json = {"paused": bool,
  "stop": bool}` (in `log_dir`).
- The agent loop reads it each tick: `stop` → break the loop → `finally` closes
  the game session cleanly; `paused` → skip acting but keep syncing state +
  writing the snapshot + **keeping the game session alive** (instant resume).
- Engine state is derived by the supervisor from the child process + the pause
  flag: no child → `STOPPED`; child alive & not paused → `RUNNING`; child alive
  & paused → `PAUSED`; child exited on its own (not a user Stop) → `CRASHED`
  (remember the exit code).

## 3. Goals / non-goals

**Goals**
- Start/Pause/Resume/Stop the agent from the dashboard; enforce one-at-a-time.
- A runtime status row: engine state + PID + uptime + snapshot age, plus the
  existing combat/build info.
- Backward compatible: `python -m nta_agent` run standalone (no `control.json`)
  behaves exactly as today.

**Non-goals**
- No interactive map / accept-reject recs (spec D).
- No adopting an externally-started agent across a dashboard restart (v1 manages
  only children it spawned; a restart shows `STOPPED` until Start is pressed).
- No multi-agent/multi-account supervision.
- No auth on the control endpoints (localhost-only, single operator).

## 4. Architecture & components

| File | Responsibility |
|---|---|
| `nta_agent/runtime/control.py` (new) | `read_mode(path) -> "run"\|"pause"\|"stop"` (missing/invalid file → "run"); `write_control(path, *, paused=None, stop=None)` merges flags into the JSON (create dir); `reset(path)` writes `{paused:false, stop:false}`. Pure file I/O. |
| `nta_agent/runtime/config.py` | Add `control_path` property → `log_dir/"control.json"`. |
| `nta_agent/execution/agent.py` | `run(..., control=None)`: `control` is a zero-arg callable returning the mode. Each iteration: `stop` → break; `pause` → `self.session.sync()` only (no `engine.tick`), `fired=[]`; else normal `tick()`. `on_tick` still called (so the snapshot stays fresh while paused). |
| `nta_agent/runtime/runner.py` | Build `control=lambda: read_mode(cfg.control_path)`; pass to `agent.run`. In `on_tick`, when the mode is `pause`, run only snapshot + event log and **skip** the acting services (decision `service`, `brain`, `forts`). Always write the snapshot. |
| `nta_agent/dashboard/supervisor.py` (new) | `AgentSupervisor(cfg)` manages one child via `subprocess.Popen([sys.executable, "-m", "nta_agent"])` (inherits env + cwd). Thread-safe (a `Lock`). Methods: `start()`, `stop(timeout=10)`, `pause()`, `resume()`, `status() -> dict`. |
| `nta_agent/dashboard/server.py` | Create one `AgentSupervisor` on `DashboardServer`; routes: `POST /api/agent/start\|stop\|pause\|resume` → the matching method → return `status()`; `GET /api/agent/status`. |
| `nta_agent/dashboard/static/components/ControlBar.js` (new) | Buttons + engine indicator; polls `/api/agent/status` (1000ms); posts control actions. Placed in the header row. |
| `static/components/StatusHeader.js` + `App.js` | Header hosts `ControlBar`; a `RuntimeStatus` line (engine/pid/uptime/snapshot-age + combat/build from `/api/state`). |

### 4.1 Supervisor behavior
- `start()`: if a child is alive → no-op, return status. Else `reset(control_path)`,
  `Popen([...])`, record `started_at`, clear `_user_stopped`/`_last_exit`.
- `stop(timeout)`: `write_control(stop=True)`; wait up to `timeout` for the child
  to exit (poll loop); if still alive → `terminate()`, wait ~3s; if still alive →
  `kill()`. Set `_user_stopped=True`, drop the handle.
- `pause()`/`resume()`: `write_control(paused=True/False)` (only meaningful while
  a child is alive; still written otherwise — harmless).
- `status()`: 
  - child is None → `{engine: "STOPPED" or "CRASHED", pid: null, uptime: 0}`
    (`CRASHED` if the last observed exit was not a user stop and exit code ≠ 0).
  - `poll() is None` (alive) → `RUNNING`, or `PAUSED` if `read_mode==pause`;
    include `pid`, `uptime = now - started_at`.
  - `poll()` returns a code (exited unexpectedly) → mark `_last_exit`, drop handle,
    report `CRASHED` (code) unless `_user_stopped` → `STOPPED`.

### 4.2 Concurrency / safety
- All supervisor mutations under a `threading.Lock` (the HTTP server is threaded).
- The spawned agent inherits the dashboard's environment (so `NTA_DISTINCT_ID`
  etc. flow through) and cwd (so `build/run/*` resolves the same).
- Control endpoints are POST, localhost bind (unchanged). No new external exposure.

## 5. Data flow

```
UI ControlBar --POST /api/agent/start--> supervisor.start() --Popen--> agent child
agent child each tick: read_mode(control.json)
   stop -> break -> session.close();  pause -> sync only;  run -> act
UI ControlBar --GET /api/agent/status (1s)--> supervisor.status() -> {engine,pid,uptime}
UI RuntimeStatus <- /api/agent/status (engine) + /api/state (combat/build/snapshot age)
```

## 6. UI

- **Control bar** in the header, right of the title: `Start` (enabled only when
  STOPPED/CRASHED), `Pause`↔`Resume` (shown per state, enabled when RUNNING/
  PAUSED), `Stop` (enabled when RUNNING/PAUSED). An engine badge colored by
  state: RUNNING=green, PAUSED=amber, STOPPED=grey, CRASHED=red. Disabled
  buttons during the brief transition after a click.
- **Runtime status line** under the header (or a compact card): `Engine: <state>
  · PID <n> · uptime <hms> · snapshot <age>s · combat <mode>/<status> · hàng đợi
  <q>/<slots>`. Engine/pid/uptime from `/api/agent/status`; the rest from
  `/api/state`. Replaces the old snapshot-only dot text.

## 7. Error handling / edge cases

- `control.json` missing/corrupt → `read_mode` returns `"run"` (agent runs
  normally; standalone use unaffected).
- Start when already running → no-op (idempotent), returns current status.
- Stop when nothing running → no-op, returns STOPPED.
- Child dies on its own → next `status()` detects via `poll()`, reports CRASHED
  with the exit code; Start re-enabled.
- Dashboard restart with a child still running → supervisor has no handle → shows
  STOPPED; pressing Start would spawn a second agent. Mitigation: `stop()` also
  writes `stop=True` so a truly-orphaned agent can be stopped by writing the flag
  — but v1 documents "start the agent via the dashboard" as the workflow. (A
  pidfile-based adopt is a noted future enhancement, out of scope here.)
- Pause keeps the session alive (does not log out) so Resume is immediate and
  does not re-kick the game client.

## 8. Testing

- `control.py`: round-trip `write_control`/`read_mode`; merge semantics (setting
  `paused` leaves `stop` untouched); missing/corrupt → `"run"`; `reset` clears both.
- `agent.run(control=...)`: a fake control returning `pause` → `engine.tick` not
  called but `session.sync` is and `on_tick` fires with `fired==[]`; returning
  `stop` → loop breaks promptly; `run` → normal.
- `runner`: paused mode writes a snapshot but does not call the acting services
  (brain/forts/decision) — via fakes.
- `supervisor`: with a fake/mini spawn target (e.g. a dummy `-c` script, or
  monkeypatched `Popen`), assert start→RUNNING, pause→PAUSED (control.json flag),
  stop→STOPPED (control.json stop flag + handle dropped), double-start no-op,
  crashed detection when the fake exits nonzero.
- `server`: POST `/api/agent/*` dispatches to supervisor (monkeypatched) and
  returns its status; GET `/api/agent/status` shape.
- FE: `ControlBar.js` has the four actions + `/api/agent/status`; buttons gated by
  engine state; mounted in the header.
- Full `pytest` + `ruff`; **live verify on machine A**: Start spawns the agent
  (status→RUNNING, ticks appear); Pause freezes acting but snapshot age keeps
  updating and session stays logged in; Resume continues; Stop ends it cleanly
  (STOPPED); no console errors.

## 9. Decomposition

One spec, but implementable as: control primitives + agent/runner gating (A-core,
no UI) → supervisor + endpoints (A-backend) → ControlBar + status UI (A/B-FE).
The plan will sequence these as tasks.
