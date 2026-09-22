# Brain học-từ-thất-bại — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho brain học từ kết cục xấu (lính chết, cạn tài nguyên, mục tiêu kẹt) và lưu hướng giải quyết có-bằng-chứng để tái dùng.

**Architecture:** Hands (deterministic, 0 token) ghi thất bại thật vào ledger + chạy counterfactual sim; digest đưa cho brain; brain chưng cất lesson có-evidence, tự áp lever an toàn / việc lớn → advice. Brain KHÔNG gọi tool (Cách A).

**Tech Stack:** Python 3.12 (venv `.venv`), pytest, ruff; Node ≥18 sidecar (`tools/battlesim/`, JSON-RPC qua `SimBridge`).

**Spec:** [docs/superpowers/specs/2026-09-22-brain-learn-from-failure-design.md](../specs/2026-09-22-brain-learn-from-failure-design.md)

## Global Constraints

- **Không bao giờ chết loop:** mọi hook/observer bọc try/except; thiếu Node/engine → bỏ enrichment, vẫn ghi loss.
- **Chống bịa (load-bearing):** lesson bắt buộc có `evidence` = `event_id` tồn tại trong ledger; không có ⇒ guard loại.
- **Brain KHÔNG tự gọi tool/API.** Hands chạy replay/counterfactual, brain chỉ đọc digest.
- **Không đụng** `occupy.max_loss`, `build.order/skip`, `army.group/roles` (của người) — lesson chạm chúng ⇒ chuyển thành advice.
- Ghi file **atomic** (tmp + `os.replace`), theo mẫu `brain_advice`/`composition_status`.
- TDD: test trước, chạy fail, impl tối thiểu, chạy pass, commit. Lint sạch: `.venv/Scripts/python.exe -m ruff check nta_agent tests tools`.
- Commit kết mỗi task với `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Chạy JS test: `node --test --test-force-exit tools/battlesim/test/<file>.test.js`.

## File Structure

**Mới:**
- `nta_agent/execution/ledger.py` — FailureLedger + FailureEvent (thuần, bounded, atomic).
- `nta_agent/execution/counterfactual.py` — summarize_record / best_counterfactual_order / AoE (gọi SimBridge, fallback None).
- `nta_agent/execution/loss_observer.py` — LossObserver: injury-delta → record → ledger (service trong loop).
- `nta_agent/brain/lessons.py` — Lesson + LessonStore (Inc 2).
- `tools/battlesim/record-summary.js` — logic "record → events/summary" dùng chung.

**Sửa:**
- `nta_agent/runtime/config.py` — `failures_path`, `lessons_path`, hằng số cửa sổ/cap.
- `nta_agent/brain/digest.py` — `failures`, `res_pressure`, `lessons`.
- `nta_agent/brain/guard.py` — `sanitize_lessons`.
- `nta_agent/brain/llm.py` — prompt: failures/counterfactual + lessons schema + luật evidence.
- `nta_agent/runtime/brain_service.py` — nạp ledger/lessons, persist lessons, `_urgent` on new loss.
- `nta_agent/runtime/runner.py` — khởi tạo ledger/observer, wire `ledger` sink cho rule + `run_services`.
- `tools/battlesim/server.js` — method `replay`, `counterfactual`.
- `tools/battlesim/replay-log.js` — dùng `record-summary.js`.
- `nta_agent/dashboard/` — panel Failures + Lessons (Inc 2).

---

# INCREMENT 1 — Ledger + Counterfactual + Digest

## Task 1: FailureLedger + config paths

**Files:**
- Create: `nta_agent/execution/ledger.py`
- Modify: `nta_agent/runtime/config.py` (add 2 properties + 3 fields)
- Test: `tests/test_ledger.py`

**Interfaces:**
- Produces: `FailureEvent(id,ts,kind,context)`; `FailureLedger(path,cap=100)` với `.record(kind,context)->str`, `.recent(n=10,kind=None)->list[FailureEvent]`, `.has(event_id)->bool`, `.aggregate_res(window_s)->dict[str,int]`, `.all()->list[FailureEvent]`.
- `RuntimeConfig.failures_path`, `.lessons_path` (properties → `log_dir/…json`).

- [ ] **Step 1: Write the failing test** — `tests/test_ledger.py`

```python
import time
from nta_agent.execution.ledger import FailureLedger

def test_record_returns_id_and_persists(tmp_path):
    p = tmp_path / "failures.json"
    led = FailureLedger(p, cap=100)
    eid = led.record("battle_loss", {"cell": 79542, "self_dead": 1})
    assert eid and led.has(eid)
    assert not led.has("nope")
    # reload from disk sees it
    led2 = FailureLedger(p, cap=100)
    assert led2.has(eid)
    assert led2.recent(5)[0].kind == "battle_loss"

def test_cap_keeps_most_recent(tmp_path):
    led = FailureLedger(tmp_path / "f.json", cap=3)
    ids = [led.record("res_depletion", {"rule": "recruit", "resource": "cereal"}) for _ in range(5)]
    assert len(led.all()) == 3
    assert led.has(ids[-1]) and not led.has(ids[0])

def test_recent_filters_by_kind(tmp_path):
    led = FailureLedger(tmp_path / "f.json")
    led.record("battle_loss", {"self_dead": 2})
    led.record("res_depletion", {"rule": "build"})
    assert len(led.recent(10, kind="battle_loss")) == 1

def test_aggregate_res_windows(tmp_path):
    led = FailureLedger(tmp_path / "f.json")
    led.record("res_depletion", {"rule": "recruit", "resource": "cereal"})
    led.record("res_depletion", {"rule": "forge", "resource": "cereal"})
    led.record("res_depletion", {"rule": "build", "resource": "stone"})
    agg = led.aggregate_res(window_s=3600)
    assert agg == {"cereal": 2, "stone": 1}
    assert led.aggregate_res(window_s=0) == {}   # nothing within a 0s window
```

- [ ] **Step 2: Run to verify fail** — `.venv/Scripts/python.exe -m pytest tests/test_ledger.py -q` → FAIL (no module).

- [ ] **Step 3: Implement** — `nta_agent/execution/ledger.py`

```python
"""Deterministic, bounded ledger of real failures for the brain to learn from."""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class FailureEvent:
    id: str
    ts: float
    kind: str            # "battle_loss" | "res_depletion" | "stuck_goal"
    context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FailureEvent":
        return cls(id=str(d.get("id", "")), ts=float(d.get("ts", 0) or 0),
                   kind=str(d.get("kind", "")), context=dict(d.get("context") or {}))


class FailureLedger:
    def __init__(self, path, cap: int = 100) -> None:
        self.path = Path(path)
        self.cap = int(cap)
        self._seq = 0
        self._events: list[FailureEvent] = self._load()

    def _load(self) -> list[FailureEvent]:
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [FailureEvent.from_dict(r) for r in rows if isinstance(r, dict)]

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps([e.to_dict() for e in self._events],
                                      ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass  # never break the loop over ledger I/O

    def record(self, kind: str, context: dict) -> str:
        self._seq += 1
        eid = f"{int(time.time() * 1000)}-{self._seq}"
        self._events.append(FailureEvent(id=eid, ts=time.time(), kind=str(kind),
                                         context=dict(context or {})))
        if len(self._events) > self.cap:
            self._events = self._events[-self.cap:]
        self._save()
        return eid

    def all(self) -> list[FailureEvent]:
        return list(self._events)

    def recent(self, n: int = 10, kind: str | None = None) -> list[FailureEvent]:
        evs = [e for e in self._events if kind is None or e.kind == kind]
        return list(reversed(evs[-n:]))

    def has(self, event_id: str) -> bool:
        return any(e.id == event_id for e in self._events)

    def aggregate_res(self, window_s: float) -> dict[str, int]:
        cutoff = time.time() - float(window_s)
        out: dict[str, int] = {}
        for e in self._events:
            if e.kind == "res_depletion" and e.ts >= cutoff:
                r = e.context.get("resource")
                if r:
                    out[str(r)] = out.get(str(r), 0) + 1
        return out
```

- [ ] **Step 4: Add config paths** — `nta_agent/runtime/config.py` (sau `composition_status_path`):

```python
    @property
    def failures_path(self) -> Path:
        return self.log_dir / "failures.json"

    @property
    def lessons_path(self) -> Path:
        return self.log_dir / "lessons.json"
```
Và trong `@dataclass RuntimeConfig` thân lớp thêm 3 field mặc định:
```python
    res_pressure_window_s: float = 3600.0
    ledger_cap: int = 100
    lessons_cap: int = 50
```

- [ ] **Step 5: Run tests + lint** — `pytest tests/test_ledger.py -q` PASS; `ruff check nta_agent tests`.

- [ ] **Step 6: Commit** — `git add nta_agent/execution/ledger.py nta_agent/runtime/config.py tests/test_ledger.py && git commit -m "feat(brain): failure ledger + config paths"`

---

## Task 2: `record-summary.js` dùng chung + server `replay` method

**Files:**
- Create: `tools/battlesim/record-summary.js`
- Modify: `tools/battlesim/replay-log.js` (dùng module chung), `tools/battlesim/server.js` (method `replay`)
- Test: `tools/battlesim/test/record-summary.test.js`

**Interfaces:**
- Produces (JS): `record-summary.js` export `summarize(record, req, {playerUid}) -> {summary:{self_dead,enemy_dead,frames,is_win}, hits:[{by,by_id,target,target_id,dmg,frame}], enemy_ids:[int], self_ids:[int]}`.
- Sidecar `replay` method: params = `{record, playerUid?}` → kết quả trên.

- [ ] **Step 1: Write failing JS test** — `tools/battlesim/test/record-summary.test.js`. Dùng fixture record 1-tile có thật (đặt tại `tools/battlesim/test/fixtures/onetile-record.json` — trích từ `build/run/battle_record.json` đã có, hoặc từ golden test hiện tại; nếu chưa có, Step 3 tạo fixture từ record thật).

```js
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const { loadEngine } = require("../bundle");
const { installAssets } = require("../assets");
const { summarize } = require("../record-summary");

test("summarize a real 1-tile record: deaths + AoE-capable hits", () => {
  const rec = JSON.parse(fs.readFileSync(
    path.join(__dirname, "fixtures", "onetile-record.json"), "utf8"));
  const record = rec.record || rec;
  const req = loadEngine();
  if (!globalThis.eventCenter) globalThis.eventCenter = { emit(){}, on(){}, off(){}, once(){} };
  if (!globalThis.mc) globalThis.mc = { getModel: () => ({}) };
  installAssets(undefined, req, { playerUid: "1000000000" });
  const out = summarize(record, req, { playerUid: "1000000000" });
  assert.ok(out.summary.frames > 0);
  assert.ok(typeof out.summary.self_dead === "number");
  assert.ok(Array.isArray(out.hits) && out.hits.length > 0);
  assert.ok(out.enemy_ids.length > 0);
});
```

- [ ] **Step 2: Run to verify fail** — `node --test --test-force-exit tools/battlesim/test/record-summary.test.js` → FAIL (no module / no fixture).

- [ ] **Step 3: Extract `summarize` from replay-log.js** — tạo `record-summary.js` chứa lõi vòng replay của `replayLog` (frames setup, wave inject, snapshot, vòng `while` sinh events), trả `{summary, hits, enemy_ids, self_ids}` (camp 1 = enemy, camp 2 = self). Chuẩn hoá field `hit` thêm `by_id` (id pawn của attacker) để phát hiện AoE ở Task 4. Nếu chưa có fixture, ghi ra từ `build/run/battle_record.json` thật (copy vào `test/fixtures/onetile-record.json`).

- [ ] **Step 4: Refactor `replay-log.js`** để `replayLog` gọi `summarize` (giữ CLI + output cũ tương thích: `{events, summary}`), tránh 2 bản logic đọc trận.

- [ ] **Step 5: Add `replay` to server.js**:
```js
const { summarize } = require("./record-summary");
// trong dispatch:
if (method === "replay") {
  const p = params || {};
  return { id, result: summarize(p.record, req, { playerUid: p.playerUid || "1000000000" }) };
}
```
(khởi tạo `req = loadEngine()` + `installAssets` một lần khi server boot — theo mẫu forecast hiện có trong server.js.)

- [ ] **Step 6: Run JS tests** — `node --test --test-force-exit tools/battlesim/test/record-summary.test.js` + `.../server.test.js` PASS.

- [ ] **Step 7: Commit** — `git commit -m "feat(sim): shared record-summary + sidecar replay method"`

---

## Task 3: server `counterfactual` method

**Files:**
- Modify: `tools/battlesim/server.js`, (nếu cần) `tools/battlesim/forecast.js`/`record-replay.js` để lấy quái từ record.
- Test: `tools/battlesim/test/counterfactual.test.js`

**Interfaces:**
- Sidecar `counterfactual` method: params `{record, orders:["tank_first","dps_first","auto"], playerUid?}` → `{by_order:{<order>:{loss:number, self_dead:number}}}`. Loss = % tổn thất phe mình dự đoán khi đội mình xếp theo `order` vs cùng bộ quái của record.

- [ ] **Step 1: Write failing JS test** — `counterfactual.test.js`: nạp fixture 1-tile, gọi `counterfactual`, assert có khoá cho mỗi order + `self_dead` là số; và ít nhất một order ≤ order khác (đội hình khác cho loss khác nhau, hoặc bằng — chỉ assert shape + determinism: gọi 2 lần cùng kết quả).

```js
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const { counterfactual } = require("../counterfactual-core"); // hoặc export từ forecast

test("counterfactual returns a loss per order, deterministically", () => {
  const rec = JSON.parse(fs.readFileSync(
    path.join(__dirname, "fixtures", "onetile-record.json"), "utf8"));
  const orders = ["tank_first", "dps_first", "auto"];
  const a = counterfactual({ record: rec.record || rec, orders, playerUid: "1000000000" });
  const b = counterfactual({ record: rec.record || rec, orders, playerUid: "1000000000" });
  for (const o of orders) {
    assert.ok(o in a.by_order);
    assert.ok(typeof a.by_order[o].self_dead === "number");
  }
  assert.deepStrictEqual(a, b);   // deterministic (seed từ record)
});
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement counterfactual core** — `tools/battlesim/counterfactual-core.js`: từ record tách quái (camp 1 fighters) + đội mình (camp 2, nhóm theo army); với mỗi `order` sắp lại thứ tự army (tank_first = army nhiều melee/tank trước; dps_first = archer trước; auto = giữ nguyên record) rồi chạy `forecast` (đường reinforce đã có) → đọc loss/self_dead. Tái dùng `record-replay.js` để lấy fighters + seed. Export `counterfactual({record, orders, playerUid})`.

- [ ] **Step 4: Wire vào server.js**:
```js
const { counterfactual } = require("./counterfactual-core");
if (method === "counterfactual") return { id, result: counterfactual(params || {}) };
```

- [ ] **Step 5: Run JS tests** PASS.

- [ ] **Step 6: Commit** — `git commit -m "feat(sim): counterfactual army-order forecast method"`

---

## Task 4: Python counterfactual bridge

**Files:**
- Create: `nta_agent/execution/counterfactual.py`
- Modify: `nta_agent/execution/predictors/sim_bridge.py` (thêm `replay`, `counterfactual` methods)
- Test: `tests/test_counterfactual.py`

**Interfaces:**
- `SimBridge.replay(record)->dict`, `SimBridge.counterfactual(record, orders)->dict` (như `forecast`, raise `SimUnavailable`).
- `counterfactual.py`: `summarize_record(bridge, record)->dict|None`; `detect_aoe(hits)->bool`; `best_counterfactual_order(bridge, record)->dict|None` (`{"best_order":str,"self_dead":int}` hoặc None).

- [ ] **Step 1: Write failing test** — `tests/test_counterfactual.py` (dùng FAKE bridge, không cần Node):

```python
from nta_agent.execution.counterfactual import detect_aoe, best_counterfactual_order, summarize_record

class FakeBridge:
    def __init__(self, replay=None, cf=None, fail=False):
        self._replay, self._cf, self._fail = replay, cf, fail
    def replay(self, record):
        if self._fail: from nta_agent.execution.predictors.sim_bridge import SimUnavailable; raise SimUnavailable("x")
        return self._replay
    def counterfactual(self, record, orders):
        if self._fail: from nta_agent.execution.predictors.sim_bridge import SimUnavailable; raise SimUnavailable("x")
        return self._cf

def test_detect_aoe_true_when_one_attacker_hits_many_same_frame():
    hits = [{"by": "q1", "target": "a", "frame": 10}, {"by": "q1", "target": "b", "frame": 10}]
    assert detect_aoe(hits) is True

def test_detect_aoe_false_for_single_target():
    assert detect_aoe([{"by": "q1", "target": "a", "frame": 10},
                       {"by": "q1", "target": "a", "frame": 12}]) is False

def test_best_counterfactual_picks_lowest_self_dead():
    cf = {"by_order": {"tank_first": {"self_dead": 0}, "dps_first": {"self_dead": 1}, "auto": {"self_dead": 1}}}
    out = best_counterfactual_order(FakeBridge(cf=cf), {"any": "record"})
    assert out == {"best_order": "tank_first", "self_dead": 0}

def test_counterfactual_none_on_sim_unavailable():
    assert best_counterfactual_order(FakeBridge(fail=True), {}) is None
    assert summarize_record(FakeBridge(fail=True), {}) is None
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Add bridge methods** — `sim_bridge.py`:
```python
    def replay(self, record: dict) -> dict:
        r = self._send("replay", {"record": record})
        if not isinstance(r, dict):
            raise SimUnavailable("sidecar returned no result")
        return r

    def counterfactual(self, record: dict, orders: list[str]) -> dict:
        r = self._send("counterfactual", {"record": record, "orders": list(orders)})
        if not isinstance(r, dict):
            raise SimUnavailable("sidecar returned no result")
        return r
```

- [ ] **Step 4: Implement** — `nta_agent/execution/counterfactual.py`:
```python
"""Ground failures in the engine: summarize a lost battle + test alternate orders."""
from __future__ import annotations

from nta_agent.execution.predictors.sim_bridge import SimUnavailable

_ORDERS = ["tank_first", "dps_first", "auto"]


def summarize_record(bridge, record) -> dict | None:
    try:
        out = bridge.replay(record)
    except SimUnavailable:
        return None
    if not isinstance(out, dict):
        return None
    out["aoe"] = detect_aoe(out.get("hits") or [])
    return out


def detect_aoe(hits) -> bool:
    seen: dict = {}
    for h in hits or []:
        key = (h.get("by"), h.get("frame"))
        seen.setdefault(key, set()).add(h.get("target"))
    return any(len(t) > 1 for t in seen.values())


def best_counterfactual_order(bridge, record) -> dict | None:
    try:
        out = bridge.counterfactual(record, _ORDERS)
    except SimUnavailable:
        return None
    by = (out or {}).get("by_order") or {}
    if not by:
        return None
    best = min(by.items(), key=lambda kv: kv[1].get("self_dead", 10 ** 9))
    return {"best_order": best[0], "self_dead": int(best[1].get("self_dead", 0))}
```

- [ ] **Step 5: Run tests + lint** PASS.

- [ ] **Step 6: Commit** — `git commit -m "feat(brain): counterfactual bridge (summarize + best order)"`

---

## Task 5: LossObserver + res_depletion/stuck sinks + runner wiring

**Files:**
- Create: `nta_agent/execution/loss_observer.py`
- Modify: `nta_agent/runtime/runner.py` (init ledger/observer, wire `ledger` sink cho rule, call trong `run_services`), `nta_agent/execution/heuristics.py` (rule báo res_depletion trên 500012)
- Test: `tests/test_loss_observer.py`

**Interfaces:**
- Consumes: `FailureLedger` (Task 1), `summarize_record`/`best_counterfactual_order` (Task 4), `Actions.get_battle_records_list/get_battle_record`.
- `LossObserver(actions, ledger, bridge, cfg, player_uid, on_event=None)` với `.tick(state)`; nội bộ giữ `_last_injured`.

- [ ] **Step 1: Write failing test** — fake actions/state; injury tăng → observer ghi battle_loss có counterfactual:

```python
from nta_agent.execution.ledger import FailureLedger
from nta_agent.execution.loss_observer import LossObserver

class St:
    def __init__(self, injured, records=None):
        self.raw = {"player": {"injuryPawns": [{}] * injured}}
        self.main_city_index = 79542

class Acts:
    def __init__(self, records, record):
        self._records, self._record = records, record
    def get_battle_records_list(self): return self._records
    def get_battle_record(self, uid): return self._record

class Bridge:
    def replay(self, record): return {"summary": {"self_dead": 1}, "hits": [], "enemy_ids": [4116]}
    def counterfactual(self, record, orders): return {"by_order": {"tank_first": {"self_dead": 0}, "auto": {"self_dead": 1}}}

def test_injury_rise_records_battle_loss_with_counterfactual(tmp_path):
    led = FailureLedger(tmp_path / "f.json")
    acts = Acts([{"uid": "b1", "endTime": 2}, {"uid": "b0", "endTime": 1}], {"frames": [1], "uid": "b1"})
    obs = LossObserver(acts, led, Bridge(), cfg=_cfg(), player_uid="1000000000")
    obs.tick(St(injured=0))          # baseline
    obs.tick(St(injured=2))          # +2 dead -> record a loss
    ev = led.recent(1, kind="battle_loss")
    assert ev and ev[0].context["counterfactual"]["best_order"] == "tank_first"
    assert ev[0].context["enemy_ids"] == [4116]

def test_no_loss_when_injury_flat(tmp_path):
    led = FailureLedger(tmp_path / "f.json")
    obs = LossObserver(Acts([], {}), led, None, cfg=_cfg(), player_uid="x")
    obs.tick(St(injured=1)); obs.tick(St(injured=1))
    assert led.all() == []
```
(`_cfg()` = một object nhỏ có `res_pressure_window_s`; hoặc dùng `types.SimpleNamespace`.)

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement** — `nta_agent/execution/loss_observer.py`:
```python
"""Hands-side observer: detect real troop losses and record them (Cách A)."""
from __future__ import annotations

from nta_agent.execution.counterfactual import best_counterfactual_order, summarize_record


class LossObserver:
    def __init__(self, actions, ledger, bridge, cfg, player_uid, on_event=None):
        self.actions = actions
        self.ledger = ledger
        self.bridge = bridge
        self.cfg = cfg
        self.player_uid = str(player_uid)
        self._on_event = on_event or (lambda *a: None)
        self._last_injured: int | None = None

    def tick(self, state) -> None:
        player = (getattr(state, "raw", None) or {}).get("player") or {}
        injured = len(player.get("injuryPawns") or [])
        prev = self._last_injured
        self._last_injured = injured
        if prev is None or injured <= prev:
            return
        try:
            self._record_latest_battle(injured - prev)
        except Exception as e:  # never break the loop
            self._on_event("loss_observer_error", {"err": str(e)})

    def _record_latest_battle(self, new_dead: int) -> None:
        ctx = {"self_dead": new_dead}
        records = self.actions.get_battle_records_list() or []
        if records:
            latest = max(records, key=lambda r: r.get("endTime", 0) or 0)
            ctx["cell"] = latest.get("index")
            record = self.actions.get_battle_record(str(latest.get("uid")))
            if record and record.get("frames") and self.bridge is not None:
                summ = summarize_record(self.bridge, record)
                if summ:
                    ctx["self_dead"] = summ.get("summary", {}).get("self_dead", new_dead)
                    ctx["enemy_ids"] = summ.get("enemy_ids", [])
                    ctx["aoe"] = bool(summ.get("aoe"))
                cf = best_counterfactual_order(self.bridge, record)
                if cf:
                    ctx["counterfactual"] = cf
        eid = self.ledger.record("battle_loss", ctx)
        self._on_event("battle_loss", {"id": eid, **ctx})
```

- [ ] **Step 4: res_depletion sink on rules** — trong `heuristics.py`, các rule dùng backoff 500012 (Recruit, BuildOrder, Forge, Leveling) thêm thuộc tính optional `ledger=None`; tại nhánh bắt `ecode.500012` gọi:
```python
if getattr(self, "ledger", None) is not None:
    self.ledger.record("res_depletion", {"rule": self.name, "resource": <res|None>})
```
(`<res>` suy từ context nếu biết, else None — vẫn ghi rule.)

- [ ] **Step 5: Wire runner** — trong `runner.py`:
  - khởi tạo `ledger = FailureLedger(cfg.failures_path, cap=cfg.ledger_cap)`, `bridge = get_bridge()`, `observer = LossObserver(agent.actions, ledger, bridge, cfg, session.state.user.uid, on_event=on_event)`.
  - gán `rule.ledger = ledger` cho các rule ở Step 4 (giống pattern gán `locked_source`).
  - stuck_goal: khi `_write_comp_status` nhận `blocked` → `ledger.record("stuck_goal", {"goal":"composition","detail":issues})` (dedup: chỉ ghi khi chuyển trạng thái sang blocked).
  - thêm `observer` vào `run_services` (chạy trước brain): sửa chữ ký `run_services(state, cfg, service, brain, forts, safe, observer=None)` và `if observer: safe(observer.tick, state)` đặt TRƯỚC `brain.tick`.

- [ ] **Step 6: Run tests + lint** PASS (test cả `run_services` observer-before-brain nếu có test runner).

- [ ] **Step 7: Commit** — `git commit -m "feat(brain): loss observer + res/stuck ledger sinks + wiring"`

---

## Task 6: Digest failures + prompt (brain thấy sự thật)

**Files:**
- Modify: `nta_agent/brain/digest.py`, `nta_agent/brain/llm.py`, `nta_agent/runtime/brain_service.py`
- Test: `tests/test_digest_failures.py`, mở rộng `tests/test_brain_service*.py`

**Interfaces:**
- `digest(state, profile, armies, territory, decisions, failures=None, res_pressure=None, lessons=None)` — thêm 3 tham số optional; output thêm khoá tương ứng khi có.

- [ ] **Step 1: Write failing test** — `tests/test_digest_failures.py`:
```python
from nta_agent.brain.digest import digest
from nta_agent.execution.ledger import FailureEvent

class P:  # minimal profile
    army={}; occupy={}; build={}; revive={}; logistics={}; notes=[]

class S:
    resources=type("R",(),{k:0 for k in ("cereal","timber","stone","iron","gold","stamina","exp_book","up_scroll","fixator")})()
    main_city_index=1; raw={"player":{}}

def test_digest_includes_failures_and_res_pressure():
    fails = [FailureEvent("e1", 1.0, "battle_loss",
             {"cell": 5, "self_dead": 1, "counterfactual": {"best_order": "tank_first", "self_dead": 0}})]
    dg = digest(S(), P(), armies=[], failures=fails, res_pressure={"cereal": 4})
    assert dg["failures"][0]["id"] == "e1"
    assert dg["failures"][0]["counterfactual"]["best_order"] == "tank_first"
    assert dg["res_pressure"] == {"cereal": 4}
```

- [ ] **Step 2: Run to verify fail.**

- [ ] **Step 3: Implement digest** — thêm tham số + build khoá `failures` (compact: id, kind, cell/rule, self_dead, counterfactual.best_order, aoe), `res_pressure`, `lessons` (nếu truyền). Giữ tương thích ngược (mặc định None → không thêm khoá).

- [ ] **Step 4: brain_service** — nạp `FailureLedger(cfg.failures_path)` (đọc-only view), truyền `failures=ledger.recent(8)`, `res_pressure=ledger.aggregate_res(cfg.res_pressure_window_s)` vào `digest(...)`. Thêm `_urgent`: fire nếu có battle_loss mới kể từ lần gọi trước (so `ledger.recent(1)` id) hoặc `res_pressure` vượt ngưỡng (vd tổng ≥ 5).

- [ ] **Step 5: Prompt** — `llm.py` `_SYSTEM` thêm: "digest.failures = real losses; use counterfactual.best_order to set occupy.policy.order; digest.res_pressure = repeated insufficient-resource blocks → lower recruit/build ambition (advice)". (Chưa nhắc lessons — Inc 2.)

- [ ] **Step 6: Run tests + lint** PASS.

- [ ] **Step 7: Commit** — `git commit -m "feat(brain): surface failures + counterfactual in digest/prompt"`

**⟶ Checkpoint Inc 1: brain hết mù kết cục. Verify live (tùy chọn): đánh 1 trận có tổn thất, xem failures.json + brain đặt policy.order.**

---

# INCREMENT 2 — Lessons store (chưng cất bài học có-bằng-chứng)

## Task 7: LessonStore

**Files:**
- Create: `nta_agent/brain/lessons.py`
- Test: `tests/test_lessons.py`

**Interfaces:**
- `Lesson(id,created,last_seen,times_seen,trigger,diagnosis,resolution,evidence,validated_by,status)`.
- `LessonStore(path, cap=50)`: `.upsert(lesson_dict)->str`, `.active()->list[Lesson]`, `.all()->list[Lesson]`, `.retire(id)`, `.pin(id)`, `.save()`. Dedup theo `trigger` (JSON-canonical) → cập nhật last_seen/times_seen thay vì thêm.

- [ ] **Step 1: Write failing test**:
```python
from nta_agent.brain.lessons import LessonStore

def _lesson(**kw):
    base = {"trigger": {"kind": "battle_loss", "match": {"monster_id": 4116}},
            "diagnosis": "AoE >9", "resolution": {"lever_edits": {"occupy": {"policy": {"order": "tank_first"}}}},
            "evidence": ["e1"]}
    base.update(kw); return base

def test_upsert_and_active(tmp_path):
    st = LessonStore(tmp_path / "l.json")
    lid = st.upsert(_lesson())
    assert [l.id for l in st.active()] == [lid]

def test_dedup_same_trigger_increments_times_seen(tmp_path):
    st = LessonStore(tmp_path / "l.json")
    a = st.upsert(_lesson()); b = st.upsert(_lesson(evidence=["e2"]))
    assert a == b and st.all()[0].times_seen == 2

def test_retire_hides_from_active(tmp_path):
    st = LessonStore(tmp_path / "l.json")
    lid = st.upsert(_lesson()); st.retire(lid)
    assert st.active() == [] and st.all()[0].status == "retired"

def test_cap_evicts_oldest_active(tmp_path):
    st = LessonStore(tmp_path / "l.json", cap=2)
    for m in (1, 2, 3):
        st.upsert(_lesson(trigger={"kind": "battle_loss", "match": {"monster_id": m}}))
    assert len(st.all()) == 2
```

- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement** `lessons.py` (dataclass + store, atomic save như ledger; dedup bằng `json.dumps(trigger, sort_keys=True)`; cap giữ N mới nhất theo last_seen).
- [ ] **Step 4: Run tests + lint** PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(brain): lessons store (dedup by trigger, retire/pin)"`

---

## Task 8: guard.sanitize_lessons (evidence-grounded + autonomy split)

**Files:**
- Modify: `nta_agent/brain/guard.py`
- Test: `tests/test_guard_lessons.py`

**Interfaces:**
- `sanitize_lessons(edits, ledger, valid_army_uids, valid_build_ids=None) -> list[dict]`. Mỗi lesson hợp lệ trả dict sẵn cho `LessonStore.upsert`. Loại lesson không còn evidence hợp lệ. `resolution.lever_edits` chạy qua `sanitize_edits`; nếu rỗng sau clamp (toàn field human-owned/max_loss) → chuyển `resolution` thành `{"advice": diagnosis}`.

- [ ] **Step 1: Write failing test**:
```python
from nta_agent.brain.guard import sanitize_lessons

class Led:
    def __init__(self, ids): self._ids = set(ids)
    def has(self, i): return i in self._ids

def test_drops_lesson_without_valid_evidence():
    led = Led([])   # no real events
    out = sanitize_lessons({"lessons": [{"trigger": {"kind": "battle_loss"},
        "diagnosis": "x", "resolution": {"lever_edits": {}}, "evidence": ["ghost"]}]}, led, set())
    assert out == []

def test_keeps_safe_lever_edit_and_filters_evidence():
    led = Led(["e1"])
    out = sanitize_lessons({"lessons": [{"trigger": {"kind": "battle_loss"}, "diagnosis": "AoE",
        "resolution": {"lever_edits": {"occupy": {"policy": {"order": "tank_first"}}}},
        "evidence": ["e1", "ghost"]}]}, led, set())
    assert out[0]["evidence"] == ["e1"]
    assert out[0]["resolution"]["lever_edits"]["occupy"]["policy"]["order"] == "tank_first"

def test_human_owned_lever_becomes_advice():
    led = Led(["e1"])
    out = sanitize_lessons({"lessons": [{"trigger": {"kind": "res_depletion"}, "diagnosis": "raise cap",
        "resolution": {"lever_edits": {"occupy": {"max_loss": 50}}}, "evidence": ["e1"]}]}, led, set())
    assert "advice" in out[0]["resolution"] and "lever_edits" not in out[0]["resolution"]
```

- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement** `sanitize_lessons` (dùng lại `sanitize_edits` + `_num`; strip `max_loss`/build/army.group như brain_service làm; nếu lever rỗng → advice). Whitelist `trigger.match` keys: `monster_id`, `resource`, `goal`.
- [ ] **Step 4: Run tests + lint** PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(brain): guard sanitize_lessons (evidence-grounded, autonomy split)"`

---

## Task 9: brain_service integrate lessons + prompt

**Files:**
- Modify: `nta_agent/brain/brain_service.py` (thực ra `nta_agent/runtime/brain_service.py`), `nta_agent/brain/llm.py`, `nta_agent/brain/digest.py` (đã có param lessons từ Task 6)
- Test: mở rộng `tests/test_brain_service*.py`

- [ ] **Step 1: Write failing test** — fake chat trả lesson hợp lệ → persist + áp lever; lesson bịa (no evidence) → không persist:
```python
# given a BrainService with a FakeLedger(has e1) + fake chat returning
#   {"lessons":[{"trigger":{"kind":"battle_loss","match":{"monster_id":4116}},
#     "diagnosis":"AoE","resolution":{"lever_edits":{"occupy":{"policy":{"order":"tank_first"}}}},
#     "evidence":["e1"]}], "occupy":{"policy":{"order":"tank_first"}}}
# after tick(): lessons.json has 1 active lesson AND profile.occupy["policy"]["order"]=="tank_first"
# a second run returning evidence:["ghost"] -> no new lesson persisted
```
(viết cụ thể theo mẫu test brain_service hiện có — inject `llm_propose`, `LessonStore` tại tmp path, `FailureLedger` fake.)

- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement** — brain_service: nạp `LessonStore(cfg.lessons_path, cap=cfg.lessons_cap)`; truyền `lessons=store.active()` vào digest; sau LLM: `for l in sanitize_lessons(edits, ledger, valid, build_ids): store.upsert(l)`; lesson có `resolution.advice` → gộp vào `advice`; `resolution.lever_edits` đã nằm trong `edits` nên áp theo đường hiện tại (không cần đụng riêng). `store.save()` cuối.
- [ ] **Step 4: Prompt** — `llm.py`: thêm schema `lessons[]` + luật: "each lesson MUST cite evidence = event ids from digest.failures; safe lever fixes go in resolution.lever_edits (also apply them in the top-level edit); human-owned fixes go as resolution.advice; dedup by trigger."
- [ ] **Step 5: Run tests + lint** PASS.
- [ ] **Step 6: Commit** — `git commit -m "feat(brain): distill grounded lessons into the loop"`

---

## Task 10: Dashboard — Failures + Lessons panel

**Files:**
- Modify: `nta_agent/dashboard/` (component JS + API route đọc `failures.json`/`lessons.json`; control để retire/pin)
- Test: theo mẫu dashboard hiện có (nếu có test API); ít nhất smoke: route trả JSON.

- [ ] **Step 1:** API route `/api/failures` + `/api/lessons` đọc file (best-effort, rỗng nếu thiếu). Test route trả list.
- [ ] **Step 2:** Component Vue hiển thị: Failures gần đây (kind, cell/rule, self_dead, counterfactual.best_order) + Lessons (diagnosis, trigger, resolution tóm tắt, nút Retire/Pin).
- [ ] **Step 3:** Retire/Pin ghi qua control file; brain_service đọc để `store.retire/pin` (hoặc dashboard sửa lessons.json trực tiếp + brain_service reload — theo mẫu profile edit).
- [ ] **Step 4:** Commit — `git commit -m "feat(dashboard): failures + lessons panel (retire/pin)"`

**⟶ Checkpoint Inc 2: brain có trí nhớ chiến thuật có-bằng-chứng, hiện trên dashboard, người kiểm soát.**

---

## Self-Review (đã chạy khi viết plan)
- **Spec coverage:** ledger (§5.1)→T1; record-summary/replay (§5.2)→T2; counterfactual (§5.2)→T3/T4; observer+sinks (§5.7,§6)→T5; digest/prompt (§5.3,§5.9)→T6; lessons store (§5.4)→T7; guard evidence (§5.5)→T8; brain_service+autonomy (§5.6)→T9; dashboard (§5.10)→T10. Đủ.
- **Placeholder scan:** không có TBD; mọi task có code + test cụ thể. (T10 dựa mẫu dashboard sẵn có nên mô tả bước, không full Vue — chấp nhận vì tuân pattern repo.)
- **Type consistency:** `FailureLedger.has/recent/record/aggregate_res` dùng nhất quán T1↔T5↔T6↔T8; `best_counterfactual_order`→`{best_order,self_dead}` nhất quán T4↔T5↔T6; `sanitize_lessons(...)->list[dict]`→`LessonStore.upsert(dict)` khớp T8↔T9.

## Execution Handoff
Plan lưu tại `docs/superpowers/plans/2026-09-22-brain-learn-from-failure.md`. Đề xuất **Subagent-Driven** (mỗi task 1 subagent, review giữa các task) hoặc **Inline**. Có thể dừng sau Inc 1 (checkpoint) để verify live trước khi làm Inc 2.
