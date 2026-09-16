# C1 — In-city Construction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The agent constructs new in-city buildings (server auto-places) — building any unlocked, under-`bt_count`, affordable building — via the same BuildOrder rule that already upgrades.

**Architecture:** A unified `next_build_action` returns either a *construct* (lv1 via `HD_AddAreaBuild`) or an *upgrade* (existing) step; `BuildOrder` dispatches accordingly. Deterministic, config-driven; no brain (C2/later).

**Tech Stack:** Python 3.12 (`.venv/Scripts/python.exe`), pytest, ruff. Reuses `data/config`, `build_planner`, `execution/heuristics`, the API session.

**Spec:** `docs/superpowers/specs/2026-09-16-c1-in-city-construction-design.md`

## Global Constraints

- Lint `ruff check nta_agent tests`; test `.venv/Scripts/python.exe -m pytest -q`.
- Route exact: `game/HD_AddAreaBuild` with `{"index": int, "id": int}`.
- `max_count(id) = abs(bt_count)`, `0 → 1`. In-city = buildBase `type == 1`.
- Construction cost/prereq = `config.build_upgrade(id, 1)` (buildAttr `id*1000+1`).
- Preserve existing upgrade behavior + build-queue/main-cap/prereq/affordability checks.
- Blocked keys: upgrades `(uid, target_lv)`; constructs `("construct", build_id)`.
- Commit proactively per green task; finish flow = push → PR → merge.

---

### Task 1: config buildBase accessors

**Files:** Modify `nta_agent/data/config.py`; Test `tests/test_config_buildbase.py` (create)

**Interfaces:** `GameConfig.build_base(build_id) -> dict | None` (buildBase row); `max_count(build_id) -> int` (`abs(bt_count)`, 0→1, unknown id→1); `in_city_build_ids() -> list[int]` (rows with `type == 1`, sorted).

- [ ] **Step 1: Write failing test**

```python
# tests/test_config_buildbase.py
from nta_agent.data.config import GameConfig


def test_max_count_and_in_city_ids():
    c = GameConfig.load()
    assert c.max_count(2002) == 3    # Kho Lương bt_count -3
    assert c.max_count(2001) == 1    # Thành Chính bt_count -1
    assert c.max_count(999999) == 1  # unknown -> 1
    ids = c.in_city_build_ids()
    assert 2001 in ids and 2004 in ids   # main hall, barracks
    assert 3001 not in ids               # ancient capital (type 2) excluded
    assert c.build_base(2001)["ui"] == "BuildMainInfo"
```

- [ ] **Step 2: Run** → FAIL (`.venv/Scripts/python.exe -m pytest tests/test_config_buildbase.py -q`).
- [ ] **Step 3: Implement** — after `build_upgrade` in `config.py`:

```python
    def build_base(self, build_id: int) -> dict | None:
        return self.table("buildBase").get(build_id)

    def max_count(self, build_id: int) -> int:
        row = self.build_base(build_id)
        n = abs(int(row.get("bt_count", 0))) if row else 0
        return n or 1

    def in_city_build_ids(self) -> list[int]:
        return sorted(bid for bid, r in self.table("buildBase").items()
                      if r.get("type") == 1)
```

- [ ] **Step 4: Run** → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/data/config.py tests/test_config_buildbase.py && git commit -m "config: buildBase accessors (build_base/max_count/in_city_build_ids)"`

---

### Task 2: `add_build` action

**Files:** Modify `nta_agent/execution/actions.py`; Test `tests/test_actions_build.py` (create)

**Interfaces:** `Actions.add_build(index: int, build_id: int) -> dict` → `game/HD_AddAreaBuild` with `{"index": int(index), "id": int(build_id)}`.

- [ ] **Step 1: Write failing test**

```python
# tests/test_actions_build.py
from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self):
        self.state = GameState(source="api"); self.state.raw = {}
        self.sent = []
    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params)); return {}


def test_add_build_sends_route():
    s = FakeSession()
    Actions(s).add_build(109726, 2016)
    assert s.sent[0] == ("game/HD_AddAreaBuild", {"index": 109726, "id": 2016})
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — near `upgrade_build` in `actions.py`:

```python
    def add_build(self, index: int, build_id: int) -> dict:
        """Construct a new building; the server auto-places it (GAME_HD_AddAreaBuild)."""
        return self.session.request("game/HD_AddAreaBuild",
                                    {"index": int(index), "id": int(build_id)})
```

- [ ] **Step 4: Run** → PASS; `ruff check`.
- [ ] **Step 5: Commit** `git add nta_agent/execution/actions.py tests/test_actions_build.py && git commit -m "execution: add_build action (HD_AddAreaBuild)"`

---

### Task 3: `next_build_action` (construct or upgrade)

**Files:** Modify `nta_agent/execution/build_planner.py`; Test `tests/test_build_planner_construct.py` (create)

**Interfaces:**
- `BuildAction` dataclass: `kind: str` (`"construct"` | `"upgrade"`), `build_id: int`, `up: object` (the `BuildUpgrade` for the target level), `build: object | None` (the existing `Building` for upgrades; None for constructs).
- `next_build_action(state, config, sequence=None, blocked=None) -> BuildAction | None`: for each id in the order, if instance count `< config.max_count(id)` and the lv1 `BuildUpgrade` is prereq-ok / affordable / not blocked (`("construct", id)`) and main-hall exists (main_lv ≥ 1 for non-main) → return a construct; else fall through to the existing upgrade selection for that id's instances. Respects build-queue slots (as `next_upgrade` does).
- Keep `next_upgrade` unchanged (upgrade half + back-compat).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_build_planner_construct.py
from nta_agent.data.config import GameConfig
from nta_agent.execution.build_planner import next_build_action
from nta_agent.state.schema import Building, GameState


def _state(builds, cereal=99999, timber=99999, stone=99999, iron=99999):
    st = GameState(source="api")
    st.builds = builds
    st.resources.cereal = cereal; st.resources.timber = timber
    st.resources.stone = stone; st.resources.iron = iron
    st.build_queue = []; st.build_queue_slots = 2
    st.main_city_index = 109726
    return st


def _b(bid, lv, uid=None):
    return Building(id=bid, lv=lv, uid=uid or f"u{bid}", index=109726)


def test_constructs_missing_unlocked_building():
    c = GameConfig.load()
    # Y Quán (2016, prep_cond "") not present -> should be constructed at lv1.
    st = _state([_b(2001, 10)])  # main hall lv10 only
    act = next_build_action(st, c, sequence=[2016])
    assert act is not None and act.kind == "construct" and act.build_id == 2016
    assert act.up.level == 1


def test_respects_bt_count_then_upgrades():
    c = GameConfig.load()
    # main hall (2001) max_count 1 and already present -> no construct, upgrade instead.
    st = _state([_b(2001, 5)])
    act = next_build_action(st, c, sequence=[2001])
    assert act.kind == "upgrade" and act.build_id == 2001 and act.up.level == 6


def test_multi_instance_granary_constructs_until_max():
    c = GameConfig.load()
    # Kho Lương (2002) max_count 3; one present -> construct a second (count 1 < 3).
    st = _state([_b(2001, 10), _b(2002, 1)])
    act = next_build_action(st, c, sequence=[2002])
    assert act.kind == "construct" and act.build_id == 2002


def test_skips_blocked_construct():
    c = GameConfig.load()
    st = _state([_b(2001, 10)])
    act = next_build_action(st, c, sequence=[2016], blocked={("construct", 2016)})
    assert act is None  # only candidate was blocked


def test_unaffordable_construct_skipped():
    c = GameConfig.load()
    st = _state([_b(2001, 10)], cereal=0, timber=0, stone=0, iron=0)
    act = next_build_action(st, c, sequence=[2016])
    assert act is None  # can't afford lv1, nothing else in the order
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — add to `build_planner.py`:

```python
from dataclasses import dataclass


@dataclass
class BuildAction:
    kind: str          # "construct" | "upgrade"
    build_id: int
    up: object         # BuildUpgrade for the target level
    build: object = None  # existing Building (upgrades); None for constructs


def next_build_action(state, config, sequence=None, blocked=None):
    if not state.builds:
        return None
    if len(state.build_queue) >= state.build_queue_slots:
        return None
    blocked = blocked or set()
    queued_uids = {str(q.get("uid", "")) for q in state.build_queue}
    level_by_id = {b.id: b.lv for b in state.builds}
    main_lv = level_by_id.get(MAIN_HALL_ID, 0)
    counts: dict[int, int] = {}
    for b in state.builds:
        counts[b.id] = counts.get(b.id, 0) + 1
    order = sequence or sorted({b.id for b in state.builds})

    for build_id in order:
        # --- construct if under the instance cap and eligible at lv1 ---
        if counts.get(build_id, 0) < config.max_count(build_id) and \
                ("construct", build_id) not in blocked:
            up1 = config.build_upgrade(build_id, 1)
            if up1 is not None and _prep_ok(up1.prep_cond, level_by_id) \
                    and _affordable(up1.cost, state) \
                    and (build_id == MAIN_HALL_ID or main_lv >= 1):
                return BuildAction(kind="construct", build_id=build_id, up=up1)
        # --- else upgrade an existing instance (existing logic) ---
        for build in [b for b in state.builds if b.id == build_id]:
            if build.uid in queued_uids:
                continue
            target = build.lv + 1
            if (build.uid, target) in blocked:
                continue
            if build_id != MAIN_HALL_ID and target > main_lv:
                continue
            up = config.build_upgrade(build_id, target)
            if up is None or not _prep_ok(up.prep_cond, level_by_id) \
                    or not _affordable(up.cost, state):
                continue
            return BuildAction(kind="upgrade", build_id=build_id, up=up, build=build)
    return None
```

- [ ] **Step 4: Run** → PASS; `ruff check`. Also run `tests/test_occupy_rule.py`-style existing build tests (`pytest -k build -q`) to confirm `next_upgrade` untouched.
- [ ] **Step 5: Commit** `git add nta_agent/execution/build_planner.py tests/test_build_planner_construct.py && git commit -m "build_planner: next_build_action (construct or upgrade)"`

---

### Task 4: BuildOrder dispatches construct vs upgrade

**Files:** Modify `nta_agent/execution/heuristics.py` (`BuildOrder`); Test `tests/test_build_order.py` (create or extend the existing build test file)

**Interfaces:** `BuildOrder.applies` uses `next_build_action`; `_pending` holds the `BuildAction`. `act`: construct → `actions.add_build(state.main_city_index, action.build_id)`; upgrade → `actions.upgrade_build(action.build.index, uid=action.build.uid)`. On reject: construct → `blocked.add(("construct", build_id))`; upgrade → `blocked.add((uid, target))`.

- [ ] **Step 1: Write failing test**

```python
# tests/test_build_order.py
from types import SimpleNamespace
from nta_agent.data.config import GameConfig
from nta_agent.execution.heuristics import BuildOrder
from nta_agent.state.schema import Building, GameState


def _state(builds):
    st = GameState(source="api"); st.builds = builds
    for r in ("cereal", "timber", "stone", "iron"):
        setattr(st.resources, r, 99999)
    st.build_queue = []; st.build_queue_slots = 2; st.main_city_index = 109726
    return st


class Acts:
    def __init__(self):
        self.calls = []
    def add_build(self, index, build_id):
        self.calls.append(("add", index, build_id)); return {}
    def upgrade_build(self, index, uid=""):
        self.calls.append(("up", index, uid)); return {}


def test_build_order_constructs_missing():
    st = _state([Building(id=2001, lv=10, uid="m", index=109726)])
    act = Acts()
    rule = BuildOrder(sequence=[2016], config=GameConfig.load())
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls == [("add", 109726, 2016)]


def test_build_order_upgrades_existing():
    st = _state([Building(id=2001, lv=5, uid="m", index=109726)])
    act = Acts()
    rule = BuildOrder(sequence=[2001], config=GameConfig.load())
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls == [("up", 109726, "m")]
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — update `BuildOrder`:
  - `applies`: `self._pending = next_build_action(state, cfg, self.sequence, self._blocked)`; `self._city = state.main_city_index`; `return self._pending is not None`. (Import `next_build_action`.)
  - `act`:
```python
    def act(self, actions: Actions) -> None:
        act_ = self._pending
        self._pending = None
        if act_ is None:
            return
        try:
            if act_.kind == "construct":
                actions.add_build(self._city, act_.build_id)
            else:
                actions.upgrade_build(act_.build.index, uid=act_.build.uid)
        except Exception:
            if act_.kind == "construct":
                self._blocked.add(("construct", act_.build_id))
            else:
                self._blocked.add((act_.build.uid, act_.up.level))
            raise
```
  - Add `_city: int = 0` to the dataclass fields.

- [ ] **Step 4: Run** `pytest tests/test_build_order.py -q` → PASS; then full suite + ruff.
- [ ] **Step 5: Commit** `git add nta_agent/execution/heuristics.py tests/test_build_order.py && git commit -m "occupy/build: BuildOrder constructs new buildings (AddAreaBuild) or upgrades"`

---

## Self-Review

**Spec coverage:** §2 RE (bt_count/AddAreaBuild/cost) → Tasks 1–3; §4 config accessors → Task 1; add_build → Task 2; next_build_action → Task 3; BuildOrder dispatch + blocked keys → Task 4. §6 error handling → Task 4 (blocked on reject) + Task 3 (queue/prereq/afford). §8 tests → each task. Covered.

**Placeholder scan:** No TBD. All steps have runnable code/commands. Task 4 lists the exact `act`/`applies` edits and the new `_city` field.

**Type consistency:** `BuildAction{kind,build_id,up,build}` (T3) consumed in T4. `max_count`/`build_base`/`in_city_build_ids` (T1) used in T3. `add_build(index, build_id)` (T2) called in T4. `build_upgrade(id, 1)` returns a `BuildUpgrade` with `.level`/`.cost`/`.prep_cond` (existing) — used in T3. Blocked keys `("construct", build_id)` and `(uid, target_lv)` consistent T3/T4.
