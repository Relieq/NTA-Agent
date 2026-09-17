# Farming Heal-Routing Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep farming armies healthy by routing wounded ones to a fort/city to heal (passive server-side), so the occupy→chest loop runs continuously.

**Architecture:** A new deterministic `HealRouting` rule (best-effort, like `ClaimTreasures`) reads the player's armies, flags wounded ones (`pawn.hp[0] < pawn.hp[1]`), and issues `HD_MoveCellArmy` to the nearest heal node (main city / Cứ Điểm) with a free slot. Occupy stays paced by stamina. Armies are raw dicts from `get_player_armys()`; fort positions come from the existing `Territory` model.

**Tech Stack:** Python 3.12 (venv `.venv`), pytest, ruff. No new deps.

**Spec:** `docs/superpowers/specs/2026-09-17-farming-heal-loop-design.md`

## Global Constraints
- Run tests with `.venv/Scripts/python.exe -m pytest -q`; lint `.venv/Scripts/python.exe -m ruff check nta_agent tests`.
- Rules are **best-effort**: never raise out of `act`/`applies` in a way that stops the loop (RuleEngine already wraps exceptions, but avoid needless requests).
- Deterministic, **zero LLM tokens**.
- Army/pawn data are **raw dicts** (no `Pawn`/`Army` dataclass). Pawn hp = `p.get("hp") or [0, 0]`, current=`hp[0]`, max=`hp[-1]`.
- Manhattan geometry (diagonal costs 2); reuse `Territory.dist`/`dist_to_main` (`nta_agent/execution/territory.py`).
- Match surrounding Vietnamese comment style where files already use it.

---

### Task 1: Army-health helpers (pure)

**Files:**
- Create: `nta_agent/execution/army_health.py`
- Test: `tests/test_army_health.py`

**Interfaces:**
- Produces: `army_is_wounded(army: dict) -> bool`, `army_wound_frac(army: dict) -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_army_health.py
from nta_agent.execution.army_health import army_is_wounded, army_wound_frac


def _army(*hps):
    return {"pawns": [{"hp": list(h)} for h in hps]}


def test_healthy_army_not_wounded():
    a = _army((100, 100), (50, 50))
    assert army_is_wounded(a) is False
    assert army_wound_frac(a) == 0.0


def test_wounded_army_detected():
    a = _army((100, 100), (20, 50))
    assert army_is_wounded(a) is True
    assert abs(army_wound_frac(a) - (30 / 150)) < 1e-9


def test_missing_or_empty_hp_is_safe():
    assert army_is_wounded({"pawns": [{}]}) is False        # no hp -> treat as full
    assert army_is_wounded({}) is False                      # no pawns
    assert army_wound_frac({"pawns": []}) == 0.0             # no max -> 0, not div0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_army_health.py -q`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```python
# nta_agent/execution/army_health.py
"""Read wounded-state from a raw army dict (pawns carry hp:[cur,max])."""
from __future__ import annotations


def _hp(pawn: dict) -> tuple[int, int]:
    hp = pawn.get("hp") or [0, 0]
    cur = int(hp[0]) if len(hp) else 0
    mx = int(hp[-1]) if len(hp) else 0
    # No max known -> treat as full (cur == max) so we never route on bad data.
    return (cur, mx) if mx > 0 else (0, 0)


def army_is_wounded(army: dict) -> bool:
    for p in army.get("pawns") or []:
        cur, mx = _hp(p)
        if mx > 0 and cur < mx:
            return True
    return False


def army_wound_frac(army: dict) -> float:
    """Fraction of the army's max hp that is missing (0.0 = full, 1.0 = empty)."""
    total_max = total_cur = 0
    for p in army.get("pawns") or []:
        cur, mx = _hp(p)
        total_max += mx
        total_cur += min(cur, mx)
    if total_max <= 0:
        return 0.0
    return (total_max - total_cur) / total_max
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_army_health.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/army_health.py tests/test_army_health.py
git commit -m "feat(farming): army-health helpers (wounded detection)"
```

---

### Task 2: `move_cell_army` action

**Files:**
- Modify: `nta_agent/execution/actions.py` (add after `occupy_cell`, ~line 300)
- Test: `tests/test_move_cell_army.py`

**Interfaces:**
- Consumes: `GameSession.request` (already used by other actions)
- Produces: `Actions.move_cell_army(armies: list[dict], target: int, *, same_speed: bool = False) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_move_cell_army.py
from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self):
        self.state = GameState(source="api")
        self.sent = []

    def request(self, route, params):
        self.sent.append((route, params))
        return {}


def test_move_cell_army_builds_request():
    s = FakeSession()
    a = Actions(session=s)
    a.move_cell_army([{"index": 10, "uid": "u1"}, {"index": 11, "uid": "u2"}], target=42)
    route, params = s.sent[-1]
    assert route == "game/HD_MoveCellArmy"
    assert params == {"indexs": [10, 11], "uids": ["u1", "u2"], "target": 42, "isSameSpeed": False}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_move_cell_army.py -q`
Expected: FAIL (`AttributeError: move_cell_army`).

- [ ] **Step 3: Write minimal implementation**

```python
# in nta_agent/execution/actions.py, inside class Actions (after occupy_cell)
    def move_cell_army(
        self,
        armies: list[dict],
        target: int,
        *,
        same_speed: bool = False,
    ) -> dict:
        """March ``armies`` to ``target`` without attacking (GAME_HD_MoveCellArmy).

        Used to route wounded armies to a fort/city to heal. ``armies`` are
        AreaArmyInfo dicts (need ``index`` and ``uid``).
        """
        indexs = [int(a["index"]) for a in armies]
        uids = [str(a["uid"]) for a in armies]
        reply = self.session.request("game/HD_MoveCellArmy", {
            "indexs": indexs, "uids": uids, "target": int(target),
            "isSameSpeed": bool(same_speed),
        })
        self._apply_result(reply)
        return reply
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_move_cell_army.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/actions.py tests/test_move_cell_army.py
git commit -m "feat(farming): move_cell_army action (HD_MoveCellArmy)"
```

---

### Task 3: Heal-node selection helper

**Files:**
- Modify: `nta_agent/execution/army_health.py`
- Test: `tests/test_heal_nodes.py`

**Interfaces:**
- Consumes: `army_is_wounded` (Task 1); `Territory` (`nta_agent/execution/territory.py`) with `.main_city`, `.forts[].index`, `.dist(a, b)`
- Produces: `nearest_heal_node(army_index: int, territory, occupancy: dict[int, int], capacity: int) -> int | None`

`occupancy` maps a node index → number of armies currently stationed there. A node is eligible when `occupancy.get(node, 0) < capacity`. Returns the nearest eligible node index (Manhattan via `territory.dist`), or None.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_heal_nodes.py
from nta_agent.execution.army_health import nearest_heal_node
from nta_agent.execution.territory import Fort, Territory


def _terr():
    # main city at index for (100,100); one fort at (110,100). map 600 wide.
    return Territory(main_city=100 * 600 + 100,
                     forts=[Fort(index=100 * 600 + 110, auto_support=True)],
                     garrisons=[], map_width=600)


def test_picks_nearest_eligible_node():
    t = _terr()
    # army at (100,105): main is dist 5, fort is dist 10 -> main wins
    n = nearest_heal_node(105 * 600 + 100, t, occupancy={}, capacity=5)
    assert n == 100 * 600 + 100


def test_skips_full_node():
    t = _terr()
    # main full -> fall back to fort even if farther
    full = {100 * 600 + 100: 5}
    n = nearest_heal_node(105 * 600 + 100, t, occupancy=full, capacity=5)
    assert n == 100 * 600 + 110


def test_none_when_all_full():
    t = _terr()
    full = {100 * 600 + 100: 5, 100 * 600 + 110: 5}
    assert nearest_heal_node(105 * 600 + 100, t, occupancy=full, capacity=5) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_heal_nodes.py -q`
Expected: FAIL (`ImportError: nearest_heal_node`).

- [ ] **Step 3: Write minimal implementation**

```python
# append to nta_agent/execution/army_health.py

def nearest_heal_node(army_index, territory, occupancy, capacity):
    """Nearest heal node (main city or a fort) with a free army slot, or None.

    ``territory`` is a Territory (main_city index + forts). ``occupancy`` maps a
    node index to how many armies sit there now; a node is eligible while
    occupancy < capacity.
    """
    nodes = [territory.main_city] + [f.index for f in territory.forts]
    eligible = [n for n in nodes if n and occupancy.get(n, 0) < capacity]
    if not eligible:
        return None
    return min(eligible, key=lambda n: territory.dist(army_index, n))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_heal_nodes.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/army_health.py tests/test_heal_nodes.py
git commit -m "feat(farming): nearest_heal_node selection"
```

---

### Task 4: `HealRouting` rule

**Files:**
- Modify: `nta_agent/execution/heuristics.py` (add rule class near `ClaimTreasures`)
- Test: `tests/test_heal_routing.py`

**Interfaces:**
- Consumes: `army_is_wounded`, `army_wound_frac`, `nearest_heal_node` (Tasks 1/3); `build_territory(state)` (`territory.py`); `Actions.get_player_armys()`, `Actions.move_cell_army()` (Task 2)
- Produces: `HealRouting` dataclass rule (`name="heal_routing"`) implementing the `Rule` protocol

Behaviour: on `applies`, throttle (`check_every` ticks) then fetch armies via `get_player_armys()`. An army is a **heal candidate** when `army_is_wounded(a)` and it is **not already stationed at a heal node** (`a["index"]` not in node set). Occupancy = count of armies whose `index` is a node. Pick candidates with the highest `army_wound_frac` first; for each (up to `max_route_per_tick`) find `nearest_heal_node`; stash `(army, node)` pairs. `act` issues one `move_cell_army([army], node)` per pair.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_heal_routing.py
from nta_agent.execution.heuristics import HealRouting
from nta_agent.state.schema import GameState, User


def _state(main, forts):
    st = GameState(source="api")
    st.user = User(uid="me")
    st.main_city_index = main
    st.raw = {"player": {"mainCityIndex": main, "fortAutoSupports": forts}}
    return st


class FakeActions:
    def __init__(self, armies):
        self._armies = armies
        self.moved = []

    def get_player_armys(self):
        return self._armies

    def move_cell_army(self, armies, target, **kw):
        self.moved.append(([a["uid"] for a in armies], target))
        return {}


def test_routes_wounded_army_to_main():
    main = 100 * 600 + 100
    st = _state(main, forts=[])
    # one wounded army stationed away at (105,100), one healthy at home
    armies = [
        {"index": 105 * 600 + 100, "uid": "hurt", "pawns": [{"hp": [10, 100]}]},
        {"index": main, "uid": "ok", "pawns": [{"hp": [100, 100]}]},
    ]
    acts = FakeActions(armies)
    rule = HealRouting(check_every=0, fort_capacity=5)
    assert rule.applies(st, acts) is True
    rule.act(acts)
    assert acts.moved == [(["hurt"], main)]


def test_no_action_when_all_healthy():
    main = 100 * 600 + 100
    st = _state(main, forts=[])
    armies = [{"index": main, "uid": "ok", "pawns": [{"hp": [100, 100]}]}]
    acts = FakeActions(armies)
    rule = HealRouting(check_every=0)
    assert rule.applies(st, acts) is False


def test_skips_army_already_at_heal_node():
    main = 100 * 600 + 100
    st = _state(main, forts=[])
    # wounded but already sitting at the main city -> already healing, don't move
    armies = [{"index": main, "uid": "healing", "pawns": [{"hp": [10, 100]}]}]
    acts = FakeActions(armies)
    rule = HealRouting(check_every=0)
    assert rule.applies(st, acts) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_heal_routing.py -q`
Expected: FAIL (`ImportError: HealRouting`).

- [ ] **Step 3: Write minimal implementation**

```python
# in nta_agent/execution/heuristics.py (import near the top-of-file imports)
# from nta_agent.execution.army_health import (
#     army_is_wounded, army_wound_frac, nearest_heal_node)
# from nta_agent.execution.territory import build_territory

@dataclass
class HealRouting:
    """Route wounded armies to the nearest fort/city to heal (passive server-side).

    Best-effort: keeps farming armies healthy so the occupy loop never stalls on
    weakened troops. Heal itself is automatic while an army sits at a fort/city;
    this rule only does the routing.
    """
    name: str = "heal_routing"
    fort_capacity: int = 5      # armies a heal node holds (maxArmyCount; refine live)
    check_every: int = 4        # ticks between get_player_armys() sweeps
    max_route_per_tick: int = 1
    on_event: object = None
    _cooldown: int = 0
    _pending: object = None

    def applies(self, state: GameState, actions: Actions) -> bool:
        if not state.main_city_index:
            return False
        if self._cooldown > 0:
            self._cooldown -= 1
            return False
        from nta_agent.execution.army_health import (
            army_is_wounded, army_wound_frac, nearest_heal_node)
        from nta_agent.execution.territory import build_territory
        armies = actions.get_player_armys()
        self._cooldown = self.check_every
        terr = build_territory(state)
        nodes = {terr.main_city} | {f.index for f in terr.forts}
        occupancy: dict[int, int] = {}
        for a in armies:
            idx = int(a.get("index", 0) or 0)
            if idx in nodes:
                occupancy[idx] = occupancy.get(idx, 0) + 1
        candidates = [a for a in armies
                      if army_is_wounded(a) and int(a.get("index", 0) or 0) not in nodes]
        candidates.sort(key=army_wound_frac, reverse=True)
        pending = []
        for a in candidates[: self.max_route_per_tick]:
            node = nearest_heal_node(int(a["index"]), terr, occupancy, self.fort_capacity)
            if node is None:
                continue
            occupancy[node] = occupancy.get(node, 0) + 1  # reserve the slot
            pending.append((a, node))
        self._pending = pending
        if pending and self.on_event:
            self.on_event("heal_routing", {"count": len(pending),
                                           "armies": [a.get("uid") for a, _ in pending]})
        return bool(pending)

    def act(self, actions: Actions) -> None:
        for army, node in self._pending or []:
            actions.move_cell_army([army], node)
        self._pending = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_heal_routing.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/heuristics.py tests/test_heal_routing.py
git commit -m "feat(farming): HealRouting rule (route wounded armies to fort/city)"
```

---

### Task 5: Wire `HealRouting` into the default engine

**Files:**
- Modify: `nta_agent/execution/heuristics.py` (`RuleEngine.default`)
- Test: `tests/test_rule_engine_default.py` (create if absent; otherwise add a case)

**Interfaces:**
- Consumes: `HealRouting` (Task 4)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rule_engine_default.py
from nta_agent.execution.heuristics import HealRouting, OccupyCell, RuleEngine


def test_default_has_heal_routing_before_occupy():
    eng = RuleEngine.default()
    names = [type(r).__name__ for r in eng.rules]
    assert "HealRouting" in names
    assert names.index("HealRouting") < names.index("OccupyCell")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_rule_engine_default.py -q`
Expected: FAIL (HealRouting not in default rules).

- [ ] **Step 3: Write minimal implementation**

```python
# in RuleEngine.default, insert HealRouting() before OccupyCell(...)
        return cls(rules=[CollectCityOutput(), BuildOrder(profile=profile),
                          Recruit(profile=profile),
                          HealRouting(),
                          OccupyCell(use_sim=True, profile=profile),
                          ClaimTreasures(), ClaimTasks()])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_rule_engine_default.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/heuristics.py tests/test_rule_engine_default.py
git commit -m "feat(farming): wire HealRouting into RuleEngine.default"
```

---

### Task 6: Stamina pacing from config (lightweight)

**Files:**
- Modify: `nta_agent/execution/occupy_planner.py` (add helper)
- Modify: `nta_agent/execution/heuristics.py` (`OccupyCell` uses it)
- Test: `tests/test_occupy_rule.py` (add a pacing case)

**Interfaces:**
- Produces: `min_occupy_stamina(config) -> int` (min `need_stamina` across occupiable lands, floor 1)

Rationale: `OccupyCell.applies` already returns early when `stamina < min_stamina` (default 1). This task makes that floor **config-derived** so a future land with higher cost still paces correctly, and asserts discovery is skipped when stamina is short (no wasted `get_area` probes).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_occupy_rule.py
def test_occupy_skips_discovery_when_stamina_below_min():
    from nta_agent.execution.heuristics import OccupyCell
    from nta_agent.state.schema import GameState, User

    st = GameState(source="api")
    st.user = User(uid="me")
    st.main_city_index = 100 * 600 + 100
    st.resources.stamina = 0

    calls = []

    class Acts:
        def get_area(self, i, **kw):
            calls.append(i)
            return {"data": {}}

    rule = OccupyCell(min_stamina=1)
    assert rule.applies(st, Acts()) is False
    assert calls == []          # no discovery probes when stamina is short
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_occupy_rule.py::test_occupy_skips_discovery_when_stamina_below_min -q`
Expected: PASS already (the min_stamina gate exists) — this **locks in** the pacing behaviour so a later refactor can't regress it. If it fails, fix the gate first.

- [ ] **Step 3: Add the config helper + wire the floor**

```python
# nta_agent/execution/occupy_planner.py
def min_occupy_stamina(config: GameConfig) -> int:
    """Cheapest occupy stamina cost across occupiable lands (floor 1)."""
    costs = [int(row.get("need_stamina", 0) or 0)
             for row in config.table("landAttr").values()
             if row.get("occupy") or True]  # landAttr rows are all occupiable tiers
    costs = [c for c in costs if c > 0]
    return min(costs) if costs else 1
```

```python
# in the runner where OccupyCell is constructed (nta_agent/runtime/runner.py),
# set min_stamina from config when a GameConfig is available:
#   OccupyCell(..., min_stamina=min_occupy_stamina(config))
# Leave the default (1) when no config is loaded.
```

- [ ] **Step 4: Run the occupy tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_occupy_rule.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/occupy_planner.py nta_agent/execution/heuristics.py nta_agent/runtime/runner.py tests/test_occupy_rule.py
git commit -m "feat(farming): config-derived stamina pacing for occupy"
```

---

### Task 7: Full suite + live verification

**Files:** none (verification + notes).

- [ ] **Step 1: Full suite + lint**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check nta_agent tests`
Expected: all green.

- [ ] **Step 2: Live verify on the emulator (answers the spec's open questions)**

Confirm on the running game (via dashboard/logs) and adjust constants if needed:
1. **Pawn hp field** — does a real army dict carry `pawns[].hp = [cur, max]`? If the key differs, update `army_health._hp`.
2. **`autoBackType`** — does occupy already auto-return armies to the city (where they heal)? If yes, HealRouting mainly matters for armies left stationed at forts; note it, keep the rule.
3. **Main city heals** like a fort? If not, drop `main_city` from heal nodes and rely on forts only.
4. **Heal timing** — hp restores over time vs instant; tune `check_every` so re-dispatch isn't premature.
5. **Fort capacity** — confirm `maxArmyCount` (≈5) from `buildMaster`/live; update `HealRouting.fort_capacity`.

- [ ] **Step 3: Record findings**

Update `docs/re/game-api.md` (MoveCellArmy/autoBackType shapes → mark ✅ once verified) and the spec's §8 with the answers. Commit any constant adjustments.

- [ ] **Step 4: Finish the branch**

Use superpowers:finishing-a-development-branch (tests green → PR → merge per the usual flow).

---

## Self-Review
- **Spec coverage:** state hp parsing (Task 1), HealRouting (Tasks 3–4), wiring (Task 5), stamina pacing (Task 6), live verify (Task 7). ✔
- **Placeholder scan:** none — every code step has concrete content.
- **Type consistency:** `nearest_heal_node(army_index, territory, occupancy, capacity)` signature identical in Task 3 impl/test and Task 4 caller; `move_cell_army(armies, target, *, same_speed)` identical in Task 2 and Task 4.
- **Out of scope (spec §3):** revive-dead, Tonden — no tasks, intentionally.
