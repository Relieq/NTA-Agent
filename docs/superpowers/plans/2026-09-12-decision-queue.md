# Human-Decision Queue (Chặng 2C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface reserved ceri decisions (unlock pawn / research policy / unlock equip) to the human on the dashboard and execute their pick/reroll on the live session, via a file command channel — the agent never auto-decides.

**Architecture:** Pure detection (`execution/decisions.py`) + two hands methods (`actions.study_select`/`ceri_reset`) + a file command channel (`runtime/commands.py`) + a per-tick `runtime/decision_service.py` wired into the runner; the 2B dashboard gains `GET /api/decisions`, `POST /api/command`, and a pending-decisions panel.

**Tech Stack:** Python 3.12 stdlib only, pytest, ruff. Venv at `.venv`.

**Spec:** `docs/superpowers/specs/2026-09-12-decision-queue-design.md`

## Global Constraints

- Python 3.12; venv runs: `.venv/Scripts/python.exe -m pytest -q`, `.venv/Scripts/python.exe -m ruff check nta_agent tests`. Ruff clean.
- stdlib only. Dashboard now accepts `POST /api/command` but still binds `127.0.0.1`.
- **StudyType `tp` (verified in client):** POLICY=1, PAWN=2, EQUIP=3. `TRACKS` maps player slot-map field → `(tp, text_table)`: `{"pawnSlots": (2, "pawnText"), "policySlots": (1, "policyText"), "equipSlots": (3, "equipText")}`.
- **Pending slot** ⟺ `id <= 0 and selectIds` non-empty (per `CeriSlotInfo`). Option name: `selectId → ceri.json.value → <text_table>["name_<value>"].vi` (fallback `.en`, then `#<value>`).
- Requests: `game/HD_StudySelect{lv, id, tp}` → `{slots: map}`; `game/HD_CeriResetSelect{lv, tp}` → `{gold, selectIds, resetCount, useGold}`.
- Exactly-once command execution across restarts via `commands.done`. Select is one-shot; reroll spends gold — never double-run.
- Seam files under `cfg.log_dir`: `decisions.json`, `commands.jsonl`, `commands.done` (in addition to 2A's `state.json`/`events.jsonl`).
- Reuse `GameConfig` (`nta_agent.data.config`) for ceri + text tables; reuse `RuntimeConfig` for paths.

---

### Task 1: RuntimeConfig — decision/command paths

**Files:**
- Modify: `nta_agent/runtime/config.py`
- Test: `tests/test_runtime_config.py` (extend)

**Interfaces:**
- Produces on `RuntimeConfig`: properties `decisions_path` (`log_dir/"decisions.json"`), `commands_path` (`log_dir/"commands.jsonl"`), `commands_done_path` (`log_dir/"commands.done"`).

- [ ] **Step 1: Write the failing test** — append to `tests/test_runtime_config.py`:

```python
def test_decision_queue_paths():
    from pathlib import Path
    cfg = RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": "/l"})
    assert cfg.decisions_path == Path("/l/decisions.json")
    assert cfg.commands_path == Path("/l/commands.jsonl")
    assert cfg.commands_done_path == Path("/l/commands.done")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runtime_config.py::test_decision_queue_paths -q`
Expected: FAIL — attributes missing.

- [ ] **Step 3: Write minimal implementation** — add to `RuntimeConfig` (after `event_log_path`):

```python
    @property
    def decisions_path(self) -> Path:
        return self.log_dir / "decisions.json"

    @property
    def commands_path(self) -> Path:
        return self.log_dir / "commands.jsonl"

    @property
    def commands_done_path(self) -> Path:
        return self.log_dir / "commands.done"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runtime_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/runtime/config.py tests/test_runtime_config.py
git commit -m "runtime: decision-queue seam paths on RuntimeConfig"
```

---

### Task 2: Actions — study_select + ceri_reset

**Files:**
- Modify: `nta_agent/execution/actions.py`
- Test: `tests/test_actions_study.py`

**Interfaces:**
- Consumes: `GameSession.request` (existing), `state.raw["player"]`.
- Produces on `Actions`:
  - `TP_SLOT_KEY = {1: "policySlots", 2: "pawnSlots", 3: "equipSlots"}` (module or class constant).
  - `study_select(self, lv: int, ceri_id: int, tp: int) -> dict` — `game/HD_StudySelect{lv, id, tp}`; if the reply has `slots`, set `state.raw["player"][TP_SLOT_KEY[tp]] = reply["slots"]`; return reply.
  - `ceri_reset(self, lv: int, tp: int) -> dict` — `game/HD_CeriResetSelect{lv, tp}`; return reply (caller applies selectIds/resetCount to the specific slot).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_actions_study.py
from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self, reply):
        self.state = GameState(source="api")
        self.state.raw = {"player": {"pawnSlots": {}, "policySlots": {}, "equipSlots": {}}}
        self._reply = reply
        self.sent = []

    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params))
        return self._reply


def test_study_select_sends_and_applies_slots():
    reply = {"slots": {"0": {"selectIds": [], "id": 3101, "resetCount": 0, "lv": 1}}}
    s = FakeSession(reply)
    out = Actions(s).study_select(lv=1, ceri_id=5, tp=2)
    assert s.sent[0] == ("game/HD_StudySelect", {"lv": 1, "id": 5, "tp": 2})
    assert out is reply
    assert s.state.raw["player"]["pawnSlots"] == reply["slots"]


def test_ceri_reset_sends_and_returns():
    reply = {"gold": 100, "selectIds": [7, 8, 9], "resetCount": 1, "useGold": False}
    s = FakeSession(reply)
    out = Actions(s).ceri_reset(lv=2, tp=1)
    assert s.sent[0] == ("game/HD_CeriResetSelect", {"lv": 2, "tp": 1})
    assert out["selectIds"] == [7, 8, 9]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_actions_study.py -q`
Expected: FAIL — methods missing.

- [ ] **Step 3: Write minimal implementation** — add to `nta_agent/execution/actions.py` (after the task-reward methods, before combat). Add a module constant near the top:

```python
TP_SLOT_KEY = {1: "policySlots", 2: "pawnSlots", 3: "equipSlots"}
```

Methods on `Actions`:

```python
    # ---- ceri: unlock pawn / policy / equip (human-reserved) -------------- #
    def study_select(self, lv: int, ceri_id: int, tp: int) -> dict:
        """Pick a ceri option (GAME_HD_StudySelect). Applies returned slots."""
        reply = self.session.request("game/HD_StudySelect",
                                     {"lv": int(lv), "id": int(ceri_id), "tp": int(tp)})
        slots = reply.get("slots")
        key = TP_SLOT_KEY.get(int(tp))
        if isinstance(slots, dict) and key:
            player = (self._state.raw or {}).setdefault("player", {})
            player[key] = slots
        return reply

    def ceri_reset(self, lv: int, tp: int) -> dict:
        """Reroll the ceri options for a track/level (GAME_HD_CeriResetSelect)."""
        return self.session.request("game/HD_CeriResetSelect", {"lv": int(lv), "tp": int(tp)})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_actions_study.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/actions.py tests/test_actions_study.py
git commit -m "execution: study_select + ceri_reset actions (ceri unlock/reroll)"
```

---

### Task 3: Pending-decision detection (`decisions.py`)

**Files:**
- Create: `nta_agent/execution/decisions.py`
- Test: `tests/test_decisions.py`

**Interfaces:**
- Consumes: `GameState` (`state.raw["player"][<slotKey>]` maps), `GameConfig` (`table("ceri")`, `table("pawnText"|"policyText"|"equipText")`).
- Produces:
  - `TRACKS = {"pawnSlots": (2, "pawnText"), "policySlots": (1, "policyText"), "equipSlots": (3, "equipText")}`.
  - `@dataclass Decision`: `track: str`, `tp: int`, `slot_key: str`, `lv: int`, `reset_count: int`, `options: list[dict]`.
  - `pending_decisions(state, config) -> list[Decision]`.

Assume `GameConfig.table(name)` returns `{id: row}`. `ceri` rows have `value`; text rows are keyed by string id `"name_<n>"` — build a lookup once.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_decisions.py
from nta_agent.execution.decisions import Decision, pending_decisions
from nta_agent.state.schema import GameState


class FakeConfig:
    """Minimal GameConfig stand-in: table(name) -> dict[id,row]."""
    def __init__(self):
        self._t = {
            "ceri": {5: {"id": 5, "value": 3101}, 6: {"id": 6, "value": 3102},
                     7: {"id": 7, "value": 1001}},
            "pawnText": {"name_3101": {"vi": "Lính Trường Thương"},
                         "name_3102": {"vi": "Lính Trường Mâu"}},
            "policyText": {"name_1001": {"vi": "Ngũ Cốc Phong Đăng"}},
            "equipText": {},
        }
    def table(self, name):
        return self._t.get(name, {})


def _state(pawn=None, policy=None):
    st = GameState(source="api")
    st.raw = {"player": {"pawnSlots": pawn or {}, "policySlots": policy or {}, "equipSlots": {}}}
    return st


def test_pending_pawn_decision_with_names():
    st = _state(pawn={"s0": {"selectIds": [5, 6], "id": 0, "resetCount": 0, "lv": 1}})
    ds = pending_decisions(st, FakeConfig())
    assert len(ds) == 1
    d = ds[0]
    assert isinstance(d, Decision) and d.track == "pawn" and d.tp == 2 and d.lv == 1
    assert d.options == [
        {"ceri_id": 5, "value": 3101, "name": "Lính Trường Thương"},
        {"ceri_id": 6, "value": 3102, "name": "Lính Trường Mâu"},
    ]


def test_chosen_or_empty_slots_are_not_pending():
    st = _state(pawn={
        "s0": {"selectIds": [5], "id": 3101, "resetCount": 0, "lv": 1},  # already chosen
        "s1": {"selectIds": [], "id": 0, "resetCount": 0, "lv": 2},        # no options
    })
    assert pending_decisions(st, FakeConfig()) == []


def test_policy_track_and_unknown_value_fallback():
    st = _state(policy={"p0": {"selectIds": [7, 99], "id": 0, "resetCount": 2, "lv": 1}})
    ds = pending_decisions(st, FakeConfig())
    assert ds[0].track == "policy" and ds[0].tp == 1 and ds[0].reset_count == 2
    assert ds[0].options[0]["name"] == "Ngũ Cốc Phong Đăng"
    assert ds[0].options[1]["name"] == "#99"  # ceri id 99 unknown -> fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_decisions.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# nta_agent/execution/decisions.py
"""Detect reserved ceri decisions (unlock pawn/policy/equip) pending a human pick."""
from __future__ import annotations

from dataclasses import dataclass

# player slot-map field -> (StudyType tp, text table). tp verified in client.
TRACKS = {
    "pawnSlots": (2, "pawnText"),
    "policySlots": (1, "policyText"),
    "equipSlots": (3, "equipText"),
}
_TRACK_NAME = {"pawnSlots": "pawn", "policySlots": "policy", "equipSlots": "equip"}


@dataclass
class Decision:
    track: str
    tp: int
    slot_key: str
    lv: int
    reset_count: int
    options: list[dict]


def _name(text_table: dict, value: int) -> str:
    row = text_table.get(f"name_{value}") or {}
    return (row.get("vi") or row.get("en") or f"#{value}")


def pending_decisions(state, config) -> list[Decision]:
    player = (state.raw or {}).get("player", {}) or {}
    ceri = config.table("ceri")
    out: list[Decision] = []
    for slot_field, (tp, text_name) in TRACKS.items():
        text_table = config.table(text_name)
        slots = player.get(slot_field) or {}
        for slot_key, slot in slots.items():
            if not isinstance(slot, dict):
                continue
            select_ids = slot.get("selectIds") or []
            if (slot.get("id") or 0) > 0 or not select_ids:
                continue  # already chosen, or nothing offered -> not pending
            options = []
            for cid in select_ids:
                value = (ceri.get(cid) or {}).get("value", 0)
                options.append({"ceri_id": cid, "value": value,
                                "name": _name(text_table, value)})
            out.append(Decision(track=_TRACK_NAME[slot_field], tp=tp, slot_key=str(slot_key),
                                lv=int(slot.get("lv", 0) or 0),
                                reset_count=int(slot.get("resetCount", 0) or 0),
                                options=options))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_decisions.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/decisions.py tests/test_decisions.py
git commit -m "execution: detect pending ceri decisions with Vietnamese names"
```

---

### Task 4: File command channel (`runtime/commands.py`)

**Files:**
- Create: `nta_agent/runtime/commands.py`
- Test: `tests/test_commands.py`

**Interfaces:**
- Produces:
  - `append_command(path: Path, cmd: dict) -> str` — add `id` (uuid4 hex) + `ts`, append one JSON line, return the id. Creates parent dirs.
  - `read_pending(commands_path: Path, done_path: Path) -> list[dict]` — parsed command dicts (with `id`) not present in `done_path`; skips malformed lines; `[]` if commands file missing.
  - `mark_done(done_path: Path, cmd_id: str) -> None` — append the id (one per line); creates parent dirs.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_commands.py
from nta_agent.runtime.commands import append_command, mark_done, read_pending


def test_append_and_read(tmp_path):
    cmds = tmp_path / "commands.jsonl"
    done = tmp_path / "commands.done"
    cid = append_command(cmds, {"action": "select", "track": "pawn", "lv": 1, "ceri_id": 5})
    assert isinstance(cid, str) and cid
    pend = read_pending(cmds, done)
    assert len(pend) == 1 and pend[0]["id"] == cid and pend[0]["action"] == "select"


def test_done_ids_are_skipped(tmp_path):
    cmds = tmp_path / "commands.jsonl"
    done = tmp_path / "commands.done"
    c1 = append_command(cmds, {"action": "reroll", "track": "policy", "lv": 1})
    c2 = append_command(cmds, {"action": "select", "track": "pawn", "lv": 1, "ceri_id": 6})
    mark_done(done, c1)
    pend = read_pending(cmds, done)
    assert [p["id"] for p in pend] == [c2]


def test_missing_and_malformed(tmp_path):
    assert read_pending(tmp_path / "none.jsonl", tmp_path / "d") == []
    cmds = tmp_path / "commands.jsonl"
    cmds.write_text('not json\n{"id":"a","action":"reroll"}\n')
    assert [p["id"] for p in read_pending(cmds, tmp_path / "d")] == ["a"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_commands.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# nta_agent/runtime/commands.py
"""File-based dashboard->agent command channel (append-only + done-set)."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path


def append_command(path: Path, cmd: dict) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cid = uuid.uuid4().hex
    row = {"id": cid, "ts": time.time(), **cmd}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return cid


def _done_ids(done_path: Path) -> set[str]:
    try:
        return {ln.strip() for ln in Path(done_path).read_text(encoding="utf-8").splitlines() if ln.strip()}
    except OSError:
        return set()


def read_pending(commands_path: Path, done_path: Path) -> list[dict]:
    try:
        lines = Path(commands_path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    done = _done_ids(done_path)
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict) and obj.get("id") and obj["id"] not in done:
            out.append(obj)
    return out


def mark_done(done_path: Path, cmd_id: str) -> None:
    done_path = Path(done_path)
    done_path.parent.mkdir(parents=True, exist_ok=True)
    with done_path.open("a", encoding="utf-8") as f:
        f.write(str(cmd_id) + "\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_commands.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/runtime/commands.py tests/test_commands.py
git commit -m "runtime: file command channel (append/read_pending/mark_done)"
```

---

### Task 5: DecisionService + wire into runner

**Files:**
- Create: `nta_agent/runtime/decision_service.py`
- Modify: `nta_agent/runtime/runner.py` (construct the service, call it in `on_tick`)
- Test: `tests/test_decision_service.py`

**Interfaces:**
- Consumes: `pending_decisions` (Task 3), `Actions.study_select`/`ceri_reset` (Task 2), commands channel (Task 4), `RuntimeConfig` paths (Task 1), `dataclasses.asdict`.
- Produces:
  - `class DecisionService` with `__init__(self, actions, config, cfg, on_event=None)` and `tick(self, state) -> None`:
    1. write `[asdict(d) for d in pending_decisions(state, config)]` atomically to `cfg.decisions_path` (guarded);
    2. for each `read_pending(cfg.commands_path, cfg.commands_done_path)`: dispatch and `mark_done` (always), emitting an event on ok/err.
  - Dispatch: `action == "select"` → `actions.study_select(lv, ceri_id, tp)`; `action == "reroll"` → `actions.ceri_reset(lv, tp)`; `tp` from `decisions.TRACKS` via the command's `track`. Unknown/malformed → event `decision_error`, still marked done.
- Runner: build `DecisionService(actions, config, cfg, on_event=log.append)` when config loads (fall back to no service if `GameConfig` unavailable), and call `service.tick(state)` inside `on_tick` after snapshot/eventlog.

Note: `DecisionService` maps `track` → `tp` with `{"pawn":2,"policy":1,"equip":3}` (from `decisions.TRACKS`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_decision_service.py
import json
from nta_agent.runtime.commands import append_command
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.decision_service import DecisionService
from nta_agent.state.schema import GameState
from tests.test_decisions import FakeConfig  # reuse the minimal config


class FakeActions:
    def __init__(self):
        self.calls = []
    def study_select(self, lv, ceri_id, tp):
        self.calls.append(("select", lv, ceri_id, tp)); return {"slots": {}}
    def ceri_reset(self, lv, tp):
        self.calls.append(("reroll", lv, tp)); return {"selectIds": [1], "resetCount": 1}


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def _state():
    st = GameState(source="api")
    st.raw = {"player": {"pawnSlots": {"s0": {"selectIds": [5, 6], "id": 0, "resetCount": 0, "lv": 1}},
                          "policySlots": {}, "equipSlots": {}}}
    return st


def test_tick_writes_decisions(tmp_path):
    cfg = _cfg(tmp_path)
    svc = DecisionService(FakeActions(), FakeConfig(), cfg)
    svc.tick(_state())
    ds = json.loads(cfg.decisions_path.read_text())
    assert ds[0]["track"] == "pawn" and ds[0]["options"][0]["name"] == "Lính Trường Thương"


def test_tick_executes_select_once(tmp_path):
    cfg = _cfg(tmp_path)
    act = FakeActions()
    svc = DecisionService(act, FakeConfig(), cfg)
    append_command(cfg.commands_path, {"action": "select", "track": "pawn", "lv": 1, "ceri_id": 5})
    svc.tick(_state())
    svc.tick(_state())  # second tick must NOT re-run
    assert act.calls == [("select", 1, 5, 2)]


def test_tick_executes_reroll(tmp_path):
    cfg = _cfg(tmp_path)
    act = FakeActions()
    svc = DecisionService(act, FakeConfig(), cfg)
    append_command(cfg.commands_path, {"action": "reroll", "track": "policy", "lv": 2})
    svc.tick(_state())
    assert act.calls == [("reroll", 2, 1)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_decision_service.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation** — `nta_agent/runtime/decision_service.py`:

```python
"""Per-tick service: publish pending decisions + execute human commands."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from nta_agent.execution.decisions import TRACKS, pending_decisions
from nta_agent.runtime.commands import mark_done, read_pending

_TRACK_TP = {"pawn": 2, "policy": 1, "equip": 3}


class DecisionService:
    def __init__(self, actions, config, cfg, on_event=None):
        self.actions = actions
        self.config = config
        self.cfg = cfg
        self._on_event = on_event or (lambda *a: None)

    def _write_decisions(self, state) -> None:
        data = [asdict(d) for d in pending_decisions(state, self.config)]
        path = Path(self.cfg.decisions_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def _execute(self, cmd: dict) -> None:
        action, track = cmd.get("action"), cmd.get("track")
        tp = _TRACK_TP.get(track)
        lv = int(cmd.get("lv", 0) or 0)
        if tp is None:
            raise ValueError(f"unknown track {track!r}")
        if action == "select":
            self.actions.study_select(lv, int(cmd["ceri_id"]), tp)
        elif action == "reroll":
            self.actions.ceri_reset(lv, tp)
        else:
            raise ValueError(f"unknown action {action!r}")

    def tick(self, state) -> None:
        try:
            self._write_decisions(state)
        except Exception as e:  # observability must not kill the loop
            sys.stderr.write(f"[decisions] write failed: {e}\n")
        for cmd in read_pending(self.cfg.commands_path, self.cfg.commands_done_path):
            try:
                self._execute(cmd)
                self._on_event("decision_done", {"id": cmd["id"], "action": cmd.get("action")})
            except Exception as e:
                self._on_event("decision_error", {"id": cmd.get("id"), "error": str(e)})
            finally:
                mark_done(self.cfg.commands_done_path, cmd["id"])
```

Then wire into `nta_agent/runtime/runner.py`. Add imports and build the service in `run`:

```python
from nta_agent.data.config import GameConfig
from nta_agent.runtime.decision_service import DecisionService
```

Inside `run`, after `agent = Agent(...)`:

```python
    service = None
    try:
        service = DecisionService(agent.actions, GameConfig.load(), cfg, on_event=log.append)
    except FileNotFoundError:
        log.append("decisions_config_missing")

    def on_tick(i, fired, state):
        _safe(write_snapshot, state, cfg.snapshot_path)
        _safe(log.tick, i, fired, state)
        if service is not None:
            _safe(service.tick, state)
```

(Replace the existing `on_tick` definition with this one; `Agent` exposes `.actions`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_decision_service.py tests/test_runner.py -q`
Expected: PASS (decision-service tests + the existing runner test still green).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/runtime/decision_service.py nta_agent/runtime/runner.py tests/test_decision_service.py
git commit -m "runtime: DecisionService publishes decisions + executes commands; wired into runner"
```

---

### Task 6: Dashboard API — /api/decisions + POST /api/command

**Files:**
- Modify: `nta_agent/dashboard/server.py`
- Test: `tests/test_dashboard_decisions_api.py`

**Interfaces:**
- Consumes: `read_state`/`tail_events` (existing), `append_command` (Task 4), `RuntimeConfig` decision paths (Task 1), `nta_agent.dashboard.data.read_state` pattern for reading `decisions.json`.
- Produces:
  - `GET /api/decisions` → the parsed `decisions.json` array (`[]` when missing/corrupt).
  - `POST /api/command` → read the request body (`Content-Length`), parse JSON `{action, track, lv, ceri_id?}`; validate (`action` in {"select","reroll"}; `track` in {"pawn","policy","equip"}; `select` requires `ceri_id`); on valid → `append_command(cfg.commands_path, cmd)` → `{"ok": true, "id": cid}`; on invalid JSON/fields → 400 `{"ok": false, "error": ...}`.
- Add a `read_json_array(path)` helper in `data.py` (returns `[]` on missing/corrupt/non-list), tested implicitly here.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_decisions_api.py
import json
import threading
import urllib.request
from nta_agent.dashboard.server import serve
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.commands import read_pending


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def _serve(cfg):
    srv = serve(cfg, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _post(port, path, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_get_decisions(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.decisions_path.write_text(json.dumps([{"track": "pawn", "lv": 1, "options": []}]))
    srv, port = _serve(cfg)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/decisions", timeout=5) as r:
            data = json.loads(r.read())
        assert data[0]["track"] == "pawn"
    finally:
        srv.shutdown()


def test_post_command_appends(tmp_path):
    cfg = _cfg(tmp_path)
    srv, port = _serve(cfg)
    try:
        st, body = _post(port, "/api/command",
                         {"action": "select", "track": "pawn", "lv": 1, "ceri_id": 5})
        assert st == 200 and body["ok"] is True and body["id"]
        pend = read_pending(cfg.commands_path, cfg.commands_done_path)
        assert pend[0]["action"] == "select" and pend[0]["ceri_id"] == 5
    finally:
        srv.shutdown()


def test_post_command_bad_body_400(tmp_path):
    cfg = _cfg(tmp_path)
    srv, port = _serve(cfg)
    try:
        st, body = _post(port, "/api/command", {"action": "nope", "track": "pawn", "lv": 1})
        assert st == 400 and body["ok"] is False
    finally:
        srv.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_decisions_api.py -q`
Expected: FAIL — routes missing.

- [ ] **Step 3: Write minimal implementation** — in `nta_agent/dashboard/data.py` add:

```python
def read_json_array(path: Path) -> list:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return []
    return data if isinstance(data, list) else []
```

In `nta_agent/dashboard/server.py`: import `read_json_array` and `append_command`; add a `do_POST` and extend `do_GET`.

```python
from nta_agent.dashboard.data import read_json_array, read_state, tail_events
from nta_agent.runtime.commands import append_command

_VALID_TRACK = {"pawn", "policy", "equip"}
```

Add to `do_GET` (before the 404 branch):

```python
        elif parsed.path == "/api/decisions":
            self._json(200, read_json_array(cfg.decisions_path))
```

Add a `do_POST`:

```python
    def do_POST(self):
        parsed = urlparse(self.path)
        cfg = self.server.cfg
        if parsed.path != "/api/command":
            self._json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            self._json(400, {"ok": False, "error": "bad json"})
            return
        action, track = body.get("action"), body.get("track")
        if action not in ("select", "reroll") or track not in _VALID_TRACK:
            self._json(400, {"ok": False, "error": "bad action/track"})
            return
        if action == "select" and "ceri_id" not in body:
            self._json(400, {"ok": False, "error": "select needs ceri_id"})
            return
        cmd = {"action": action, "track": track, "lv": int(body.get("lv", 0) or 0)}
        if action == "select":
            cmd["ceri_id"] = int(body["ceri_id"])
        cid = append_command(cfg.commands_path, cmd)
        self._json(200, {"ok": True, "id": cid})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_decisions_api.py tests/test_dashboard_server.py -q`
Expected: PASS (new API tests + existing server tests still green).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/dashboard/data.py nta_agent/dashboard/server.py tests/test_dashboard_decisions_api.py
git commit -m "dashboard: /api/decisions + POST /api/command"
```

---

### Task 7: Dashboard page — pending-decisions panel

**Files:**
- Modify: `nta_agent/dashboard/page.py`
- Test: `tests/test_dashboard_page.py` (extend)

**Interfaces:**
- Produces: `INDEX_HTML` gains a "Quyết định đang chờ" card that polls `/api/decisions`, renders each decision's options as buttons and a reroll button, and POSTs to `/api/command` on click.

- [ ] **Step 1: Write the failing test** — append to `tests/test_dashboard_page.py`:

```python
def test_index_html_has_decisions_panel():
    from nta_agent.dashboard.page import INDEX_HTML
    assert "/api/decisions" in INDEX_HTML
    assert "/api/command" in INDEX_HTML
    assert "Quyết định đang chờ" in INDEX_HTML
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_page.py -q`
Expected: FAIL — markers absent.

- [ ] **Step 3: Write minimal implementation** — in `nta_agent/dashboard/page.py`, add a card to the `<main>` (after the misc card, before the feed card):

```html
 <div class="card full"><h2>Quyết định đang chờ</h2><div id="decisions"><span class=muted>—</span></div></div>
```

And add JS before `refresh();setInterval(...)` (and call `renderDecisions()` inside `refresh`):

```javascript
async function post(cmd){try{await fetch("/api/command",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(cmd)});}catch(e){}}
function decCard(d){
 const opts=(d.options||[]).map(o=>`<button data-a=select data-t="${d.track}" data-lv="${d.lv}" data-id="${o.ceri_id}">${o.name}</button>`).join(" ");
 const reroll=`<button data-a=reroll data-t="${d.track}" data-lv="${d.lv}">Làm mới${d.reset_count?(" ("+d.reset_count+")"):" (free)"}</button>`;
 return `<div style="margin:6px 0"><span class=muted>${d.track} · Lv${d.lv}</span><br>${opts} ${reroll}</div>`;
}
async function renderDecisions(){
 const ds=await j("/api/decisions")||[];
 const box=document.getElementById("decisions");
 box.innerHTML=ds.length?ds.map(decCard).join(""):"<span class=muted>—</span>";
 box.querySelectorAll("button").forEach(b=>b.onclick=async()=>{
   const cmd={action:b.dataset.a,track:b.dataset.t,lv:Number(b.dataset.lv)};
   if(b.dataset.a==="select")cmd.ceri_id=Number(b.dataset.id);
   b.disabled=true;b.textContent="đã gửi…";await post(cmd);
 });
}
```

Add `renderDecisions();` inside `refresh()` (e.g., right after the events feed render).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_page.py -q`
Expected: PASS.

- [ ] **Step 5: Full verification + commit**

Run: `.venv/Scripts/python.exe -m pytest -q` (all pass) and `.venv/Scripts/python.exe -m ruff check nta_agent tests` (clean).

```bash
git add nta_agent/dashboard/page.py tests/test_dashboard_page.py
git commit -m "dashboard: pending-decisions panel (select/reroll)"
```

---

## Self-Review

**Spec coverage:**
- §4.1 decisions.py → Task 3. §4.2 actions study_select/ceri_reset → Task 2. §4.3 commands.py → Task 4. §4.4 decision_service + runner wiring → Task 5. §4.5 dashboard API + config paths + page → Tasks 1, 6, 7. ✓
- §2 tp values (POLICY=1/PAWN=2/EQUIP=3), pending rule (id<=0 && selectIds), name resolution → Task 3 (constants + logic) + Global Constraints. ✓
- §3 file command channel, exactly-once (commands.done) → Task 4 + Task 5. ✓
- §6 error handling: guarded decisions write + execute-once + mark_done always + 400 on bad POST → Tasks 5, 6. ✓
- §7 testing: decisions/actions/commands/decision_service/dashboard all covered. ✓
- §8 out of scope (gear assignment/forge = 2E, captcha = 2D) — not in any task. ✓

**Placeholder scan:** No TBD/TODO; every code step complete. tp values are concrete (verified), not deferred.

**Type consistency:** `TRACKS` (Task 3) and `_TRACK_TP`/`TP_SLOT_KEY` (Tasks 2/5) agree: pawn=2, policy=1, equip=3. `Decision` fields (Task 3) → `asdict` → `decisions.json` → dashboard `d.track/d.lv/d.options/d.reset_count` (Task 7) and API passthrough (Task 6). Command dict shape `{id, ts, action, track, lv, ceri_id?}` is produced by `append_command` (Task 4), validated in `POST /api/command` (Task 6), consumed by `DecisionService._execute` (Task 5). `RuntimeConfig.decisions_path/commands_path/commands_done_path` (Task 1) used in Tasks 5/6. `Actions.study_select(lv, ceri_id, tp)`/`ceri_reset(lv, tp)` (Task 2) called by `DecisionService._execute` (Task 5). `read_json_array` (Task 6) added to data.py.
