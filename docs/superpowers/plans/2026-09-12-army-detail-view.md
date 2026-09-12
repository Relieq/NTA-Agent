# Army/Squad Detail View + Dashboard Polish (Chặng A1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only per-army/per-troop detail view to the dashboard (throttled `GetPlayerArmys`), fix resource labels, add per-option descriptions, and lightly restyle for clarity.

**Architecture:** Pure `army_view` (`execution/armies.py`) + one `Actions` fetch + a config path; `DecisionService` fetches armies on a throttle and writes `armies.json`; the dashboard gains `GET /api/armies`, an "Đội quân" section, corrected resource labels, and rendered option descriptions. Decisions gain a `desc` per option.

**Tech Stack:** Python 3.12 stdlib, pytest, ruff. Venv at `.venv`.

**Spec:** `docs/superpowers/specs/2026-09-12-army-detail-view-design.md`

## Global Constraints

- Python 3.12; venv runs: `.venv/Scripts/python.exe -m pytest -q`, `.venv/Scripts/python.exe -m ruff check nta_agent tests`. Ruff clean.
- stdlib only; dashboard binds `127.0.0.1`; observability writes never crash the loop.
- `GetPlayerArmys{}` → `{list: AreaArmyInfo[]}`; `AreaArmyInfo{uid,name,index,state,marchSpeed,pawns:[AreaPawnInfo{id,lv,attackSpeed,equip:EquipInfo,...}]}` (pawn order = squad order).
- Names: `pawnText`/`equipText` `name_<id>` `.vi` (fallback `.en`, then `#<id>`). Option descriptions: policy `policyText.desc_<value>`, equip `equipText.effect_<value>`, pawn `""`.
- Resource labels (verified from `ui.json`): cereal="L.Thực", timber="Gỗ", stone="Đá", iron="Sắt", gold="Vàng", exp_book="Sách EXP", up_scroll="Quyển Trục", fixator="Máy Cố Định". No "Thể lực"/stamina.
- Army fetch is a network request → throttled (`armies_every`, default 6) + guarded.

---

### Task 1: army view (`armies.py`)

**Files:**
- Create: `nta_agent/execution/armies.py`
- Test: `tests/test_armies.py`

**Interfaces:**
- Produces: `STATE_LABELS: dict[int,str]`; `army_view(armys: list[dict], config) -> list[dict]` with rows `{uid, name, index, state, state_label, march_speed, pawns:[{uid, id, name, lv, attack_speed, equip_name}]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_armies.py
from nta_agent.execution.armies import army_view


class FakeConfig:
    def __init__(self):
        self._t = {"pawnText": {"name_3101": {"vi": "Lính Trường Thương"}},
                   "equipText": {"name_6001": {"vi": "Kiếm Sắt"}}}

    def table(self, name):
        return self._t.get(name, {})


def test_army_view_orders_pawns_and_resolves_names():
    armys = [{
        "uid": "a1", "name": "Đội 1", "index": 109726, "state": 1, "marchSpeed": 120,
        "pawns": [
            {"uid": "p1", "id": 3101, "lv": 2, "attackSpeed": 6, "equip": {"id": 6001}},
            {"uid": "p2", "id": 3101, "lv": 1, "attackSpeed": 6, "equip": None},
        ],
    }]
    rows = army_view(armys, FakeConfig())
    assert len(rows) == 1
    r = rows[0]
    assert r["uid"] == "a1" and r["name"] == "Đội 1" and r["index"] == 109726
    assert r["state"] == 1 and r["state_label"] == "hành quân" and r["march_speed"] == 120
    assert r["pawns"] == [
        {"uid": "p1", "id": 3101, "name": "Lính Trường Thương", "lv": 2,
         "attack_speed": 6, "equip_name": "Kiếm Sắt"},
        {"uid": "p2", "id": 3101, "name": "Lính Trường Thương", "lv": 1,
         "attack_speed": 6, "equip_name": ""},
    ]


def test_unknown_state_and_names_fall_back():
    rows = army_view([{"uid": "a", "name": "", "index": 0, "state": 9, "marchSpeed": 0,
                       "pawns": [{"uid": "x", "id": 9999, "lv": 1, "attackSpeed": 5, "equip": {"id": 8888}}]}],
                     FakeConfig())
    assert rows[0]["state_label"] == "9"
    assert rows[0]["pawns"][0]["name"] == "#9999" and rows[0]["pawns"][0]["equip_name"] == "#8888"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_armies.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

```python
# nta_agent/execution/armies.py
"""Build a read-only per-army / per-troop view for the dashboard."""
from __future__ import annotations

STATE_LABELS = {0: "rảnh", 1: "hành quân", 2: "đang đánh"}


def _name(config, table_name: str, id_: int) -> str:
    row = config.table(table_name).get(f"name_{id_}") or {}
    return row.get("vi") or row.get("en") or f"#{id_}"


def army_view(armys: list[dict], config) -> list[dict]:
    rows: list[dict] = []
    for a in armys or []:
        if not isinstance(a, dict):
            continue
        pawns = []
        for p in a.get("pawns") or []:
            equip = p.get("equip") or {}
            eid = equip.get("id") if isinstance(equip, dict) else None
            pawns.append({
                "uid": p.get("uid", ""),
                "id": int(p.get("id", 0) or 0),
                "name": _name(config, "pawnText", int(p.get("id", 0) or 0)),
                "lv": int(p.get("lv", 0) or 0),
                "attack_speed": int(p.get("attackSpeed", 0) or 0),
                "equip_name": _name(config, "equipText", eid) if eid else "",
            })
        state = int(a.get("state", 0) or 0)
        rows.append({
            "uid": a.get("uid", ""),
            "name": a.get("name", "") or "",
            "index": int(a.get("index", 0) or 0),
            "state": state,
            "state_label": STATE_LABELS.get(state, str(state)),
            "march_speed": int(a.get("marchSpeed", 0) or 0),
            "pawns": pawns,
        })
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_armies.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/armies.py tests/test_armies.py
git commit -m "execution: read-only army/squad view"
```

---

### Task 2: Actions — get_player_armys

**Files:**
- Modify: `nta_agent/execution/actions.py`
- Test: `tests/test_actions_armies.py`

**Interfaces:**
- Produces on `Actions`: `get_player_armys() -> list[dict]` — `game/HD_GetPlayerArmys{}` → `reply.get("list", []) or []`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_actions_armies.py
from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self, reply):
        self.state = GameState(source="api")
        self._reply = reply
        self.sent = []

    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params))
        return self._reply


def test_get_player_armys():
    s = FakeSession({"list": [{"uid": "a1", "name": "Đội 1"}]})
    out = Actions(s).get_player_armys()
    assert s.sent[0] == ("game/HD_GetPlayerArmys", {})
    assert out == [{"uid": "a1", "name": "Đội 1"}]


def test_get_player_armys_empty():
    assert Actions(FakeSession({})).get_player_armys() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_actions_armies.py -q`
Expected: FAIL — method missing.

- [ ] **Step 3: Write minimal implementation** — add to `nta_agent/execution/actions.py` after `change_pawn_equip`:

```python
    # ---- army reads ----------------------------------------------------- #
    def get_player_armys(self) -> list[dict]:
        """All of the player's armies with their pawns (GAME_HD_GetPlayerArmys)."""
        reply = self.session.request("game/HD_GetPlayerArmys", {})
        return reply.get("list", []) or []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_actions_armies.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/actions.py tests/test_actions_armies.py
git commit -m "execution: get_player_armys action"
```

---

### Task 3: RuntimeConfig — armies_path

**Files:**
- Modify: `nta_agent/runtime/config.py`
- Test: `tests/test_runtime_config.py` (extend)

**Interfaces:**
- Produces on `RuntimeConfig`: `armies_path` (`log_dir/"armies.json"`).

- [ ] **Step 1: Write the failing test** — append to `tests/test_runtime_config.py`:

```python
def test_armies_path():
    cfg = RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": "/l"})
    assert cfg.armies_path == Path("/l/armies.json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runtime_config.py::test_armies_path -q`
Expected: FAIL — attribute missing.

- [ ] **Step 3: Write minimal implementation** — add to `RuntimeConfig` after `equipment_path`:

```python
    @property
    def armies_path(self) -> Path:
        return self.log_dir / "armies.json"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runtime_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/runtime/config.py tests/test_runtime_config.py
git commit -m "runtime: armies_path on RuntimeConfig"
```

---

### Task 4: decisions.py — per-option descriptions

**Files:**
- Modify: `nta_agent/execution/decisions.py`
- Modify: `tests/test_decisions.py` (update expectations to include `desc`)

**Interfaces:**
- Produces: each option dict from `pending_decisions` gains `"desc"`: policy → `policyText["desc_<value>"].vi`, equip → `equipText["effect_<value>"].vi`, pawn → `""`. Fallback `""`.

- [ ] **Step 1: Update the test to expect `desc`** — in `tests/test_decisions.py`:

Extend `FakeConfig._t` with a policy desc and equip effect:

```python
            "policyText": {"name_1001": {"vi": "Ngũ Cốc Phong Đăng"},
                           "desc_1001": {"vi": "Sản lượng cơ bản mỗi giờ tăng {0}"}},
            "equipText": {"effect_6001": {"vi": "HP +100"}},
```

Update `test_pending_pawn_decision_with_names` options to include `"desc": ""`:

```python
    assert d.options == [
        {"ceri_id": 5, "value": 3101, "name": "Lính Trường Thương", "desc": ""},
        {"ceri_id": 6, "value": 3102, "name": "Lính Trường Mâu", "desc": ""},
    ]
```

Add a policy-desc assertion in `test_policy_track_and_unknown_value_fallback`:

```python
    assert ds[0].options[0]["desc"] == "Sản lượng cơ bản mỗi giờ tăng {0}"
    assert ds[0].options[1]["desc"] == ""  # unknown ceri id -> no desc
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_decisions.py -q`
Expected: FAIL — options lack `desc`.

- [ ] **Step 3: Write minimal implementation** — in `nta_agent/execution/decisions.py`, add a helper and include `desc` in each option.

Add after `_name`:

```python
def _desc(config, text_name: str, value: int) -> str:
    if text_name == "policyText":
        key = f"desc_{value}"
    elif text_name == "equipText":
        key = f"effect_{value}"
    else:
        return ""
    row = config.table(text_name).get(key) or {}
    return row.get("vi") or row.get("en") or ""
```

In the option-building loop, add `desc` (value falsy → ""):

```python
            for cid in select_ids:
                value = (ceri.get(cid) or {}).get("value", 0)
                name = _name(text_table, value) if value else f"#{cid}"
                desc = _desc(config, text_name, value) if value else ""
                options.append({"ceri_id": cid, "value": value, "name": name, "desc": desc})
```

(Note: `_name` takes the text table dict; `_desc` takes `config` + the table name. `text_name` is already in scope from the `TRACKS` unpack.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_decisions.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/decisions.py tests/test_decisions.py
git commit -m "execution: decision options carry in-game descriptions"
```

---

### Task 5: DecisionService — throttled army fetch → armies.json

**Files:**
- Modify: `nta_agent/runtime/decision_service.py`
- Test: `tests/test_decision_service_armies.py`

**Interfaces:**
- Consumes: `army_view` (Task 1), `Actions.get_player_armys` (Task 2), `RuntimeConfig.armies_path` (Task 3).
- Produces: `DecisionService.__init__` gains `armies_every: int = 6`; `tick(state)` fetches armies on the throttle and writes `armies.json` (guarded). Other writes/commands unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_decision_service_armies.py
import json

from nta_agent.runtime.config import RuntimeConfig
from nta_agent.runtime.decision_service import DecisionService
from nta_agent.state.schema import GameState
from tests.test_armies import FakeConfig


class FakeActions:
    def __init__(self):
        self.armys_calls = 0

    def get_player_armys(self):
        self.armys_calls += 1
        return [{"uid": "a1", "name": "Đội 1", "index": 5, "state": 0, "marchSpeed": 100,
                 "pawns": [{"uid": "p1", "id": 3101, "lv": 1, "attackSpeed": 6, "equip": {"id": 6001}}]}]


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def _state():
    st = GameState(source="api")
    st.raw = {"player": {"configPawnMap": {}, "equips": [], "pawnSlots": {}, "policySlots": {}, "equipSlots": {}}}
    return st


def test_armies_fetched_on_throttle(tmp_path):
    cfg = _cfg(tmp_path)
    act = FakeActions()
    svc = DecisionService(act, FakeConfig(), cfg, armies_every=2)
    svc.tick(_state())   # first tick -> fetch
    rows = json.loads(cfg.armies_path.read_text(encoding="utf-8"))
    assert rows[0]["name"] == "Đội 1" and rows[0]["pawns"][0]["name"] == "Lính Trường Thương"
    assert act.armys_calls == 1
    svc.tick(_state())   # throttled: no fetch
    assert act.armys_calls == 1


def test_army_fetch_failure_is_swallowed(tmp_path):
    cfg = _cfg(tmp_path)

    class Boom:
        def get_player_armys(self):
            raise RuntimeError("net down")

    DecisionService(Boom(), FakeConfig(), cfg, armies_every=1).tick(_state())  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_decision_service_armies.py -q`
Expected: FAIL — `armies_every` / armies.json not implemented.

- [ ] **Step 3: Write minimal implementation** — in `nta_agent/runtime/decision_service.py`:

Add the import:

```python
from nta_agent.execution.armies import army_view
```

Add `armies_every` + counter to `__init__`:

```python
    def __init__(self, actions, config, cfg, on_event=None, armies_every=6):
        self.actions = actions
        self.config = config
        self.cfg = cfg
        self._on_event = on_event or (lambda *a: None)
        self.armies_every = armies_every
        self._armies_counter = 0
```

Add a writer:

```python
    def _write_armies(self) -> None:
        data = army_view(self.actions.get_player_armys(), self.config)
        path = Path(self.cfg.armies_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
```

In `tick`, after the equipment write (still before command processing), add the throttled army fetch:

```python
        if self._armies_counter <= 0:
            self._armies_counter = self.armies_every - 1
            try:
                self._write_armies()
            except Exception as e:  # network call — never kill the loop
                sys.stderr.write(f"[armies] fetch failed: {e}\n")
        else:
            self._armies_counter -= 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_decision_service_armies.py tests/test_decision_service.py tests/test_decision_service_equip.py -q`
Expected: PASS (new army tests + existing decision-service tests still green).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/runtime/decision_service.py tests/test_decision_service_armies.py
git commit -m "runtime: DecisionService throttled army fetch -> armies.json"
```

---

### Task 6: Dashboard — /api/armies + "Đội quân" section + polish

**Files:**
- Modify: `nta_agent/dashboard/server.py`
- Modify: `nta_agent/dashboard/page.py`
- Test: `tests/test_dashboard_armies.py`, `tests/test_dashboard_page.py` (extend)

**Interfaces:**
- Consumes: `read_json_array` (existing), `RuntimeConfig.armies_path` (Task 3).
- Produces: `GET /api/armies` → the armies array; `INDEX_HTML` gains the "Đội quân" section, corrected resource labels, and rendered option descriptions.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dashboard_armies.py
import json
import threading
import urllib.request

from nta_agent.dashboard.server import serve
from nta_agent.runtime.config import RuntimeConfig


def _cfg(tmp_path):
    return RuntimeConfig.from_env({"NTA_DISTINCT_ID": "x", "NTA_LOG_DIR": str(tmp_path)})


def test_get_armies(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.armies_path.write_text(json.dumps([{"uid": "a1", "name": "Đội 1", "pawns": []}]))
    srv = serve(cfg, 0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/armies", timeout=5) as r:
            data = json.loads(r.read())
        assert data[0]["name"] == "Đội 1"
    finally:
        srv.shutdown()
```

Append to `tests/test_dashboard_page.py`:

```python
def test_index_html_has_army_section_and_labels():
    from nta_agent.dashboard.page import INDEX_HTML
    assert "/api/armies" in INDEX_HTML
    assert "Đội quân" in INDEX_HTML
    assert "Sách EXP" in INDEX_HTML          # corrected resource label
    assert "Thể lực" not in INDEX_HTML       # dropped
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_armies.py tests/test_dashboard_page.py -q`
Expected: FAIL — no /api/armies; labels/section absent.

- [ ] **Step 3: Implement**

In `nta_agent/dashboard/server.py` `do_GET`, add before the 404 branch:

```python
        elif parsed.path == "/api/armies":
            self._json(200, read_json_array(cfg.armies_path))
```

In `nta_agent/dashboard/page.py`:

(a) Replace the `const RES=[...]` line with the corrected labels:

```javascript
const RES=[["cereal","L.Thực"],["timber","Gỗ"],["stone","Đá"],["iron","Sắt"],["gold","Vàng"],["exp_book","Sách EXP"],["up_scroll","Quyển Trục"],["fixator","Máy Cố Định"]];
```

(b) Update `decCard` to render each option's `desc` (muted line):

```javascript
function decCard(d){
 const opts=(d.options||[]).map(o=>`<button data-a=select data-t="${d.track}" data-lv="${d.lv}" data-id="${o.ceri_id}">${o.name}</button>${o.desc?` <span class=muted>${o.desc}</span>`:""}`).join("<br>");
 const reroll=`<button data-a=reroll data-t="${d.track}" data-lv="${d.lv}">Làm mới${d.reset_count?(" ("+d.reset_count+")"):" (free)"}</button>`;
 return `<div style="margin:6px 0"><span class=muted>${d.track} · Lv${d.lv}</span><br>${opts}<br>${reroll}</div>`;
}
```

(c) Add the "Đội quân" card to `<main>` after the misc card (before decisions):

```html
 <div class="card full"><h2>Đội quân</h2><div id="armies"><span class="muted">—</span></div></div>
```

(d) Add `renderArmies` JS (near `renderEquipment`):

```javascript
function armyCard(a){
 const ps=(a.pawns||[]).map((p,i)=>`<li>${i+1}. ${p.name} <b>Lv${p.lv}</b> · tốc ${p.attack_speed} · ${p.equip_name||"—"}</li>`).join("");
 return `<div style="margin:8px 0"><b>${a.name||a.uid}</b> <span class=muted>· ${a.state_label} · tốc hành quân ${a.march_speed}</span><ul>${ps||"<li class=muted>trống</li>"}</ul></div>`;
}
async function renderArmies(){
 const as=await j("/api/armies")||[];
 const box=document.getElementById("armies");
 box.innerHTML=as.length?as.map(armyCard).join(""):"<span class=muted>—</span>";
}
```

Add `renderArmies();` inside `refresh()` (next to `renderDecisions();`/`renderEquipment();`).

(e) Light restyle — in the `<style>` block, add an accent + card polish:

```css
 .card h2{color:#58a6ff}
 .card{transition:border-color .15s}.card:hover{border-color:#3a4450}
 button{background:#21262d;color:#e6e6e6;border:1px solid #3a4450;border-radius:6px;padding:4px 10px;margin:2px;cursor:pointer}
 button:hover:not(:disabled){border-color:#58a6ff}button:disabled{opacity:.5;cursor:default}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_armies.py tests/test_dashboard_page.py -q`
Expected: PASS.

- [ ] **Step 5: Full verification + commit**

Run: `.venv/Scripts/python.exe -m pytest -q` (all pass) and `.venv/Scripts/python.exe -m ruff check nta_agent tests` (clean).

```bash
git add nta_agent/dashboard/server.py nta_agent/dashboard/page.py tests/test_dashboard_armies.py tests/test_dashboard_page.py
git commit -m "dashboard: Đội quân section + correct resource labels + option descriptions + restyle"
```

---

## Self-Review

**Spec coverage:**
- §4.1 armies.py → Task 1. §4.2 get_player_armys → Task 2. §4.3 decisions desc → Task 4. §4.4 armies_path → Task 3. §4.5 throttled fetch → Task 5. §4.6 dashboard view + polish → Task 6. ✓
- §2 GetPlayerArmys shape, resource labels, option descs → Tasks 1/4/6 (verbatim labels). ✓
- §6 error handling: guarded army write + fetch failure swallowed (Task 5), missing config fallbacks (Task 1/4), missing armies.json → [] (Task 6). ✓
- §7 testing: armies/actions/decisions/decision_service/dashboard all covered. ✓
- §8 out of scope (A2 editing, sim-advisor, pawn skill desc) — not in any task. ✓

**Placeholder scan:** No TBD/TODO; every code step complete.

**Type consistency:** `army_view` row keys (Task 1) → `armies.json` (Task 5) → `/api/armies` (Task 6) → page `a.name/state_label/march_speed/pawns[].name/lv/attack_speed/equip_name` (Task 6). `get_player_armys() -> list` (Task 2) consumed by `_write_armies` (Task 5). `RuntimeConfig.armies_path` (Task 3) used in Tasks 5/6. Decision option now `{ceri_id,value,name,desc}` (Task 4) rendered by `decCard` (Task 6). `DecisionService(..., armies_every=6)` (Task 5) — existing callers (runner) use defaults, unaffected.
