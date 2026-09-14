# B1 — Tactics Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A persisted tactics profile the hands obey deterministically — driving army composition and a chest-budget-aware occupy-farming planner (win with ≤ max_loss, maximize loot per chest) — with no LLM.

**Architecture:** `profile.py` loads a typed `Profile` (army + occupy policy). A `treasure_model` turns a cell's land config into (chest_cost, reward_value) and reads the current chest budget from state. A pure `farming` planner filters winnable cells (existing sim-advisor) and picks the highest-loot set within the chest budget. `OccupyCell` and `Recruit` consume the profile; a small rule opens/claims earned treasures.

**Tech Stack:** Python 3.12 (`.venv/Scripts/python.exe`), pytest, ruff. Reuses `execution/advisor.py` (best_plan), `order_strategies`, `data/config`.

**Spec:** `docs/superpowers/specs/2026-09-14-track-b-brain-and-tactics-profile-design.md`

## Global Constraints

- Lint `ruff check nta_agent tests`; test `.venv/Scripts/python.exe -m pytest -q`.
- Thin brain: B1 has **no LLM**; all decisions are rules reading the profile.
- `max_loss` alone gates danger (sim already reflects thorns/reflect in loss%).
- Loop must never die: missing profile → defaults; missing/failed treasure model or sim → planner degrades to the current single-best-win occupy.
- Determinism preserved; do not regress existing sim/advisor goldens.
- Commit proactively at each green task; finish flow = push → PR → merge.
- Config fields observed: `landAttr.json` rows have `treasures_count` ("min,max"), `treasures_lv`, `need_stamina`, `armys_3/4/5`; `treasure.json` rows have `lv`, `rewards` (`"type,sub,min,max|..."`), `count`.

---

### Task 1: RE the chest/treasure mechanic (investigation → documented model)

**Files:**
- Create: `docs/re/treasure-mechanic.md` (findings)
- Create (fixture): `nta_agent/data/config/` already holds the tables; no new config.

**Goal:** Nail three unknowns so later tasks are concrete: (a) how a discovered cell maps to its `landAttr` row (chest_cost/reward source); (b) where the **chest budget** lives in `GameState` (newbie/ranked: +50/day capped 50; free: empty pawn treasure slots); (c) the open→claim action flow.

- [ ] **Step 1: Map cell → landAttr → loot.** Inspect config + a live/fixture area:

Run: `.venv/Scripts/python.exe -c "import json;la={r['id']:r for r in json.load(open('nta_agent/data/config/landAttr.json',encoding='utf-8'))};tr={r['id']:r for r in json.load(open('nta_agent/data/config/treasure.json',encoding='utf-8'))};print(list(la.items())[:2]);print(list(tr.items())[:2])"`

Determine: given an occupy candidate's `land_id` (from `get_area`/`AreaInfo`), which `landAttr` row applies, and how `treasures_count` + `treasures_lv` select `treasure.json` rows → resource reward. Record the exact lookup in the findings doc.

- [ ] **Step 2: Find the chest budget in state.** Search the entry/state for a treasure-capacity field:

Run: `.venv/Scripts/python.exe -c "import json;s=json.load(open('nta_agent/io/api/schema.json',encoding='utf-8'));[print(n) for n in s if 'TREASURE' in n.upper() or 'ENTRY' in n.upper()]"`
and grep the decrypted engine: `grep -oE '.{40}(treasureCount|openCount|treasureCap|canOpen|treasureNum).{40}' tools/re/decrypted/index.js | head`

Record: the field name + room-type rule (newbie/ranked cap 50 +50/day; free = empty pawn treasure slots), and where `GameState` exposes/should expose it.

- [ ] **Step 3: Confirm open→claim flow.** From schema: `GAME_HD_OpenArmyTreasure{index,auid}` / `GAME_HD_ClaimArmyTreasure{index,auid}` / batch `OpenArmysTreasure{targets}`. Record which to call and in what order, and what counts against the budget.

- [ ] **Step 4: Write findings** to `docs/re/treasure-mechanic.md`: the cell→loot lookup, budget field + rule, open/claim flow. This doc is the contract Tasks 3 & 6 implement to.

- [ ] **Step 5: Commit**

```bash
git add docs/re/treasure-mechanic.md
git commit -m "re: document chest/treasure mechanic (loot lookup, budget, open/claim)"
```

---

### Task 2: `profile.py` — typed Profile + load/save/defaults

**Files:**
- Create: `nta_agent/execution/profile.py`
- Test: `tests/test_profile.py`

**Interfaces:**
- Produces: `DEFAULT_PROFILE: dict`; `Profile` dataclass with `.army` and `.occupy`; `load_profile(path) -> Profile` (deep-merges file over defaults; missing/invalid file → defaults); `save_profile(profile, path)`.
- `army`: `{group: list[str], roles: dict[str,str], onetile: bool, composition: dict[str, dict[str,int]]}`.
- `occupy`: `{max_loss: float, max_march_ms: int, loot: {enabled: bool, min_reward_per_chest: float}}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profile.py
import json
from nta_agent.execution.profile import load_profile, save_profile, DEFAULT_PROFILE, Profile


def test_defaults_when_file_missing(tmp_path):
    p = load_profile(tmp_path / "nope.json")
    assert isinstance(p, Profile)
    assert p.occupy["max_loss"] == DEFAULT_PROFILE["occupy"]["max_loss"]
    assert p.army["onetile"] == DEFAULT_PROFILE["army"]["onetile"]


def test_file_overrides_merge_over_defaults(tmp_path):
    f = tmp_path / "profile.json"
    f.write_text(json.dumps({"occupy": {"max_loss": 15}}), encoding="utf-8")
    p = load_profile(f)
    assert p.occupy["max_loss"] == 15                 # overridden
    assert "loot" in p.occupy                          # default kept
    assert p.army["group"] == DEFAULT_PROFILE["army"]["group"]


def test_save_then_load_roundtrip(tmp_path):
    f = tmp_path / "profile.json"
    prof = load_profile(f)
    prof.occupy["max_loss"] = 7
    save_profile(prof, f)
    assert load_profile(f).occupy["max_loss"] == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_profile.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# nta_agent/execution/profile.py
"""Tactics profile: the contract the hands obey (army + occupy policy)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROFILE = {
    "army": {"group": [], "roles": {}, "onetile": True, "composition": {}},
    "occupy": {"max_loss": 0.0, "max_march_ms": 0,
               "loot": {"enabled": True, "min_reward_per_chest": 0.0}},
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


@dataclass
class Profile:
    army: dict
    occupy: dict


def load_profile(path) -> Profile:
    path = Path(path)
    data = {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        data = {}
    merged = _merge(DEFAULT_PROFILE, data if isinstance(data, dict) else {})
    return Profile(army=merged["army"], occupy=merged["occupy"])


def save_profile(profile: Profile, path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"army": profile.army, "occupy": profile.occupy},
                               ensure_ascii=False, indent=1), encoding="utf-8")
```

- [ ] **Step 4: Run test** → PASS. Then `ruff check nta_agent/execution/profile.py tests/test_profile.py`.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/profile.py tests/test_profile.py
git commit -m "execution: tactics Profile (load/save/defaults, deep-merge)"
```

---

### Task 3: `treasure_model.py` — cell loot + chest budget

**Files:**
- Create: `nta_agent/execution/treasure_model.py`
- Test: `tests/test_treasure_model.py`

**Interfaces:**
- Consumes: `GameConfig` (config tables), the Task 1 findings for the exact lookup/budget field.
- Produces: `CellLoot` dataclass `{chest_cost: int, reward_value: float}`; `cell_loot(land_id: int, config) -> CellLoot` (0-cost/0-value when the land has no treasure); `chest_budget(state) -> int` (reads the budget field per Task 1; returns a large sentinel for unlimited/free mode).

- [ ] **Step 1: Write the failing test** (uses the real config tables)

```python
# tests/test_treasure_model.py
from nta_agent.data.config import GameConfig
from nta_agent.execution.treasure_model import cell_loot, CellLoot


def test_cell_loot_reads_treasure_count_and_reward():
    cfg = GameConfig.load()
    # a land type with treasures (e.g. 1003: treasures_count "2,2") yields cost>0,
    # reward>0; a no-treasure land yields zeros.
    loot = cell_loot(1003, cfg)
    assert isinstance(loot, CellLoot)
    assert loot.chest_cost >= 1 and loot.reward_value > 0
    assert cell_loot(-1, cfg) == CellLoot(chest_cost=0, reward_value=0.0)
```

- [ ] **Step 2: Run test** → FAIL (module missing).

- [ ] **Step 3: Implement** (map per Task 1; from config inspection: `landAttr.treasures_count` = "min,max" chest count, `treasures_lv` selects `treasure.json` rows whose `rewards` = `"type,sub,min,max|..."`; reward_value = sum of average resource amounts × count).

```python
# nta_agent/execution/treasure_model.py
"""Turn a cell's land config into (chest_cost, reward_value); read chest budget.

Lookup confirmed in docs/re/treasure-mechanic.md. reward_value is a comparable
scalar (avg resource amount * chest count), used only to rank cells.
"""
from __future__ import annotations

from dataclasses import dataclass

_UNLIMITED = 10_000  # free-mode / no-cap sentinel


@dataclass(frozen=True)
class CellLoot:
    chest_cost: int
    reward_value: float


def _avg_reward(treasure_row: dict) -> float:
    total = 0.0
    for chunk in str(treasure_row.get("rewards", "")).split("|"):
        parts = chunk.split(",")
        if len(parts) >= 4:
            lo, hi = float(parts[2]), float(parts[3])
            total += (lo + hi) / 2
    return total


def cell_loot(land_id: int, config) -> CellLoot:
    la = config.table("landAttr").get(int(land_id))
    if not la:
        return CellLoot(0, 0.0)
    cnt = str(la.get("treasures_count", "0,0")).split(",")
    chest_cost = int(cnt[-1] or 0)  # upper bound of chests
    if chest_cost <= 0:
        return CellLoot(0, 0.0)
    lv = int(str(la.get("treasures_lv", "0")).split(",")[0] or 0)
    tr = config.table("treasure")
    row = tr.get(lv) or next((r for r in tr.values() if int(r.get("lv", 0)) == lv), None)
    reward = _avg_reward(row) * chest_cost if row else 0.0
    return CellLoot(chest_cost=chest_cost, reward_value=reward)


def chest_budget(state) -> int:
    """Current openable-chest budget. Per Task 1: newbie/ranked exposes a capped
    counter; free mode is bounded by empty pawn slots. Returns _UNLIMITED when
    the field is absent (never block occupy on a missing budget)."""
    player = (state.raw or {}).get("player", {}) or {}
    cap = player.get("treasureOpenCount")  # exact key confirmed in Task 1
    return int(cap) if cap is not None else _UNLIMITED
```

*(Task 1 confirms `landAttr` keying by `land_id`, the `treasures_lv`→`treasure` join, and the `treasureOpenCount` field name; adjust these three to the findings before finishing the task.)*

- [ ] **Step 4: Run test** → PASS. `ruff check`.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/treasure_model.py tests/test_treasure_model.py
git commit -m "execution: treasure model (cell loot + chest budget)"
```

---

### Task 4: `farming.py` — chest-budget farming picker (pure)

**Files:**
- Create: `nta_agent/execution/farming.py`
- Test: `tests/test_farming.py`

**Interfaces:**
- Consumes: candidates (objects with `.index`, `.land_id`), `predict(cell) -> Plan|None` (winnable plan with `.prediction.loss_percent`, `.armies`; from the existing advisor), `loot_of(cell) -> CellLoot`, `budget: int`, `max_loss: float`, `min_reward_per_chest: float`, `max_march_ms: int`, `march_of(cell) -> int`.
- Produces: `FarmPick{cell, plan, loot}`; `plan_farm(candidates, predict, loot_of, *, budget, max_loss, min_reward_per_chest=0, max_march_ms=0, march_of=None) -> list[FarmPick]` — greedy by reward/chest within budget.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_farming.py
from types import SimpleNamespace
from nta_agent.execution.farming import plan_farm, FarmPick
from nta_agent.execution.treasure_model import CellLoot


def _cell(i, land): return SimpleNamespace(index=i, land_id=land)


def test_picks_highest_reward_per_chest_within_budget():
    cells = [_cell(1, 11), _cell(2, 22), _cell(3, 33)]
    loot = {1: CellLoot(2, 100.0), 2: CellLoot(1, 90.0), 3: CellLoot(3, 30.0)}
    def predict(c):  # all winnable, 0 loss
        return SimpleNamespace(armies=[{"uid": "a"}], target=c.index,
                               label="x", prediction=SimpleNamespace(win=True, loss_percent=0))
    picks = plan_farm(cells, predict, lambda c: loot[c.index], budget=3, max_loss=0)
    # reward/chest: cell2=90, cell1=50, cell3=10 -> take cell2(1) + cell1(2) = budget 3
    assert [p.cell.index for p in picks] == [2, 1]


def test_filters_by_max_loss_and_min_reward():
    cells = [_cell(1, 11), _cell(2, 22)]
    loot = {1: CellLoot(1, 5.0), 2: CellLoot(1, 100.0)}
    def predict(c):
        win = c.index == 1  # cell2 unwinnable within max_loss
        return SimpleNamespace(armies=[{"uid": "a"}], target=c.index, label="x",
                               prediction=SimpleNamespace(win=win, loss_percent=0 if win else 80))
    picks = plan_farm(cells, predict, lambda c: loot[c.index], budget=5,
                      max_loss=0, min_reward_per_chest=10)
    assert picks == []  # cell1 below min_reward_per_chest, cell2 not winnable
```

- [ ] **Step 2: Run test** → FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# nta_agent/execution/farming.py
"""Pick which resource cells to occupy: winnable (<=max_loss), highest loot per
chest, within the chest budget. Pure over injected predict + loot lookup."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FarmPick:
    cell: object
    plan: object
    loot: object


def plan_farm(candidates, predict, loot_of, *, budget, max_loss,
              min_reward_per_chest=0.0, max_march_ms=0, march_of=None):
    scored = []
    for c in candidates:
        if max_march_ms and march_of and march_of(c) > max_march_ms:
            continue
        loot = loot_of(c)
        if loot.chest_cost <= 0:
            continue
        per = loot.reward_value / loot.chest_cost
        if per < min_reward_per_chest:
            continue
        plan = predict(c)
        if plan is None or not plan.prediction.win or plan.prediction.loss_percent > max_loss:
            continue
        scored.append((per, loot, plan, c))
    scored.sort(key=lambda t: t[0], reverse=True)  # best reward/chest first
    picks, spent = [], 0
    for _per, loot, plan, c in scored:
        if spent + loot.chest_cost > budget:
            continue
        picks.append(FarmPick(cell=c, plan=plan, loot=loot))
        spent += loot.chest_cost
    return picks
```

- [ ] **Step 4: Run test** → PASS. `ruff check`.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/farming.py tests/test_farming.py
git commit -m "execution: chest-budget farming picker (reward/chest within budget)"
```

---

### Task 5: Recruit fills armies toward profile composition

**Files:**
- Modify: `nta_agent/execution/heuristics.py` (the `Recruit` rule)
- Test: `tests/test_recruit_composition.py`

**Interfaces:**
- Consumes: `Profile.army.composition` (`{armyUid: {pawnId: count}}`), current armies (from `actions.get_player_armys`).
- Produces: `Recruit` (when given a profile) recruits toward the per-army target counts; without a profile it keeps current behavior.

- [ ] **Step 1: Write the failing test** (fake actions; assert it drills the missing pawns)

```python
# tests/test_recruit_composition.py
from types import SimpleNamespace
from nta_agent.execution.heuristics import Recruit
from nta_agent.execution.profile import Profile


def test_recruit_targets_missing_pawns_from_profile():
    prof = Profile(army={"group": ["A"], "roles": {}, "onetile": True,
                         "composition": {"A": {3101: 3}}},
                   occupy={})
    armies = [{"uid": "A", "index": 5, "pawns": [{"id": 3101}]}]  # has 1, wants 3
    drills = []
    actions = SimpleNamespace(
        get_player_armys=lambda: armies,
        drill_pawn=lambda **kw: drills.append(kw))
    rule = Recruit(profile=prof)
    rule.run(actions)   # adapt to Recruit's actual entry point
    assert any(d.get("id") == 3101 for d in drills)
    # asked for 2 more (3 target - 1 have)
    assert sum(1 for d in drills if d.get("id") == 3101) == 2
```

- [ ] **Step 2: Run test** → FAIL (Recruit has no profile-driven mode / `run`).

- [ ] **Step 3: Implement** — give `Recruit` an optional `profile`; when set, for each army in `profile.army.composition`, compute missing = target - current per pawnId and drill that many into that army (reuse the existing drill/recruit action; respect existing guards). Keep the no-profile path unchanged. (Match the real `Recruit`/`Actions.drill_pawn` signature; the test's `run` is illustrative — wire into the rule's real tick.)

- [ ] **Step 4: Run test** → PASS. `ruff check`. Also run existing recruit tests.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/heuristics.py tests/test_recruit_composition.py
git commit -m "recruit: fill armies toward profile composition"
```

---

### Task 6: Wire profile + farming into OccupyCell and the runtime

**Files:**
- Modify: `nta_agent/execution/heuristics.py` (`OccupyCell`, `RuleEngine.default`)
- Modify: `nta_agent/runtime/runner.py` (load profile, pass to rules)
- Modify: `nta_agent/runtime/config.py` (add `profile_path`)
- Modify: `nta_agent/execution/actions.py` (add `open_army_treasure`/`claim_army_treasure` per Task 1)
- Test: `tests/test_occupy_rule.py` (extend)

**Interfaces:**
- Consumes: `Profile`, `farming.plan_farm`, `treasure_model.cell_loot`/`chest_budget`, the advisor `best_plan`, treasure actions from Task 1.
- Produces: `OccupyCell(profile=...)` uses the profile group for candidate orders and `plan_farm` to choose targets within the chest budget; emits `farm_plan{picks:[{target,reward,chest_cost,loss}]}`; occupies the top pick; a treasure open/claim step runs while budget allows. `RuleEngine.default(profile=None)` threads the profile.

- [ ] **Step 1: Write the failing test** — a fake sim + treasure model: two winnable cells, budget=1 chest; assert OccupyCell picks the higher reward/chest cell and occupies it.

```python
# tests/test_occupy_rule.py (add)
def test_occupy_uses_profile_farming_within_budget(monkeypatch):
    from types import SimpleNamespace
    from nta_agent.execution.profile import Profile
    center = 182 * W + 526
    st = GameState(source="api"); st.user.uid = "me"; st.main_city_index = center
    st.resources.stamina = 10
    st.raw = {"player": {"treasureOpenCount": 1}}   # budget = 1 chest
    areas = {center: _cell(owner="me", city=1001),
             center - 1: _cell(owner="", pawns=[50]),
             center + 1: _cell(owner="", pawns=[50])}
    army = [{"index": center, "uid": "A", "pawns": [{"id": 3101}, {"id": 3101}]}]
    act = FakeActions(areas=areas, armies=army)
    prof = Profile(army={"group": ["A"], "roles": {}, "onetile": True, "composition": {}},
                   occupy={"max_loss": 0, "max_march_ms": 0,
                           "loot": {"enabled": True, "min_reward_per_chest": 0}})
    # both cells winnable; cell center-1 has higher reward/chest -> chosen
    monkeypatch.setattr("nta_agent.execution.treasure_model.cell_loot",
        lambda land, cfg: __import__("nta_agent.execution.treasure_model", fromlist=["CellLoot"]).CellLoot(1, 100.0 if land else 10.0))
    rule = OccupyCell(radius=1, use_sim=False, predictor=BattlePredictor(), profile=prof)
    assert rule.applies(st, act) is True
    rule.act(act)
    assert act.calls and act.calls[0][0] == "occupy"
```

- [ ] **Step 2: Run test** → FAIL (OccupyCell has no profile/farming path).

- [ ] **Step 3: Implement** — `OccupyCell` gains `profile`; when present, build candidate orders from `profile.army.group` (feeding `best_plan`), compute `loot_of = lambda c: cell_loot(c.land_id, config)` and `budget = chest_budget(state)` (skip the loot filter if `profile.occupy.loot.enabled` is false → budget = unlimited), call `plan_farm(...)`, pick `picks[0]`, emit `farm_plan`, occupy it. Keep the current behavior when `profile is None`. Add `Actions.open_army_treasure`/`claim_army_treasure` (routes per Task 1) and a guarded post-occupy claim step. Thread `profile` through `RuleEngine.default(profile)` and `runner.run` (load via `load_profile(cfg.profile_path)`; `profile_path` defaults to `build/run/profile.json`).

- [ ] **Step 4: Run test** → PASS. Then full suite + ruff + node goldens.

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check nta_agent tests && node --test --test-force-exit tools/battlesim/test/golden.test.js`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/heuristics.py nta_agent/runtime/runner.py nta_agent/runtime/config.py nta_agent/execution/actions.py tests/test_occupy_rule.py
git commit -m "occupy: profile-driven chest-budget farming; treasure open/claim; wire profile"
```

---

## Self-Review

**Spec coverage:** §3.1 profile → Task 2; §3.2 chest RE → Task 1; §3.3 farming planner + treasure model → Tasks 3,4,6; §3.4 recruit/occupy consumers → Tasks 5,6; §3.5 profile access/runtime → Tasks 2,6; treasure open/claim → Task 6. Non-goals (LLM/chat/intents/build) excluded. Covered.

**Placeholder scan:** No TBD/TODO. Task 1 is an investigation with concrete probes + a findings-doc deliverable that Tasks 3/6 implement to; the three RE-gated identifiers (landAttr keying, treasures_lv→treasure join, `treasureOpenCount`) are flagged explicitly to reconcile against findings — not left blank. Tasks 5/6 note where the illustrative `run` must bind to the real rule entry points.

**Type consistency:** `Profile{army,occupy}` (Task 2) used in 5,6. `CellLoot{chest_cost,reward_value}` + `cell_loot`/`chest_budget` (Task 3) used in 4,6. `plan_farm(...) -> [FarmPick{cell,plan,loot}]` (Task 4) used in 6. `Plan.prediction.{win,loss_percent}` matches advisor. Config table names (`landAttr`, `treasure`) match Task 1 inspection.

**Residual risk:** the three RE-gated identifiers (Task 1) — if the live field differs (e.g. budget key name, or cell→landAttr needs `land.json` indirection), Task 3 adjusts to the findings before its test is finalized; the farming/occupy logic (Tasks 4,6) is independent of those exact names.
