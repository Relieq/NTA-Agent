# Operational Spine (Chặng 2A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A production entrypoint (`python -m nta_agent`) that runs a full resilient agent session unattended, with env config, structured JSONL event logging, and an atomic JSON state snapshot as the dashboard seam.

**Architecture:** New `nta_agent/runtime/` package with four focused units (config, snapshot, eventlog, runner) plus `__main__`. It wires existing pieces — `DeviceManager`, `make_token_refresher`, `GameSession`, `Agent.run` — and hangs snapshot/log writing off `Agent`'s existing `on_tick`/`on_event` hooks. The dashboard (2B) is a separate process that reads the snapshot + event files.

**Tech Stack:** Python 3.12 (stdlib only: `argparse`, `json`, `os`, `pathlib`, `dataclasses`), pytest, ruff. Venv at `.venv`.

**Spec:** `docs/superpowers/specs/2026-09-12-operational-spine-design.md`

## Global Constraints

- Python 3.12; run tests/lint via the venv: `.venv/Scripts/python.exe -m pytest -q`, `.venv/Scripts/python.exe -m ruff check nta_agent tests`. All new code passes ruff clean.
- Config via environment variables with the `NTA_` prefix (matches `nta_agent/config.py`). Required: `NTA_DISTINCT_ID`. Secrets (distinct id, token) never committed.
- Operational code lives in the new `nta_agent/runtime/` package; do not add web dependencies (stdlib only for 2A).
- Observability (snapshot/event writes) must NEVER crash the agent loop — wrap writes in try/except, log to stderr, continue.
- Defaults: `NTA_SERVER_HOST=nine-hk.twomiles.cn`, `NTA_TOKEN_PATH=build/nta_token.txt`, `NTA_TICK_INTERVAL=5.0`, `NTA_MAX_BACKOFF=60.0`, `NTA_LOG_DIR=build/run`; `snapshot_path=<log_dir>/state.json`, `event_log_path=<log_dir>/events.jsonl`.
- Reuse, don't duplicate: device/adb config comes from `nta_agent/config.py` (`DeviceManager.connect()`); token refresh from `nta_agent/io/bootstrap.py` (`make_token_refresher`).

---

### Task 1: RuntimeConfig

**Files:**
- Create: `nta_agent/runtime/__init__.py`
- Create: `nta_agent/runtime/config.py`
- Test: `tests/test_runtime_config.py`

**Interfaces:**
- Produces:
  - `class ConfigError(Exception)`.
  - `@dataclass RuntimeConfig` with fields `host: str`, `distinct_id: str`, `token_path: Path`, `interval: float`, `max_backoff: float`, `log_dir: Path`, and computed properties `snapshot_path: Path` (`log_dir/"state.json"`) and `event_log_path: Path` (`log_dir/"events.jsonl"`).
  - classmethod `RuntimeConfig.from_env(env: Mapping[str,str] | None = None) -> RuntimeConfig` — reads `NTA_*` from `env` (default `os.environ`); raises `ConfigError` naming the variable if `NTA_DISTINCT_ID` is missing/empty.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_runtime_config.py
import pytest
from pathlib import Path
from nta_agent.runtime.config import RuntimeConfig, ConfigError


def test_from_env_defaults():
    cfg = RuntimeConfig.from_env({"NTA_DISTINCT_ID": "abc"})
    assert cfg.distinct_id == "abc"
    assert cfg.host == "nine-hk.twomiles.cn"
    assert cfg.interval == 5.0
    assert cfg.max_backoff == 60.0
    assert cfg.token_path == Path("build/nta_token.txt")
    assert cfg.log_dir == Path("build/run")
    assert cfg.snapshot_path == Path("build/run/state.json")
    assert cfg.event_log_path == Path("build/run/events.jsonl")


def test_from_env_overrides():
    cfg = RuntimeConfig.from_env({
        "NTA_DISTINCT_ID": "x", "NTA_SERVER_HOST": "h", "NTA_TICK_INTERVAL": "2.5",
        "NTA_MAX_BACKOFF": "10", "NTA_TOKEN_PATH": "/t/tok.txt", "NTA_LOG_DIR": "/l",
    })
    assert (cfg.host, cfg.interval, cfg.max_backoff) == ("h", 2.5, 10.0)
    assert cfg.token_path == Path("/t/tok.txt")
    assert cfg.snapshot_path == Path("/l/state.json")


def test_missing_distinct_id_raises():
    with pytest.raises(ConfigError):
        RuntimeConfig.from_env({})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runtime_config.py -q`
Expected: FAIL — `ModuleNotFoundError: nta_agent.runtime.config`.

- [ ] **Step 3: Write minimal implementation**

Create `nta_agent/runtime/__init__.py` empty. Then `nta_agent/runtime/config.py`:

```python
"""Runtime configuration for the operational spine (env NTA_* -> RuntimeConfig)."""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """A required runtime configuration value is missing or invalid."""


@dataclass
class RuntimeConfig:
    distinct_id: str
    host: str = "nine-hk.twomiles.cn"
    token_path: Path = Path("build/nta_token.txt")
    interval: float = 5.0
    max_backoff: float = 60.0
    log_dir: Path = Path("build/run")

    @property
    def snapshot_path(self) -> Path:
        return self.log_dir / "state.json"

    @property
    def event_log_path(self) -> Path:
        return self.log_dir / "events.jsonl"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> RuntimeConfig:
        env = os.environ if env is None else env
        distinct = env.get("NTA_DISTINCT_ID", "").strip()
        if not distinct:
            raise ConfigError("NTA_DISTINCT_ID is required")
        return cls(
            distinct_id=distinct,
            host=env.get("NTA_SERVER_HOST", "nine-hk.twomiles.cn"),
            token_path=Path(env.get("NTA_TOKEN_PATH", "build/nta_token.txt")),
            interval=float(env.get("NTA_TICK_INTERVAL", "5.0")),
            max_backoff=float(env.get("NTA_MAX_BACKOFF", "60.0")),
            log_dir=Path(env.get("NTA_LOG_DIR", "build/run")),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runtime_config.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/runtime/__init__.py nta_agent/runtime/config.py tests/test_runtime_config.py
git commit -m "runtime: RuntimeConfig from NTA_* env"
```

---

### Task 2: State snapshot

**Files:**
- Create: `nta_agent/runtime/snapshot.py`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Consumes: `nta_agent.state.schema.GameState` (fields: `resources` with `cereal/timber/stone/iron/gold/stamina/exp_book/up_scroll/fixator`; `main_city_index: int`; `builds: list[Building]` where Building has `index/id/lv/uid`; `marches: list[March]`; `areas: dict[int, Area]`; `build_queue: list[dict]`; `build_queue_slots: int`; `production: dict`; `granary_cap: int`; `warehouse_cap: int`; `source: str`; `updated_at: float`; `raw: dict`).
- Produces:
  - `state_to_dict(state: GameState) -> dict` — stable JSON-safe view; excludes `raw` except a small `player` subset: `{"guide_tasks": len(player.guideTasks), "other_tasks": len(player.otherTasks), "today_tasks": len(player.todayTasks), "pawn_slots": [ids]}`.
  - `write_snapshot(state: GameState, path: Path) -> dict` — writes `state_to_dict` JSON atomically (`path` + ".tmp" then `os.replace`), creating parent dirs; returns the dict.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_snapshot.py
import json
from pathlib import Path
from nta_agent.runtime.snapshot import state_to_dict, write_snapshot
from nta_agent.state.schema import GameState, Building, User


def _state():
    st = GameState(source="api")
    st.user = User(uid="7")
    st.main_city_index = 109726
    st.resources.cereal = 500
    st.resources.timber = 20
    st.builds = [Building(index=109726, id=2001, lv=2, uid="b1")]
    st.granary_cap = 1000
    st.raw = {"player": {"guideTasks": [{"id": 1}], "otherTasks": [],
                          "todayTasks": [{"id": 2}, {"id": 3}],
                          "pawnSlots": {"0": {"id": 3101}}}}
    return st


def test_state_to_dict_shape_and_json_safe():
    d = state_to_dict(_state())
    assert d["main_city_index"] == 109726
    assert d["resources"]["cereal"] == 500
    assert d["builds"] == [{"index": 109726, "id": 2001, "lv": 2, "uid": "b1"}]
    assert d["granary_cap"] == 1000
    assert d["player"]["guide_tasks"] == 1 and d["player"]["today_tasks"] == 2
    assert d["player"]["pawn_slots"] == [3101]
    assert "raw" not in d
    json.dumps(d)  # must be serializable


def test_write_snapshot_atomic(tmp_path):
    p = tmp_path / "sub" / "state.json"
    write_snapshot(_state(), p)
    assert json.loads(p.read_text())["main_city_index"] == 109726
    assert not (tmp_path / "sub" / "state.json.tmp").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_snapshot.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# nta_agent/runtime/snapshot.py
"""Serialize GameState to a stable, JSON-safe snapshot for the dashboard."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from nta_agent.state.schema import GameState


def _player_subset(raw: dict) -> dict:
    player = (raw or {}).get("player", {}) or {}
    slots = player.get("pawnSlots") or {}
    pawn_ids = [v["id"] for v in slots.values() if isinstance(v, dict) and v.get("id")]
    return {
        "guide_tasks": len(player.get("guideTasks") or []),
        "other_tasks": len(player.get("otherTasks") or []),
        "today_tasks": len(player.get("todayTasks") or []),
        "pawn_slots": pawn_ids,
    }


def state_to_dict(state: GameState) -> dict:
    return {
        "source": state.source,
        "updated_at": state.updated_at,
        "uid": state.user.uid,
        "main_city_index": state.main_city_index,
        "resources": asdict(state.resources),
        "builds": [{"index": b.index, "id": b.id, "lv": b.lv, "uid": b.uid}
                   for b in state.builds],
        "marches": len(state.marches),
        "areas": len(state.areas),
        "build_queue": state.build_queue,
        "build_queue_slots": state.build_queue_slots,
        "production": state.production,
        "granary_cap": state.granary_cap,
        "warehouse_cap": state.warehouse_cap,
        "player": _player_subset(state.raw),
    }


def write_snapshot(state: GameState, path: Path) -> dict:
    d = state_to_dict(state)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return d
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_snapshot.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/runtime/snapshot.py tests/test_snapshot.py
git commit -m "runtime: atomic GameState JSON snapshot"
```

---

### Task 3: Event log

**Files:**
- Create: `nta_agent/runtime/eventlog.py`
- Test: `tests/test_eventlog.py`

**Interfaces:**
- Produces:
  - `class EventLog` with `__init__(self, path: Path)`, `append(self, kind: str, detail=None) -> None` (writes one JSON line `{"ts": float, "kind": str, "detail": <json-safe>}`; non-serializable `detail` is `str()`-coerced; `None` detail omitted), and `tick(self, i: int, fired: list[str], state) -> None` (appends `{"ts","kind":"tick","i","fired","cereal","timber","stone"}`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eventlog.py
import json
from nta_agent.runtime.eventlog import EventLog
from nta_agent.state.schema import GameState


def _lines(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_append_writes_jsonl(tmp_path):
    p = tmp_path / "d" / "events.jsonl"
    log = EventLog(p)
    log.append("recovered")
    log.append("recover_retry", "boom")
    rows = _lines(p)
    assert rows[0]["kind"] == "recovered" and "detail" not in rows[0]
    assert rows[1] == {"ts": rows[1]["ts"], "kind": "recover_retry", "detail": "boom"}


def test_append_coerces_non_serializable(tmp_path):
    p = tmp_path / "events.jsonl"
    EventLog(p).append("connection_lost", ValueError("x"))
    assert _lines(p)[0]["detail"] == "x"


def test_tick_summary(tmp_path):
    p = tmp_path / "events.jsonl"
    st = GameState(); st.resources.cereal = 12
    EventLog(p).tick(3, ["collect_city_output"], st)
    row = _lines(p)[0]
    assert row["kind"] == "tick" and row["i"] == 3
    assert row["fired"] == ["collect_city_output"] and row["cereal"] == 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_eventlog.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# nta_agent/runtime/eventlog.py
"""Append-only JSONL event log for the operational spine."""
from __future__ import annotations

import json
import time
from pathlib import Path


class EventLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, obj: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def append(self, kind: str, detail=None) -> None:
        row = {"ts": time.time(), "kind": kind}
        if detail is not None:
            try:
                json.dumps(detail)
                row["detail"] = detail
            except (TypeError, ValueError):
                row["detail"] = str(detail)
        self._write(row)

    def tick(self, i: int, fired: list[str], state) -> None:
        r = state.resources
        self._write({"ts": time.time(), "kind": "tick", "i": i, "fired": fired,
                     "cereal": r.cereal, "timber": r.timber, "stone": r.stone})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_eventlog.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/runtime/eventlog.py tests/test_eventlog.py
git commit -m "runtime: JSONL event log"
```

---

### Task 4: Runner (build_session + run)

**Files:**
- Create: `nta_agent/runtime/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: `RuntimeConfig` (Task 1), `write_snapshot` (Task 2), `EventLog` (Task 3), `Agent` (`nta_agent.execution.agent`), `GameSession`/`ServerConfig` (`nta_agent.io.api`), `DeviceManager` (`nta_agent.io.adb`), `make_token_refresher` (`nta_agent.io.bootstrap`), `RuleEngine` (`nta_agent.execution.heuristics`), `TokenChainBroken` (`nta_agent.io.api.session`).
- Produces:
  - `build_session(cfg: RuntimeConfig) -> GameSession` — DeviceManager.connect() → make_token_refresher → GameSession(server, token_path, token_refresher) → connect/login/enter_game(distinct_id).
  - `run(cfg: RuntimeConfig, *, ticks: int = 0, session=None, engine=None) -> None` — build (or accept) session; `Agent(session, engine or RuleEngine.default(), max_backoff=cfg.max_backoff, on_event=log.append)`; `agent.run(ticks, cfg.interval, on_tick=<snapshot + log.tick, guarded>)`; on `KeyboardInterrupt` log `"interrupted"`; always write a final snapshot (guarded) and `session.close()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_runner.py
import json
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime import runner
from nta_agent.execution.heuristics import RuleEngine
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self):
        self.state = GameState(source="api")
        self.state.resources.cereal = 100
        self.closed = False
        self.synced = 0
    def sync(self):
        self.synced += 1
        self.state.resources.cereal += 1
    def close(self):
        self.closed = True


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x",
                                   "NTA_LOG_DIR": str(tmp_path / "run"),
                                   "NTA_TICK_INTERVAL": "0"})


def test_run_writes_snapshot_and_events_and_closes(tmp_path):
    cfg = _cfg(tmp_path)
    sess = FakeSession()
    runner.run(cfg, ticks=3, session=sess, engine=RuleEngine(rules=[]))
    # snapshot exists and reflects the last tick
    snap = json.loads(cfg.snapshot_path.read_text())
    assert snap["resources"]["cereal"] >= 103
    # event log has 3 tick rows
    rows = [json.loads(x) for x in cfg.event_log_path.read_text().splitlines() if x.strip()]
    assert sum(1 for r in rows if r["kind"] == "tick") == 3
    assert sess.closed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runner.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# nta_agent/runtime/runner.py
"""Wire config + bootstrap + session + Agent into a runnable, observable spine."""
from __future__ import annotations

import sys

from nta_agent.execution.agent import Agent
from nta_agent.execution.heuristics import RuleEngine
from nta_agent.io.adb import DeviceManager
from nta_agent.io.api.client import ServerConfig
from nta_agent.io.api.session import GameSession
from nta_agent.io.bootstrap import make_token_refresher
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.eventlog import EventLog
from nta_agent.runtime.snapshot import write_snapshot


def build_session(cfg: RuntimeConfig) -> GameSession:
    dm = DeviceManager.connect()
    refresher = make_token_refresher(dm, cfg.token_path)
    session = GameSession(server=ServerConfig(host=cfg.host),
                          token_path=cfg.token_path, token_refresher=refresher)
    session.connect(timeout=15)
    session.login(distinct_id=cfg.distinct_id)
    session.enter_game(distinct_id=cfg.distinct_id)
    return session


def run(cfg: RuntimeConfig, *, ticks: int = 0, session=None, engine=None) -> None:
    log = EventLog(cfg.event_log_path)
    if session is None:
        session = build_session(cfg)
        log.append("started", {"host": cfg.host})
    agent = Agent(session, engine or RuleEngine.default(),
                  max_backoff=cfg.max_backoff, on_event=log.append)

    def _safe(fn, *a):
        try:
            fn(*a)
        except Exception as e:  # observability must not kill the loop
            sys.stderr.write(f"[spine] {fn.__name__} failed: {e}\n")

    def on_tick(i, fired, state):
        _safe(write_snapshot, state, cfg.snapshot_path)
        _safe(log.tick, i, fired, state)

    try:
        agent.run(ticks=ticks, interval=cfg.interval, on_tick=on_tick)
    except KeyboardInterrupt:
        log.append("interrupted")
    finally:
        _safe(write_snapshot, session.state, cfg.snapshot_path)
        session.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/runtime/runner.py tests/test_runner.py
git commit -m "runtime: runner wires session+Agent with snapshot/eventlog + graceful stop"
```

---

### Task 5: CLI entrypoint (`python -m nta_agent`)

**Files:**
- Create: `nta_agent/__main__.py`
- Test: `tests/test_main_cli.py`

**Interfaces:**
- Consumes: `RuntimeConfig.from_env`/`ConfigError` (Task 1), `runner.run` (Task 4), `TokenChainBroken` (`nta_agent.io.api.session`).
- Produces: `main(argv: list[str] | None = None) -> int` — parses `--ticks N` (default 0) and `--once` (sets ticks=1); loads config; calls `runner.run(cfg, ticks=...)`; returns 0 on clean finish, 2 on `ConfigError`, 1 on `TokenChainBroken` (each printing a clear message to stderr). Module runs `raise SystemExit(main())` under `if __name__ == "__main__"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main_cli.py
import pytest
from nta_agent import __main__ as cli
from nta_agent.runtime.config import ConfigError


def test_main_missing_config_returns_2(monkeypatch, capsys):
    monkeypatch.setattr(cli.RuntimeConfig, "from_env", staticmethod(
        lambda *a, **k: (_ for _ in ()).throw(ConfigError("NTA_DISTINCT_ID is required"))))
    assert cli.main([]) == 2
    assert "NTA_DISTINCT_ID" in capsys.readouterr().err


def test_main_once_calls_runner_with_ticks_1(monkeypatch):
    calls = {}
    monkeypatch.setattr(cli.RuntimeConfig, "from_env", staticmethod(lambda *a, **k: "CFG"))
    monkeypatch.setattr(cli.runner, "run", lambda cfg, *, ticks: calls.update(cfg=cfg, ticks=ticks))
    assert cli.main(["--once"]) == 0
    assert calls == {"cfg": "CFG", "ticks": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_main_cli.py -q`
Expected: FAIL — `nta_agent/__main__.py` missing.

- [ ] **Step 3: Write minimal implementation**

```python
# nta_agent/__main__.py
"""CLI entrypoint: `python -m nta_agent` runs the operational spine."""
from __future__ import annotations

import argparse
import sys

from nta_agent.io.api.session import TokenChainBroken
from nta_agent.runtime import runner
from nta_agent.runtime.config import ConfigError, RuntimeConfig


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nta_agent", description="Run the NTA agent spine.")
    ap.add_argument("--ticks", type=int, default=0, help="number of ticks (0 = forever)")
    ap.add_argument("--once", action="store_true", help="run a single tick then exit")
    args = ap.parse_args(argv)
    ticks = 1 if args.once else args.ticks
    try:
        cfg = RuntimeConfig.from_env()
    except ConfigError as e:
        sys.stderr.write(f"config error: {e}\n")
        return 2
    try:
        runner.run(cfg, ticks=ticks)
    except TokenChainBroken:
        sys.stderr.write("fatal: account token chain broken and refresh failed\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_main_cli.py -q`
Expected: PASS.

- [ ] **Step 5: Full verification + commit**

Run: `.venv/Scripts/python.exe -m pytest -q` (all pass) and `.venv/Scripts/python.exe -m ruff check nta_agent tests` (clean).

```bash
git add nta_agent/__main__.py tests/test_main_cli.py
git commit -m "runtime: python -m nta_agent CLI entrypoint"
```

---

## Self-Review

**Spec coverage:**
- §3.1 RuntimeConfig → Task 1. §3.2 snapshot → Task 2. §3.3 eventlog → Task 3. §3.4 runner (build_session + run + graceful shutdown) → Task 4. §3.5 `__main__` → Task 5. ✓
- §2 state seam (atomic JSON snapshot + JSONL) → Tasks 2, 3, wired in 4. ✓
- §2 config via `NTA_` env, required distinct id → Task 1. ✓
- §5 error handling: ConfigError→exit 2 (Task 5), TokenChainBroken→exit 1 (Task 5), snapshot/log guarded `_safe` never kills loop (Task 4), recovery unchanged (reuses Agent). ✓
- §6 testing: config/snapshot/eventlog/runner/CLI all have tests; no live network (fakes + monkeypatch). ✓
- §7 out of scope (dashboard/decision-queue/captcha) — not in any task. ✓

**Placeholder scan:** No TBD/TODO; every code step is complete and runnable. No "similar to Task N".

**Type consistency:** `RuntimeConfig` fields/properties (`snapshot_path`, `event_log_path`, `interval`, `max_backoff`, `token_path`, `distinct_id`, `host`, `log_dir`) are used identically in Tasks 4/5. `write_snapshot(state, path)`, `EventLog(path).append/tick`, `runner.run(cfg, *, ticks, session, engine)`, `runner.build_session(cfg)`, `main(argv)` signatures match across tasks. `Agent(session, engine, max_backoff=, on_event=)` matches `execution/agent.py`. `GameSession(server=ServerConfig(host=), token_path=, token_refresher=)` + `connect/login/enter_game` match `smoke_agent.py`. `DeviceManager.connect()` and `make_token_refresher(dm, token_path)` match their modules.
