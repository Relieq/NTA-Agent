# Dashboard Bot Control + Runtime Status (A+B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Control the agent (Start/Pause/Resume/Stop) from the dashboard and show a clear runtime status (engine state, PID, uptime, snapshot age), using a dashboard-supervisor model with a file control channel and pidfile-adopt so status survives a dashboard restart.

**Architecture:** A `control.json` file gates the agent loop (pause skips acting but keeps the session alive; stop breaks cleanly). A thread-safe `AgentSupervisor` in the dashboard spawns the agent as a child `subprocess`, or adopts a still-running one via `agent.pid`. New `/api/agent/*` endpoints drive it; a Vue `ControlBar` calls them.

**Tech Stack:** Python 3.12 stdlib (`subprocess`, `threading`, `ctypes` for Windows PID checks); Vue 3 (vendored, no-build) FE.

**Spec:** `docs/superpowers/specs/2026-09-17-dashboard-control-status-design.md`

## Global Constraints

- Backward compatible: `python -m nta_agent` with no `control.json` behaves exactly as today (`read_mode` → `"run"`).
- One agent at a time: Start never spawns a second agent while one is alive (owned or adopted).
- Pause must NOT log out of the game (keep the session alive for instant resume).
- No new external exposure: endpoints are POST/GET on the existing localhost server.
- Cross-platform PID ops via `runtime/proc.py` (target is Windows machine A; keep POSIX working for tests/CI).
- Tests: `.venv/Scripts/python.exe -m pytest -q`; lint `.venv/Scripts/python.exe -m ruff check nta_agent tests`.
- Commit footer on every commit:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_017SWX7TP9uSdjA1HbV883Tm`.

---

### Task 1: Control primitives + config paths

**Files:**
- Create: `nta_agent/runtime/control.py`
- Modify: `nta_agent/runtime/config.py` (add `control_path`, `agent_pid_path`)
- Test: `tests/test_control.py`

**Interfaces:**
- Produces: `read_mode(path) -> "run"|"pause"|"stop"`; `write_control(path, *, paused=None, stop=None) -> None` (merge); `reset(path) -> None` (write `{paused:false, stop:false}`). `cfg.control_path`, `cfg.agent_pid_path`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_control.py
from nta_agent.runtime.control import read_mode, write_control, reset
from nta_agent.runtime.config import RuntimeConfig


def test_read_mode_missing_is_run(tmp_path):
    assert read_mode(tmp_path / "nope.json") == "run"


def test_write_and_read_pause_stop(tmp_path):
    p = tmp_path / "control.json"
    write_control(p, paused=True)
    assert read_mode(p) == "pause"
    write_control(p, stop=True)        # merge: stop wins over pause
    assert read_mode(p) == "stop"


def test_write_control_merges(tmp_path):
    p = tmp_path / "control.json"
    write_control(p, paused=True)
    write_control(p, stop=False)       # leaves paused untouched
    assert read_mode(p) == "pause"


def test_reset_clears_both(tmp_path):
    p = tmp_path / "control.json"
    write_control(p, paused=True, stop=True)
    reset(p)
    assert read_mode(p) == "run"


def test_corrupt_file_is_run(tmp_path):
    p = tmp_path / "control.json"; p.write_text("{bad", encoding="utf-8")
    assert read_mode(p) == "run"


def test_config_paths():
    cfg = RuntimeConfig(distinct_id="x")
    assert cfg.control_path.name == "control.json"
    assert cfg.agent_pid_path.name == "agent.pid"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_control.py -q` → FAIL (import error).

- [ ] **Step 3: Implement `control.py`**

```python
# nta_agent/runtime/control.py
"""File-based control channel between the dashboard and the agent loop."""
from __future__ import annotations

import json
from pathlib import Path


def read_mode(path) -> str:
    """Return 'stop', 'pause', or 'run' from control.json (missing/bad -> 'run')."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "run"
    if d.get("stop"):
        return "stop"
    return "pause" if d.get("paused") else "run"


def write_control(path, *, paused=None, stop=None) -> None:
    """Merge the given flags into control.json (create parent dir)."""
    path = Path(path)
    try:
        cur = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(cur, dict):
            cur = {}
    except (OSError, ValueError):
        cur = {}
    if paused is not None:
        cur["paused"] = bool(paused)
    if stop is not None:
        cur["stop"] = bool(stop)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cur), encoding="utf-8")


def reset(path) -> None:
    """Clear both flags (fresh start)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"paused": False, "stop": False}), encoding="utf-8")
```

- [ ] **Step 4: Add config paths**

In `nta_agent/runtime/config.py`, next to `profile_path`/`forts_path`:
```python
    @property
    def control_path(self) -> Path:
        return self.log_dir / "control.json"

    @property
    def agent_pid_path(self) -> Path:
        return self.log_dir / "agent.pid"
```

- [ ] **Step 5: Run + lint + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_control.py -q` → PASS.
```bash
.venv/Scripts/python.exe -m ruff check nta_agent/runtime/control.py nta_agent/runtime/config.py tests/test_control.py
git add nta_agent/runtime/control.py nta_agent/runtime/config.py tests/test_control.py
git commit -m "feat(runtime): control.json channel + control/pid config paths"
```

---

### Task 2: Gate the agent loop (`agent.run(control=...)`)

**Files:**
- Modify: `nta_agent/execution/agent.py` (`run` signature + loop)
- Test: `tests/test_agent_control.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Agent.run(ticks=0, interval=5.0, on_tick=None, control=None)`. `control` is a zero-arg callable returning `"run"|"pause"|"stop"`. `pause` → `session.sync()` only, `fired=[]`, `on_tick` still fires; `stop` → break; default/None → unchanged behavior.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_control.py
from nta_agent.execution.agent import Agent


class FakeEngine:
    def __init__(self): self.ticks = 0
    def tick(self, state, actions): self.ticks += 1; return ["did_something"]


class FakeSession:
    def __init__(self): self.state = object(); self.syncs = 0
    def sync(self): self.syncs += 1; return self.state


def _agent():
    return Agent(FakeSession(), FakeEngine())


def test_pause_syncs_but_does_not_act():
    a = _agent(); seen = []
    a.run(ticks=1, interval=0, control=lambda: "pause",
          on_tick=lambda i, fired, st: seen.append(fired))
    assert a.engine.ticks == 0        # engine.tick NOT called while paused
    assert a.session.syncs == 1       # but state kept fresh
    assert seen == [[]]               # on_tick fired with empty fired list


def test_stop_breaks_immediately():
    a = _agent(); seen = []
    a.run(ticks=5, interval=0, control=lambda: "stop",
          on_tick=lambda i, fired, st: seen.append(i))
    assert a.engine.ticks == 0 and seen == []


def test_run_mode_is_normal():
    a = _agent()
    a.run(ticks=2, interval=0, control=lambda: "run")
    assert a.engine.ticks == 2
```

- [ ] **Step 2: Run → FAIL** (`control` not accepted / not honored).

- [ ] **Step 3: Implement** — replace the `run` loop body:

```python
    def run(self, ticks: int = 0, interval: float = 5.0, on_tick=None, control=None) -> None:
        """Run the loop. ``ticks=0`` means forever; ``interval`` seconds between ticks.

        ``control`` is an optional zero-arg callable returning "run", "pause", or
        "stop": pause keeps the session synced but skips acting; stop ends the loop.

        Raises :class:`TokenChainBroken` if the token chain breaks and no
        ``token_refresher`` is configured on the session.
        """
        i = 0
        while ticks == 0 or i < ticks:
            mode = control() if control else "run"
            if mode == "stop":
                break
            try:
                if mode == "pause":
                    self.session.sync()   # keep state fresh + session alive; do not act
                    fired = []
                else:
                    fired = self.tick()
            except _TRANSIENT as e:
                self._emit("connection_lost", e)
                self._recover()
                continue  # retry the tick immediately after recovery
            if on_tick:
                on_tick(i, fired, self.session.state)
            i += 1
            if ticks and i >= ticks:
                break
            time.sleep(interval)
```

- [ ] **Step 4: Run + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_agent_control.py tests/test_execution.py -q` → PASS.
```bash
git add nta_agent/execution/agent.py tests/test_agent_control.py
git commit -m "feat(agent): run(control=) — pause/stop the loop"
```

---

### Task 3: Runner wiring — pass control + gate services on pause

**Files:**
- Modify: `nta_agent/runtime/runner.py`
- Test: `tests/test_runner_control.py`

**Interfaces:**
- Consumes: `read_mode` (T1), `Agent.run(control=)` (T2).
- Produces: module-level `run_services(state, cfg, service, brain, forts, safe) -> bool` (returns False + skips the acting services when `read_mode(cfg.control_path)=="pause"`); `runner.run` passes `control=lambda: read_mode(cfg.control_path)` to `agent.run` and routes `on_tick` acting through `run_services`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_runner_control.py
from nta_agent.runtime.control import write_control
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime import runner


class Spy:
    def __init__(self): self.n = 0
    def tick(self, state): self.n += 1


def _safe(fn, *a): fn(*a)


def test_run_services_skips_when_paused(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    write_control(cfg.control_path, paused=True)
    svc, brain, forts = Spy(), Spy(), Spy()
    acted = runner.run_services(object(), cfg, svc, brain, forts, _safe)
    assert acted is False
    assert (svc.n, brain.n, forts.n) == (0, 0, 0)


def test_run_services_acts_when_running(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)  # no control.json -> run
    svc, brain, forts = Spy(), Spy(), Spy()
    acted = runner.run_services(object(), cfg, svc, brain, forts, _safe)
    assert acted is True
    assert (svc.n, brain.n, forts.n) == (1, 1, 1)
```

- [ ] **Step 2: Run → FAIL** (`run_services` missing).

- [ ] **Step 3: Implement** — add the helper and wire it:

At module top of `runner.py` add:
```python
from nta_agent.runtime.control import read_mode
```
Add the helper (module level):
```python
def run_services(state, cfg, service, brain, forts, safe) -> bool:
    """Run the acting services unless paused. Returns True if it acted."""
    if read_mode(cfg.control_path) == "pause":
        return False  # observe only while paused
    if service is not None:
        safe(service.tick, state)
    safe(brain.tick, state)
    safe(forts.tick, state)
    return True
```
Replace the service calls in `on_tick`:
```python
    def on_tick(i, fired, state):
        _safe(write_snapshot, state, cfg.snapshot_path)
        _safe(log.tick, i, fired, state)
        run_services(state, cfg, service, brain, forts, _safe)
```
Pass control to `agent.run`:
```python
        agent.run(ticks=ticks, interval=cfg.interval, on_tick=on_tick,
                  control=lambda: read_mode(cfg.control_path))
```

- [ ] **Step 4: Run full suite + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runner_control.py -q` and the existing runner tests → PASS.
```bash
git add nta_agent/runtime/runner.py tests/test_runner_control.py
git commit -m "feat(runner): pass control to agent.run; skip services while paused"
```

---

### Task 4: Cross-platform process helpers

**Files:**
- Create: `nta_agent/runtime/proc.py`
- Test: `tests/test_proc.py`

**Interfaces:**
- Produces: `pid_alive(pid: int) -> bool`; `hard_kill(pid: int) -> None` (best-effort force kill; POSIX `SIGKILL`, Windows `taskkill /F`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_proc.py
import os
from nta_agent.runtime.proc import pid_alive


def test_pid_alive_true_for_self():
    assert pid_alive(os.getpid()) is True


def test_pid_alive_false_for_unused():
    assert pid_alive(2_000_000_000) is False


def test_pid_alive_false_for_nonpositive():
    assert pid_alive(0) is False and pid_alive(-1) is False
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement**

```python
# nta_agent/runtime/proc.py
"""Cross-platform process liveness + force-kill (no third-party deps)."""
from __future__ import annotations

import os
import signal
import subprocess

_STILL_ACTIVE = 259


def pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED = 0x1000
        k = ctypes.windll.kernel32
        h = k.OpenProcess(PROCESS_QUERY_LIMITED, False, int(pid))
        if not h:
            return False
        try:
            code = ctypes.c_ulong()
            if not k.GetExitCodeProcess(h, ctypes.byref(code)):
                return False
            return code.value == _STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def hard_kill(pid: int) -> None:
    if not pid or pid <= 0:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/PID", str(int(pid))],
                       capture_output=True, check=False)
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
```

- [ ] **Step 4: Run + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_proc.py -q` → PASS.
```bash
git add nta_agent/runtime/proc.py tests/test_proc.py
git commit -m "feat(runtime): cross-platform pid_alive + hard_kill"
```

---

### Task 5: AgentSupervisor (spawn / adopt / control / status)

**Files:**
- Create: `nta_agent/dashboard/supervisor.py`
- Test: `tests/test_supervisor.py`

**Interfaces:**
- Consumes: `control.reset/write_control/read_mode`, `proc.pid_alive/hard_kill`, `cfg.control_path`, `cfg.agent_pid_path`.
- Produces: `AgentSupervisor(cfg)` with `start()`, `stop(timeout=10.0)`, `pause()`, `resume()`, `status() -> {"engine","pid","uptime"}`. Engine ∈ {RUNNING, PAUSED, STOPPED, CRASHED}.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_supervisor.py
import json
import nta_agent.dashboard.supervisor as sup_mod
from nta_agent.dashboard.supervisor import AgentSupervisor
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.control import read_mode


class FakeProc:
    def __init__(self, pid=4321): self.pid = pid; self._code = None
    def poll(self): return self._code
    def terminate(self): self._code = -15
    def kill(self): self._code = -9
    def wait(self, timeout=None): return self._code


def _cfg(tmp_path): return RuntimeConfig(distinct_id="x", log_dir=tmp_path)


def _patch_spawn(monkeypatch, proc):
    monkeypatch.setattr(sup_mod.subprocess, "Popen", lambda *a, **k: proc)


def test_start_then_running(tmp_path, monkeypatch):
    proc = FakeProc()
    _patch_spawn(monkeypatch, proc)
    monkeypatch.setattr(sup_mod, "pid_alive", lambda pid: proc.poll() is None)
    s = AgentSupervisor(_cfg(tmp_path))
    st = s.start()
    assert st["engine"] == "RUNNING" and st["pid"] == 4321
    assert read_mode(_cfg(tmp_path).control_path) == "run"   # reset on start
    # pidfile written
    assert json.loads((tmp_path / "agent.pid").read_text())["pid"] == 4321


def test_pause_resume(tmp_path, monkeypatch):
    proc = FakeProc(); _patch_spawn(monkeypatch, proc)
    monkeypatch.setattr(sup_mod, "pid_alive", lambda pid: proc.poll() is None)
    s = AgentSupervisor(_cfg(tmp_path)); s.start()
    assert s.pause()["engine"] == "PAUSED"
    assert read_mode(tmp_path / "control.json") == "pause"
    assert s.resume()["engine"] == "RUNNING"


def test_double_start_is_noop(tmp_path, monkeypatch):
    calls = []
    proc = FakeProc()
    monkeypatch.setattr(sup_mod.subprocess, "Popen",
                        lambda *a, **k: (calls.append(1), proc)[1])
    monkeypatch.setattr(sup_mod, "pid_alive", lambda pid: proc.poll() is None)
    s = AgentSupervisor(_cfg(tmp_path)); s.start(); s.start()
    assert len(calls) == 1


def test_stop_writes_flag_and_clears(tmp_path, monkeypatch):
    proc = FakeProc(); _patch_spawn(monkeypatch, proc)
    alive = {"v": True}
    monkeypatch.setattr(sup_mod, "pid_alive", lambda pid: alive["v"])
    s = AgentSupervisor(_cfg(tmp_path)); s.start()
    # simulate the agent honoring stop: it exits, so pid_alive flips false
    def fake_stop_effect(*a, **k):
        proc._code = 0; alive["v"] = False
    monkeypatch.setattr(proc, "poll", lambda: proc._code)
    st = s.stop(timeout=0.1)  # agent already 'exited' via poll code 0
    assert st["engine"] == "STOPPED"
    assert not (tmp_path / "agent.pid").exists()


def test_crashed_detection(tmp_path, monkeypatch):
    proc = FakeProc(); _patch_spawn(monkeypatch, proc)
    monkeypatch.setattr(sup_mod, "pid_alive", lambda pid: proc.poll() is None)
    s = AgentSupervisor(_cfg(tmp_path)); s.start()
    proc._code = 1  # exited nonzero without a user stop
    assert s.status()["engine"] == "CRASHED"


def test_adopt_live_pidfile(tmp_path, monkeypatch):
    (tmp_path / "agent.pid").write_text(json.dumps({"pid": 777, "started_at": 0}))
    monkeypatch.setattr(sup_mod, "pid_alive", lambda pid: pid == 777)
    s = AgentSupervisor(_cfg(tmp_path))
    assert s.status()["engine"] == "RUNNING" and s.status()["pid"] == 777


def test_adopt_stale_pidfile_deleted(tmp_path, monkeypatch):
    (tmp_path / "agent.pid").write_text(json.dumps({"pid": 777, "started_at": 0}))
    monkeypatch.setattr(sup_mod, "pid_alive", lambda pid: False)
    s = AgentSupervisor(_cfg(tmp_path))
    assert s.status()["engine"] == "STOPPED"
    assert not (tmp_path / "agent.pid").exists()
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement**

```python
# nta_agent/dashboard/supervisor.py
"""Supervise the agent as a child process (spawn or adopt), thread-safe."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from nta_agent.runtime.control import read_mode, reset, write_control
from nta_agent.runtime.proc import hard_kill, pid_alive


class AgentSupervisor:
    def __init__(self, cfg):
        self.cfg = cfg
        self._lock = threading.Lock()
        self._proc = None            # Popen when we spawned it; None when adopted
        self._pid = 0
        self._started_at = 0.0
        self._user_stopped = False
        self._last_exit = None
        self._adopt()

    # ---- helpers -------------------------------------------------------- #
    def _adopt(self):
        try:
            d = json.loads(Path(self.cfg.agent_pid_path).read_text(encoding="utf-8"))
            pid = int(d.get("pid", 0))
        except (OSError, ValueError):
            return
        if pid and pid_alive(pid):
            self._pid = pid
            self._started_at = float(d.get("started_at") or time.time())
        else:
            self._clear_pidfile()

    def _write_pidfile(self):
        Path(self.cfg.agent_pid_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.cfg.agent_pid_path).write_text(
            json.dumps({"pid": self._pid, "started_at": self._started_at}),
            encoding="utf-8")

    def _clear_pidfile(self):
        try:
            Path(self.cfg.agent_pid_path).unlink()
        except OSError:
            pass

    def _alive(self) -> bool:
        if self._proc is not None:
            return self._proc.poll() is None
        if self._pid:
            return pid_alive(self._pid)
        return False

    def _reap_if_exited(self):
        """If an owned child exited on its own, record it and clear handles."""
        if self._proc is not None and self._proc.poll() is not None:
            self._last_exit = self._proc.poll()
            self._proc = None
            self._pid = 0
            self._clear_pidfile()

    # ---- API ------------------------------------------------------------ #
    def start(self) -> dict:
        with self._lock:
            self._reap_if_exited()
            if self._alive():
                return self._status()
            reset(self.cfg.control_path)
            self._proc = subprocess.Popen([sys.executable, "-m", "nta_agent"])
            self._pid = self._proc.pid
            self._started_at = time.time()
            self._user_stopped = False
            self._last_exit = None
            self._write_pidfile()
            return self._status()

    def stop(self, timeout: float = 10.0) -> dict:
        with self._lock:
            if not self._alive():
                self._proc = None; self._pid = 0; self._clear_pidfile()
                self._user_stopped = True
                return self._status()
            write_control(self.cfg.control_path, stop=True)
            deadline = time.time() + timeout
            while time.time() < deadline and self._alive():
                time.sleep(0.1)
            if self._alive():
                if self._proc is not None:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=3)
                    except Exception:
                        self._proc.kill()
                else:
                    hard_kill(self._pid)
            self._user_stopped = True
            self._proc = None; self._pid = 0
            self._clear_pidfile()
            return self._status()

    def pause(self) -> dict:
        with self._lock:
            write_control(self.cfg.control_path, paused=True)
            return self._status()

    def resume(self) -> dict:
        with self._lock:
            write_control(self.cfg.control_path, paused=False)
            return self._status()

    def status(self) -> dict:
        with self._lock:
            self._reap_if_exited()
            return self._status()

    # ---- internal status (assumes lock held) ---------------------------- #
    def _status(self) -> dict:
        if self._alive():
            engine = "PAUSED" if read_mode(self.cfg.control_path) == "pause" else "RUNNING"
            return {"engine": engine, "pid": self._pid,
                    "uptime": max(0.0, time.time() - self._started_at)}
        if self._last_exit not in (None, 0) and not self._user_stopped:
            return {"engine": "CRASHED", "pid": None, "uptime": 0.0,
                    "exit_code": self._last_exit}
        return {"engine": "STOPPED", "pid": None, "uptime": 0.0}
```

- [ ] **Step 4: Run + lint + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_supervisor.py -q` → PASS.
```bash
.venv/Scripts/python.exe -m ruff check nta_agent/dashboard/supervisor.py tests/test_supervisor.py
git add nta_agent/dashboard/supervisor.py tests/test_supervisor.py
git commit -m "feat(dashboard): AgentSupervisor — spawn/adopt/pause/stop/status"
```

---

### Task 6: Control endpoints on the server

**Files:**
- Modify: `nta_agent/dashboard/server.py` (create supervisor on `DashboardServer`; routes)
- Test: `tests/test_dashboard_agent_api.py`

**Interfaces:**
- Consumes: `AgentSupervisor` (T5).
- Produces: `GET /api/agent/status` → supervisor.status(); `POST /api/agent/start|stop|pause|resume` → the matching method → its status dict.

- [ ] **Step 1: Write the failing test** (attach a fake supervisor, hit the handler through the existing server-test harness)

```python
# tests/test_dashboard_agent_api.py
import json
import urllib.request
from nta_agent.dashboard.server import DashboardServer, Handler
from nta_agent.runtime.config import RuntimeConfig


class FakeSup:
    def __init__(self): self.calls = []
    def status(self): return {"engine": "STOPPED", "pid": None, "uptime": 0.0}
    def start(self): self.calls.append("start"); return {"engine": "RUNNING", "pid": 1, "uptime": 0.0}
    def stop(self): self.calls.append("stop"); return {"engine": "STOPPED", "pid": None, "uptime": 0.0}
    def pause(self): self.calls.append("pause"); return {"engine": "PAUSED", "pid": 1, "uptime": 1.0}
    def resume(self): self.calls.append("resume"); return {"engine": "RUNNING", "pid": 1, "uptime": 2.0}


def _server(tmp_path):
    cfg = RuntimeConfig(distinct_id="x", log_dir=tmp_path)
    srv = DashboardServer(("127.0.0.1", 0), Handler, cfg)
    srv.supervisor = FakeSup()
    return srv


def _get(srv, path):
    port = srv.server_address[1]
    import threading
    t = threading.Thread(target=srv.handle_request, daemon=True); t.start()
    r = urllib.request.urlopen(f"http://127.0.0.1:{port}{path}")
    return json.loads(r.read())


def _post(srv, path):
    port = srv.server_address[1]
    import threading
    t = threading.Thread(target=srv.handle_request, daemon=True); t.start()
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=b"{}",
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req).read())


def test_status_endpoint(tmp_path):
    srv = _server(tmp_path)
    assert _get(srv, "/api/agent/status")["engine"] == "STOPPED"
    srv.server_close()


def test_action_endpoints(tmp_path):
    for action, engine in (("start","RUNNING"),("pause","PAUSED"),("resume","RUNNING"),("stop","STOPPED")):
        srv = _server(tmp_path)
        out = _post(srv, f"/api/agent/{action}")
        assert out["engine"] == engine
        assert srv.supervisor.calls == [action]
        srv.server_close()
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement**

In `DashboardServer.__init__` add:
```python
        from nta_agent.dashboard.supervisor import AgentSupervisor
        self.supervisor = AgentSupervisor(cfg)
```
In `Handler.do_GET`, before the `/static/` branch:
```python
        elif parsed.path == "/api/agent/status":
            self._json(200, self.server.supervisor.status())
```
In `Handler.do_POST`, near the top (before `/api/chat`):
```python
        if parsed.path.startswith("/api/agent/"):
            action = parsed.path[len("/api/agent/"):]
            sup = self.server.supervisor
            fn = {"start": sup.start, "stop": sup.stop,
                  "pause": sup.pause, "resume": sup.resume}.get(action)
            if fn is None:
                self._json(404, {"ok": False, "error": "unknown agent action"})
                return
            # drain any request body (ignored)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length:
                    self.rfile.read(length)
            except (ValueError, TypeError):
                pass
            self._json(200, fn())
            return
```

- [ ] **Step 4: Run + commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_agent_api.py -q` → PASS.
```bash
git add nta_agent/dashboard/server.py tests/test_dashboard_agent_api.py
git commit -m "feat(dashboard): /api/agent control + status endpoints"
```

---

### Task 7: FE — ControlBar + runtime status; live verify

**Files:**
- Create: `nta_agent/dashboard/static/components/ControlBar.js`
- Modify: `nta_agent/dashboard/static/components/StatusHeader.js` (host ControlBar + engine/pid/uptime + snapshot age)
- Modify: `nta_agent/dashboard/static/components/App.js` (StatusHeader already mounted — no grid change)
- Test: extend `tests/test_dashboard_components.py`

**Interfaces:**
- Consumes: `getJSON`, `postJSON`, `usePolling`, `ago`. `ControlBar` polls `/api/agent/status` (1000ms) and POSTs `/api/agent/{start,pause,resume,stop}`.

- [ ] **Step 1: Add failing assertions**

```python
def test_control_bar_component():
    cb = _c("ControlBar.js")
    for m in ("/api/agent/status", "/api/agent/start", "/api/agent/stop",
              "/api/agent/pause", "/api/agent/resume", "RUNNING", "PAUSED", "STOPPED"):
        assert m in cb
    assert "ControlBar" in _c("StatusHeader.js")
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement `ControlBar.js`**

```js
// nta_agent/dashboard/static/components/ControlBar.js
import { getJSON, postJSON, usePolling } from "../api.js";
const { ref } = window.Vue;
const COLOR={RUNNING:"var(--ok)",PAUSED:"var(--warn)",STOPPED:"var(--muted)",CRASHED:"var(--danger)"};
export default {
 setup(){
  const st=ref({engine:"STOPPED",pid:null,uptime:0}); const busy=ref(false);
  usePolling(async ()=>{ const s=await getJSON("/api/agent/status"); if(s) st.value=s; },1000);
  async function act(name){ busy.value=true;
   const s=await postJSON("/api/agent/"+name,{}); if(s) st.value=s; busy.value=false; }
  const alive=()=> st.value.engine==="RUNNING"||st.value.engine==="PAUSED";
  const color=()=> COLOR[st.value.engine]||"var(--muted)";
  return { st, busy, act, alive, color };
 },
 template:`<div style="display:flex;align-items:center;gap:8px">
  <span class="dot" :style="{background:color()}"></span>
  <b :style="{color:color()}">{{ st.engine }}</b>
  <button :disabled="busy||alive()" @click="act('start')">▶ Start</button>
  <button v-if="st.engine!=='PAUSED'" :disabled="busy||!alive()" @click="act('pause')">⏸ Pause</button>
  <button v-else :disabled="busy" @click="act('resume')">▶ Resume</button>
  <button :disabled="busy||!alive()" @click="act('stop')">⏹ Stop</button>
 </div>`
};
```

- [ ] **Step 4: Update `StatusHeader.js`** to host ControlBar + engine/uptime/snapshot age

```js
// nta_agent/dashboard/static/components/StatusHeader.js
import { getJSON, usePolling, ago } from "../api.js";
import ControlBar from "./ControlBar.js";
const { ref } = window.Vue;
export default {
 components:{ ControlBar },
 setup(){
  const snap=ref("…");
  usePolling(async ()=>{
   const s=await getJSON("/api/state");
   snap.value=(s&&s.ok)? ("snapshot "+ago(s.updated_at)) : "chưa có snapshot";
  }, 2000);
  return { snap };
 },
 template:`<header><div><h1>NTA Agent</h1><div class="muted" style="font-size:12px">{{ snap }}</div></div>
  <ControlBar/></header>`
};
```

- [ ] **Step 5: Run tests + full suite + lint**

Run: `.venv/Scripts/python.exe -m pytest -q` → all pass. `ruff check nta_agent tests` → clean.

- [ ] **Step 6: Live verify on machine A**

Start the dashboard (`python -m nta_agent.dashboard`); do NOT start the agent from a terminal. In the machine-A browser (select browser "Quyền"), open `http://127.0.0.1:8787`:
- Engine shows STOPPED. Click **Start** → engine → RUNNING, PID shown; the event feed starts ticking.
- Click **Pause** → PAUSED; snapshot age keeps updating (agent alive) but no new acting events; the game session stays logged in.
- Click **Resume** → RUNNING resumes acting.
- **Restart the dashboard process** while the agent runs → after reload, engine still shows RUNNING (adopted), and Stop still works.
- Click **Stop** → STOPPED, agent exits cleanly.
- No console errors. Screenshot for the user.

- [ ] **Step 7: Commit**

```bash
git add nta_agent/dashboard/static/components tests/test_dashboard_components.py
git commit -m "feat(dashboard): ControlBar + runtime status (Vue); A+B complete"
```

---

## Self-Review notes (author)

- **Spec coverage**: control channel (T1), agent gating (T2), runner service-gating (T3), pid helpers (T4), supervisor spawn/adopt/status incl. CRASHED + adopt (T5), endpoints (T6), UI + live verify incl. dashboard-restart-adopt (T7). All spec sections covered.
- **Type consistency**: `read_mode/write_control/reset` (T1) used by runner (T3) + supervisor (T5); `pid_alive/hard_kill` (T4) used by supervisor (T5); `status()` dict shape `{engine,pid,uptime}` produced in T5, consumed by T6 endpoints and T7 UI; engine strings RUNNING/PAUSED/STOPPED/CRASHED consistent across T5-T7.
- **No placeholders**: all task code is inline and concrete.
- **Backward compat**: `read_mode` on a missing file returns "run" (T1 test), so standalone `python -m nta_agent` is unchanged (T3 keeps behavior when no control.json).
