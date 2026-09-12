# Gear Assignment (Chặng 2E-1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the human assign owned equipment to each pawn type from the dashboard; the agent executes `ChangeConfigPawnEquip` on the live session. Forge is out of scope (2E-2).

**Architecture:** Pure view builder (`execution/equipment.py`) + one `Actions` method + a new config path; the existing `DecisionService` (the single command consumer) writes an `equipment.json` view and dispatches a new `equip` command; the dashboard gains `GET /api/equipment`, a `POST /api/command` `equip` action, and a "Trang bị lính" section.

**Tech Stack:** Python 3.12 stdlib, pytest, ruff. Venv at `.venv`.

**Spec:** `docs/superpowers/specs/2026-09-12-gear-assignment-design.md`

## Global Constraints

- Python 3.12; venv runs: `.venv/Scripts/python.exe -m pytest -q`, `.venv/Scripts/python.exe -m ruff check nta_agent tests`. Ruff clean.
- stdlib only; dashboard binds `127.0.0.1`.
- Reuse the 2C command channel (`commands.jsonl` + `commands.done`) — `DecisionService` stays the ONLY consumer. New action: `equip`.
- Assign call: `game/HD_ChangeConfigPawnEquip{id: pawnId, equipUid, skinId, attackSpeed}`. The command echoes the pawn's current `skin_id`/`attack_speed` so only the equip changes.
- Data: `player.configPawnMap` (map pawnId→`{equipUid,skinId,attackSpeed}`), `player.equips` (list of `{uid,id,...}`), `equipBase[id].exclusive_pawn` (empty ⇒ any pawn). Names: `pawnText`/`equipText` `name_<id>` `.vi` (fallback `.en`, then `#<id>`).
- Config absent ⇒ empty view; commands still execute.

---

### Task 1: equipment view (`equipment.py`)

**Files:**
- Create: `nta_agent/execution/equipment.py`
- Test: `tests/test_equipment.py`

**Interfaces:**
- Produces:
  - `pawn_name(config, pawn_id) -> str`, `equip_name(config, equip_id) -> str`.
  - `_compatible(config, equip_id, pawn_id) -> bool`.
  - `pawn_equipment(state, config) -> list[dict]` with rows
    `{pawn_id, pawn_name, current_equip_uid, current_equip_name, skin_id,
    attack_speed, options: [{uid, id, name}]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_equipment.py
from nta_agent.execution.equipment import pawn_equipment
from nta_agent.state.schema import GameState


class FakeConfig:
    def __init__(self):
        self._t = {
            "pawnText": {"name_3101": {"vi": "Lính Trường Thương"}},
            "equipText": {"name_6001": {"vi": "Kiếm Sắt"}, "name_6003": {"vi": "Đao Hồi Máu"}},
            "equipBase": {6001: {"id": 6001, "exclusive_pawn": ""},
                          6003: {"id": 6003, "exclusive_pawn": "3999"}},  # exclusive to another pawn
        }

    def table(self, name):
        return self._t.get(name, {})


def _state():
    st = GameState(source="api")
    st.raw = {"player": {
        "configPawnMap": {"3101": {"equipUid": "e1", "skinId": 0, "attackSpeed": 6}},
        "equips": [{"uid": "e1", "id": 6001}, {"uid": "e2", "id": 6003}],
    }}
    return st


def test_pawn_equipment_row_and_compat_filtering():
    rows = pawn_equipment(_state(), FakeConfig())
    assert len(rows) == 1
    r = rows[0]
    assert r["pawn_id"] == 3101 and r["pawn_name"] == "Lính Trường Thương"
    assert r["current_equip_uid"] == "e1" and r["current_equip_name"] == "Kiếm Sắt"
    assert r["skin_id"] == 0 and r["attack_speed"] == 6
    # e1 (6001, general) is an option; e2 (6003, exclusive to 3999) is filtered out
    assert r["options"] == [{"uid": "e1", "id": 6001, "name": "Kiếm Sắt"}]


def test_unknown_names_fall_back():
    st = GameState(source="api")
    st.raw = {"player": {"configPawnMap": {"3102": {"equipUid": "", "skinId": 0, "attackSpeed": 0}},
                          "equips": [{"uid": "x", "id": 9999}]}}
    rows = pawn_equipment(st, FakeConfig())
    assert rows[0]["pawn_name"] == "#3102"
    assert rows[0]["current_equip_uid"] == "" and rows[0]["current_equip_name"] == ""
    assert rows[0]["options"] == [{"uid": "x", "id": 9999, "name": "#9999"}]  # unknown equip -> compatible
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_equipment.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# nta_agent/execution/equipment.py
"""Build the per-pawn equipment view (human-reserved gear assignment)."""
from __future__ import annotations


def _text(config, table_name: str, id_: int) -> str:
    row = config.table(table_name).get(f"name_{id_}") or {}
    return row.get("vi") or row.get("en") or f"#{id_}"


def pawn_name(config, pawn_id: int) -> str:
    return _text(config, "pawnText", pawn_id)


def equip_name(config, equip_id: int) -> str:
    return _text(config, "equipText", equip_id)


def _compatible(config, equip_id: int, pawn_id: int) -> bool:
    row = config.table("equipBase").get(equip_id)
    if not row:
        return True  # unknown -> let the server validate
    ex = str(row.get("exclusive_pawn") or "").strip()
    if not ex:
        return True
    parts = ex.replace("|", ",").split(",")
    return str(pawn_id) in [p.strip() for p in parts]


def pawn_equipment(state, config) -> list[dict]:
    player = (state.raw or {}).get("player", {}) or {}
    equips = player.get("equips") or []
    by_uid = {e.get("uid"): e for e in equips if isinstance(e, dict)}
    rows: list[dict] = []
    for pid_str, cfg in (player.get("configPawnMap") or {}).items():
        if not isinstance(cfg, dict):
            continue
        pid = int(pid_str)
        cur_uid = cfg.get("equipUid", "") or ""
        cur = by_uid.get(cur_uid)
        cur_name = equip_name(config, cur["id"]) if cur else ""
        options = [
            {"uid": e["uid"], "id": e["id"], "name": equip_name(config, e["id"])}
            for e in equips
            if isinstance(e, dict) and _compatible(config, e.get("id", 0), pid)
        ]
        rows.append({
            "pawn_id": pid,
            "pawn_name": pawn_name(config, pid),
            "current_equip_uid": cur_uid,
            "current_equip_name": cur_name,
            "skin_id": int(cfg.get("skinId", 0) or 0),
            "attack_speed": int(cfg.get("attackSpeed", 0) or 0),
            "options": options,
        })
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_equipment.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/equipment.py tests/test_equipment.py
git commit -m "execution: per-pawn equipment view (gear assignment)"
```

---

### Task 2: Actions — change_pawn_equip

**Files:**
- Modify: `nta_agent/execution/actions.py`
- Test: `tests/test_actions_equip.py`

**Interfaces:**
- Produces on `Actions`: `change_pawn_equip(pawn_id, equip_uid, skin_id=0, attack_speed=0) -> dict` — `game/HD_ChangeConfigPawnEquip{id, equipUid, skinId, attackSpeed}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_actions_equip.py
from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self):
        self.state = GameState(source="api")
        self.sent = []

    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params))
        return {}


def test_change_pawn_equip():
    s = FakeSession()
    Actions(s).change_pawn_equip(3101, "e1", skin_id=2, attack_speed=6)
    assert s.sent[0] == ("game/HD_ChangeConfigPawnEquip",
                         {"id": 3101, "equipUid": "e1", "skinId": 2, "attackSpeed": 6})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_actions_equip.py -q`
Expected: FAIL — method missing.

- [ ] **Step 3: Write minimal implementation** — add to `nta_agent/execution/actions.py` after `answer_anticheat`:

```python
    # ---- equipment (gear assignment) ------------------------------------ #
    def change_pawn_equip(self, pawn_id: int, equip_uid: str,
                          skin_id: int = 0, attack_speed: int = 0) -> dict:
        """Assign an owned equip to a pawn config (GAME_HD_ChangeConfigPawnEquip)."""
        return self.session.request("game/HD_ChangeConfigPawnEquip", {
            "id": int(pawn_id), "equipUid": str(equip_uid),
            "skinId": int(skin_id), "attackSpeed": int(attack_speed),
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_actions_equip.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/actions.py tests/test_actions_equip.py
git commit -m "execution: change_pawn_equip action"
```

---

### Task 3: RuntimeConfig — equipment_path

**Files:**
- Modify: `nta_agent/runtime/config.py`
- Test: `tests/test_runtime_config.py` (extend)

**Interfaces:**
- Produces on `RuntimeConfig`: `equipment_path` (`log_dir/"equipment.json"`).

- [ ] **Step 1: Write the failing test** — append to `tests/test_runtime_config.py`:

```python
def test_equipment_path():
    cfg = RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": "/l"})
    assert cfg.equipment_path == Path("/l/equipment.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runtime_config.py::test_equipment_path -q`
Expected: FAIL — attribute missing.

- [ ] **Step 3: Write minimal implementation** — add to `RuntimeConfig` after `commands_done_path`:

```python
    @property
    def equipment_path(self) -> Path:
        return self.log_dir / "equipment.json"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runtime_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/runtime/config.py tests/test_runtime_config.py
git commit -m "runtime: equipment_path on RuntimeConfig"
```

---

### Task 4: DecisionService — write equipment.json + equip dispatch

**Files:**
- Modify: `nta_agent/runtime/decision_service.py`
- Test: `tests/test_decision_service_equip.py`

**Interfaces:**
- Consumes: `pawn_equipment` (Task 1), `Actions.change_pawn_equip` (Task 2), `RuntimeConfig.equipment_path` (Task 3).
- Produces: `DecisionService.tick(state)` also writes `equipment_path` (atomic, guarded); `_execute(cmd)` handles `action == "equip"` →
  `actions.change_pawn_equip(int(cmd["pawn_id"]), cmd["equip_uid"], int(cmd.get("skin_id",0) or 0), int(cmd.get("attack_speed",0) or 0))`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_decision_service_equip.py
import json

from nta_agent.runtime.commands import append_command
from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.decision_service import DecisionService
from nta_agent.state.schema import GameState
from tests.test_equipment import FakeConfig


class FakeActions:
    def __init__(self):
        self.calls = []

    def change_pawn_equip(self, pawn_id, equip_uid, skin_id=0, attack_speed=0):
        self.calls.append((pawn_id, equip_uid, skin_id, attack_speed))
        return {}


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def _state():
    st = GameState(source="api")
    st.raw = {"player": {
        "configPawnMap": {"3101": {"equipUid": "e1", "skinId": 0, "attackSpeed": 6}},
        "equips": [{"uid": "e1", "id": 6001}],
    }}
    return st


def test_tick_writes_equipment_json(tmp_path):
    cfg = _cfg(tmp_path)
    DecisionService(FakeActions(), FakeConfig(), cfg).tick(_state())
    rows = json.loads(cfg.equipment_path.read_text(encoding="utf-8"))
    assert rows[0]["pawn_id"] == 3101 and rows[0]["current_equip_name"] == "Kiếm Sắt"


def test_equip_command_calls_change_pawn_equip(tmp_path):
    cfg = _cfg(tmp_path)
    act = FakeActions()
    svc = DecisionService(act, FakeConfig(), cfg)
    append_command(cfg.commands_path, {"action": "equip", "pawn_id": 3101,
                                       "equip_uid": "e1", "skin_id": 0, "attack_speed": 6})
    svc.tick(_state())
    svc.tick(_state())  # once-only
    assert act.calls == [(3101, "e1", 0, 6)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_decision_service_equip.py -q`
Expected: FAIL — no equipment.json / equip dispatch.

- [ ] **Step 3: Write minimal implementation** — in `nta_agent/runtime/decision_service.py`:

Add the import:

```python
from nta_agent.execution.equipment import pawn_equipment
```

Add a writer method (next to `_write_decisions`):

```python
    def _write_equipment(self, state) -> None:
        data = pawn_equipment(state, self.config)
        path = Path(self.cfg.equipment_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
```

In `tick`, after the guarded `_write_decisions` call, add a guarded equipment write:

```python
        try:
            self._write_equipment(state)
        except Exception as e:
            sys.stderr.write(f"[equipment] write failed: {e}\n")
```

In `_execute`, add before the final `else`:

```python
        elif action == "equip":
            self.actions.change_pawn_equip(
                int(cmd["pawn_id"]), cmd["equip_uid"],
                int(cmd.get("skin_id", 0) or 0), int(cmd.get("attack_speed", 0) or 0))
```

(The `tp`/`track` lookup at the top of `_execute` only applies to select/reroll; keep it, but guard so an `equip` command does not require a track — see note.)

Note: reorder `_execute` so the `equip` branch does not hit the `track`/`tp` resolution. Concretely, structure it as:

```python
    def _execute(self, cmd: dict) -> None:
        action = cmd.get("action")
        lv = int(cmd.get("lv", 0) or 0)
        if action == "equip":
            self.actions.change_pawn_equip(
                int(cmd["pawn_id"]), cmd["equip_uid"],
                int(cmd.get("skin_id", 0) or 0), int(cmd.get("attack_speed", 0) or 0))
            return
        track = cmd.get("track")
        tp = _TRACK_TP.get(track)
        if tp is None:
            raise ValueError(f"unknown track {track!r}")
        if action == "select":
            self.actions.study_select(lv, int(cmd["ceri_id"]), tp)
        elif action == "reroll":
            self.actions.ceri_reset(lv, tp)
        else:
            raise ValueError(f"unknown action {action!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_decision_service_equip.py tests/test_decision_service.py -q`
Expected: PASS (new equip tests + existing decision-service tests still green).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/runtime/decision_service.py tests/test_decision_service_equip.py
git commit -m "runtime: DecisionService writes equipment.json + handles equip command"
```

---

### Task 5: Dashboard API — /api/equipment + equip POST

**Files:**
- Modify: `nta_agent/dashboard/server.py`
- Test: `tests/test_dashboard_equipment_api.py`

**Interfaces:**
- Consumes: `read_json_array` (existing), `append_command` (existing), `RuntimeConfig.equipment_path` (Task 3).
- Produces: `GET /api/equipment` → the equipment array; `POST /api/command` accepts `action=="equip"` with `{pawn_id, equip_uid, skin_id?, attack_speed?}` (requires `pawn_id` and `equip_uid`), appending a command with those fields.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_equipment_api.py
import json
import threading
import urllib.error
import urllib.request

from nta_agent.dashboard.server import serve
from nta_agent.runtime.commands import read_pending
from nta_agent.runtime.config import RuntimeConfig


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def _serve(cfg):
    srv = serve(cfg, 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _post(port, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/command",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_get_equipment(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.equipment_path.write_text(json.dumps([{"pawn_id": 3101, "options": []}]))
    srv, port = _serve(cfg)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/equipment", timeout=5) as r:
            data = json.loads(r.read())
        assert data[0]["pawn_id"] == 3101
    finally:
        srv.shutdown()


def test_post_equip_command(tmp_path):
    cfg = _cfg(tmp_path)
    srv, port = _serve(cfg)
    try:
        st, body = _post(port, {"action": "equip", "pawn_id": 3101, "equip_uid": "e1",
                                "skin_id": 0, "attack_speed": 6})
        assert st == 200 and body["ok"] is True
        pend = read_pending(cfg.commands_path, cfg.commands_done_path)
        assert pend[0]["action"] == "equip" and pend[0]["pawn_id"] == 3101 and pend[0]["equip_uid"] == "e1"
    finally:
        srv.shutdown()


def test_post_equip_missing_fields_400(tmp_path):
    cfg = _cfg(tmp_path)
    srv, port = _serve(cfg)
    try:
        st, body = _post(port, {"action": "equip", "pawn_id": 3101})  # no equip_uid
        assert st == 400 and body["ok"] is False
    finally:
        srv.shutdown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_equipment_api.py -q`
Expected: FAIL — no /api/equipment; equip rejected by current validation.

- [ ] **Step 3: Write minimal implementation** — in `nta_agent/dashboard/server.py`:

Add to `do_GET` (before the 404 branch):

```python
        elif parsed.path == "/api/equipment":
            self._json(200, read_json_array(cfg.equipment_path))
```

Replace the `do_POST` validation/build block (from `action, track = ...` through the `append_command` call) with an action-branched version:

```python
        action = body.get("action")
        if action == "equip":
            if not body.get("pawn_id") and body.get("pawn_id") != 0 or not body.get("equip_uid"):
                self._json(400, {"ok": False, "error": "equip needs pawn_id + equip_uid"})
                return
            cmd = {"action": "equip", "pawn_id": int(body["pawn_id"]),
                   "equip_uid": str(body["equip_uid"]),
                   "skin_id": int(body.get("skin_id", 0) or 0),
                   "attack_speed": int(body.get("attack_speed", 0) or 0)}
            cid = append_command(cfg.commands_path, cmd)
            self._json(200, {"ok": True, "id": cid})
            return
        track = body.get("track")
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

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_equipment_api.py tests/test_dashboard_decisions_api.py -q`
Expected: PASS (equip API + existing decision API still green).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/dashboard/server.py tests/test_dashboard_equipment_api.py
git commit -m "dashboard: /api/equipment + equip command"
```

---

### Task 6: Dashboard page — "Trang bị lính" section

**Files:**
- Modify: `nta_agent/dashboard/page.py`
- Test: `tests/test_dashboard_page.py` (extend)

**Interfaces:**
- Produces: `INDEX_HTML` gains a "Trang bị lính" card polling `/api/equipment`, rendering each pawn's current gear + compatible options as buttons that POST an `equip` command.

- [ ] **Step 1: Write the failing test** — append to `tests/test_dashboard_page.py`:

```python
def test_index_html_has_equipment_panel():
    from nta_agent.dashboard.page import INDEX_HTML
    assert "/api/equipment" in INDEX_HTML
    assert "Trang bị lính" in INDEX_HTML
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_page.py -q`
Expected: FAIL — marker absent.

- [ ] **Step 3: Write minimal implementation** — in `nta_agent/dashboard/page.py`:

Add a card to `<main>` after the decisions card:

```html
 <div class="card full"><h2>Trang bị lính</h2><div id="equipment"><span class="muted">—</span></div></div>
```

Add JS (near `renderDecisions`, using the existing `post`/`j` helpers):

```javascript
function equipRow(p){
 const opts=(p.options||[]).map(o=>`<button data-p="${p.pawn_id}" data-u="${o.uid}" data-sk="${p.skin_id}" data-as="${p.attack_speed}"${o.uid===p.current_equip_uid?" disabled":""}>${o.name}</button>`).join(" ");
 return `<div style="margin:6px 0"><span class=muted>${p.pawn_name}</span> — hiện: <b>${p.current_equip_name||"—"}</b><br>${opts||"<span class=muted>không có trang bị phù hợp</span>"}</div>`;
}
async function renderEquipment(){
 const ps=await j("/api/equipment")||[];
 const box=document.getElementById("equipment");
 box.innerHTML=ps.length?ps.map(equipRow).join(""):"<span class=muted>—</span>";
 box.querySelectorAll("button").forEach(b=>b.onclick=async()=>{
   const cmd={action:"equip",pawn_id:Number(b.dataset.p),equip_uid:b.dataset.u,
              skin_id:Number(b.dataset.sk),attack_speed:Number(b.dataset.as)};
   b.disabled=true;b.textContent="đã gửi…";await post(cmd);
 });
}
```

Add `renderEquipment();` inside `refresh()` (next to `renderDecisions();`).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_page.py -q`
Expected: PASS.

- [ ] **Step 5: Full verification + commit**

Run: `.venv/Scripts/python.exe -m pytest -q` (all pass) and `.venv/Scripts/python.exe -m ruff check nta_agent tests` (clean).

```bash
git add nta_agent/dashboard/page.py tests/test_dashboard_page.py
git commit -m "dashboard: Trang bị lính (gear assignment) section"
```

---

## Self-Review

**Spec coverage:**
- §4.1 equipment.py → Task 1. §4.2 change_pawn_equip → Task 2. §4.3 equipment_path → Task 3. §4.4 DecisionService write+dispatch → Task 4. §4.5 dashboard API + page → Tasks 5, 6. ✓
- §2 ChangeConfigPawnEquip params + skin/attack echo → Tasks 2, 4, 5 (command carries skin_id/attack_speed). ✓
- §3 single command consumer (equip added to DecisionService) → Task 4. ✓
- §6 error handling: guarded equipment write (Task 4), server error caught by existing `_execute` try/finally (2C), POST 400 on missing fields (Task 5), config-absent empty view (Task 1). ✓
- §7 testing: equipment/actions/decision_service/dashboard-api/page all covered. ✓
- §8 out of scope (forge, skin/attack as choices, auto-assign) — not in any task. ✓

**Placeholder scan:** No TBD/TODO; every code step complete.

**Type consistency:** `pawn_equipment` row keys (Task 1) → written to `equipment.json` (Task 4) → served by `/api/equipment` (Task 5) → consumed by page `p.pawn_id/pawn_name/current_equip_name/options/skin_id/attack_speed` (Task 6). Equip command shape `{action:"equip", pawn_id, equip_uid, skin_id, attack_speed}` produced by POST (Task 5) and consumed by `_execute` (Task 4). `change_pawn_equip(pawn_id, equip_uid, skin_id, attack_speed)` signature matches between Tasks 2 and 4. `RuntimeConfig.equipment_path` (Task 3) used in Tasks 4/5. `read_json_array`/`append_command`/`_VALID_TRACK` reused from 2B/2C.
