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

**Goals (cont.)**
- **Status survives a dashboard restart** (pidfile-adopt): the supervisor records
  the child PID to a file; on start it adopts a still-running agent, so a restarted
  dashboard shows the true state and can Pause/Resume/Stop it — and Start never
  spawns a second agent while one is alive.

**Non-goals**
- No interactive map / accept-reject recs (spec D).
- No multi-agent/multi-account supervision.
- No auth on the control endpoints (localhost-only, single operator).
- No hardening against PID reuse beyond a `started_at` sanity marker (single-user
  local; reuse window is tiny — documented, not fully solved).

## 4. Architecture & components

| File | Responsibility |
|---|---|
| `nta_agent/runtime/control.py` (new) | `read_mode(path) -> "run"\|"pause"\|"stop"` (missing/invalid file → "run"); `write_control(path, *, paused=None, stop=None)` merges flags into the JSON (create dir); `reset(path)` writes `{paused:false, stop:false}`. Pure file I/O. |
| `nta_agent/runtime/config.py` | Add `control_path` → `log_dir/"control.json"` and `agent_pid_path` → `log_dir/"agent.pid"`. |
| `nta_agent/runtime/proc.py` (new) | `pid_alive(pid) -> bool` cross-platform (POSIX `os.kill(pid,0)`; Windows `ctypes` `OpenProcess`+`GetExitCodeProcess`==STILL_ACTIVE); `hard_kill(pid)` (POSIX `os.kill` SIGTERM/SIGKILL; Windows `taskkill /F /PID`). |
| `nta_agent/execution/agent.py` | `run(..., control=None)`: `control` is a zero-arg callable returning the mode. Each iteration: `stop` → break; `pause` → `self.session.sync()` only (no `engine.tick`), `fired=[]`; else normal `tick()`. `on_tick` still called (so the snapshot stays fresh while paused). |
| `nta_agent/runtime/runner.py` | Build `control=lambda: read_mode(cfg.control_path)`; pass to `agent.run`. In `on_tick`, when the mode is `pause`, run only snapshot + event log and **skip** the acting services (decision `service`, `brain`, `forts`). Always write the snapshot. |
| `nta_agent/dashboard/supervisor.py` (new) | `AgentSupervisor(cfg)` manages one agent, whether spawned here (`subprocess.Popen([sys.executable, "-m", "nta_agent"])`, inherits env+cwd) or **adopted** from `agent_pid_path` on construction. Thread-safe (a `Lock`). Methods: `start()`, `stop(timeout=10)`, `pause()`, `resume()`, `status() -> dict`. Tracks `_proc` (Popen or None when adopted), `_pid`, `_started_at`, `_user_stopped`, `_last_exit`. |
| `nta_agent/dashboard/server.py` | Create one `AgentSupervisor` on `DashboardServer`; routes: `POST /api/agent/start\|stop\|pause\|resume` → the matching method → return `status()`; `GET /api/agent/status`. |
| `nta_agent/dashboard/static/components/ControlBar.js` (new) | Buttons + engine indicator; polls `/api/agent/status` (1000ms); posts control actions. Placed in the header row. |
| `static/components/StatusHeader.js` + `App.js` | Header hosts `ControlBar`; a `RuntimeStatus` line (engine/pid/uptime/snapshot-age + combat/build from `/api/state`). |

### 4.1 Supervisor behavior
- `__init__(cfg)`: **adopt** — read `agent_pid_path` `{pid, started_at}`; if
  `pid_alive(pid)` set `_pid`/`_started_at`, `_proc=None` (adopted); else delete a
  stale pidfile.
- `_alive()`: `_proc.poll() is None` when owned; else `pid_alive(_pid)` when adopted;
  else `False`.
- `start()`: if `_alive()` → no-op, return status (never a second agent). Else
  `reset(control_path)`, `Popen([...])`, set `_pid=proc.pid`, `_started_at=now`,
  write `agent_pid_path` `{pid, started_at}`, clear `_user_stopped`/`_last_exit`.
- `stop(timeout)`: `write_control(stop=True)`; wait up to `timeout` for `_alive()`
  to go false (the agent honors `stop` and exits); if still alive → owned:
  `terminate()` then `kill()`; adopted: `hard_kill(_pid)`. Set `_user_stopped=True`,
  delete the pidfile, clear handles.
- `pause()`/`resume()`: `write_control(paused=True/False)`.
- `status()`:
  - `_alive()` → `RUNNING`, or `PAUSED` if `read_mode(control_path)=="pause"`;
    include `pid`, `uptime = now - _started_at`.
  - owned child exited unexpectedly (`poll()` returns a code) → record `_last_exit`,
    delete pidfile, drop handle → `CRASHED` (code) unless `_user_stopped` → `STOPPED`.
  - nothing alive → `STOPPED` (or `CRASHED` if the last observed exit was not a user
    stop and code ≠ 0). `pid: null`, `uptime: 0`.
- PID-reuse guard: the pidfile carries `started_at`; adoption is best-effort. Worst
  case a reused live PID blocks Start — the user can Stop (writes the flag; if that
  PID is not our agent, `hard_kill` clears it) then Start.

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
- Dashboard restart with a child still running → the new supervisor **adopts** it
  via `agent_pid_path` (shows RUNNING/PAUSED, controllable); Start stays locked
  while it is alive, so no second agent is spawned.
- Stale pidfile (agent died without cleanup) → `pid_alive` is false → pidfile
  deleted on construction/status; Start works normally.
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
- `proc`: `pid_alive(os.getpid())` is True; `pid_alive(<unused pid>)` is False.
- `supervisor`: with monkeypatched `Popen`/`pid_alive`, assert start→RUNNING,
  pause→PAUSED (control.json flag), stop→STOPPED (stop flag + pidfile deleted),
  double-start no-op, crashed detection when the fake exits nonzero, and **adopt**:
  constructing a supervisor when `agent_pid_path` names a live PID → status RUNNING
  without spawning; a stale pidfile → deleted, STOPPED.
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
