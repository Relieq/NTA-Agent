# Formation Optimizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-arrange each tank/melee army's formation (which pawn stands in front) so the beefiest pawn absorbs damage — minimizing deaths and spreading damage — before the occupy is issued.

**Architecture:** Enemies target the closest pawn, so front position decides who tanks. The sim already respects per-pawn grid points (proven by spike). A pure `formation` module generates candidate pawn→slot assignments (permuting pawns among the slots they already occupy); the sim scores each (per-pawn survival); the best is applied via `HD_MoveAreaPawns` before occupy. Wires into Phase 1's `OccupyCell` after `best_plan`.

**Tech Stack:** Python 3.12 (`.venv/Scripts/python.exe`), Node ≥18 sidecar, pytest, `node --test --test-force-exit`, ruff.

**Spec:** `docs/superpowers/specs/2026-09-13-formation-optimizer-design.md`

## Global Constraints

- Lint: `ruff check nta_agent tests`. Node tests need `--test-force-exit`.
- Camps: 2 = ours, 1 = enemy. Melee = NOT archer (order_strategies.is_archer_army); archer id 33xx.
- Route strings exact: `game/HD_MoveAreaPawns`. Params: `{index:int, armyUid:str, pawns:[{uid:str, point:{x,y}}]}`.
- Determinism unchanged: `randSeed = floor(uid/100) + targetIndex`.
- Loop must never die: sim/move failures skip optimization; occupy still proceeds.
- Commit proactively at each green task; finish flow = push → PR → merge.

---

### Task 1: `move_area_pawns` action

**Files:**
- Modify: `nta_agent/execution/actions.py`
- Test: `tests/test_actions_move_pawns.py` (create)

**Interfaces:**
- Produces: `Actions.move_area_pawns(index:int, army_uid:str, assignment:dict[str, dict]) -> dict` where `assignment` maps `pawn_uid -> {"x":int,"y":int}`; sends `game/HD_MoveAreaPawns` with `pawns=[{"uid":u,"point":p} for u,p in assignment.items()]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_actions_move_pawns.py
from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self, reply=None):
        self.state = GameState(source="api"); self.state.raw = {}
        self._reply = reply or {}
        self.sent = []
    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params)); return self._reply


def test_move_area_pawns_sends_route_and_pawns():
    s = FakeSession()
    Actions(s).move_area_pawns(109725, "army1", {"p1": {"x": 6, "y": 7}, "p2": {"x": 9, "y": 7}})
    route, params = s.sent[0]
    assert route == "game/HD_MoveAreaPawns"
    assert params["index"] == 109725 and params["armyUid"] == "army1"
    assert {"uid": "p1", "point": {"x": 6, "y": 7}} in params["pawns"]
    assert {"uid": "p2", "point": {"x": 9, "y": 7}} in params["pawns"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_actions_move_pawns.py -q`
Expected: FAIL (no `move_area_pawns`).

- [ ] **Step 3: Implement (after `get_battle_record` in actions.py)**

```python
    def move_area_pawns(self, index: int, army_uid: str, assignment: dict) -> dict:
        """Set the grid positions of an army's pawns (GAME_HD_MoveAreaPawns)."""
        pawns = [{"uid": str(u), "point": {"x": int(p["x"]), "y": int(p["y"])}}
                 for u, p in assignment.items()]
        return self.session.request("game/HD_MoveAreaPawns",
                                    {"index": int(index), "armyUid": str(army_uid), "pawns": pawns})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_actions_move_pawns.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/actions.py tests/test_actions_move_pawns.py
git commit -m "execution: move_area_pawns action (formation positioning)"
```

---

### Task 2: sim carries per-pawn points (sim_input + frames.js)

**Files:**
- Modify: `nta_agent/execution/predictors/sim_input.py`
- Modify: `tools/battlesim/frames.js`
- Test: `tests/test_sim_input.py` (extend); `tools/battlesim/test/frames.test.js` (extend)

**Interfaces:**
- `sim_input._pawn` includes `"point"` when the source pawn has one.
- `frames.js` `stripArmy` uses a pawn's provided `point` when present, else the army entry point.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sim_input.py (add)
def test_forecast_input_passes_pawn_point_when_present():
    from nta_agent.execution.predictors.sim_input import build_forecast_input
    from nta_agent.state.schema import GameState
    st = GameState(source="api"); st.raw = {}; st.user.uid = "1"
    armies = [{"uid": "a", "index": 1, "marchTime": 0,
               "pawns": [{"uid": "p1", "id": 3101, "lv": 1, "point": {"x": 6, "y": 7}}]}]
    out = build_forecast_input(st, armies, target_index=9, land_id=0, distance=1)
    assert out["armies"][0]["pawns"][0]["point"] == {"x": 6, "y": 7}
```

```js
// tools/battlesim/test/frames.test.js (add)
const { test: t2 } = require("node:test");
// (import buildFrames lazily inside the test; it needs the engine globals.)
```

Note: `buildFrames` needs engine globals (assetsMgr/mapHelper), so its point-honoring is covered by the Task 3 golden (which runs the engine), not a pure unit test. The pure test here is the Python one above; add a comment in frames.test.js pointing to the golden.

- [ ] **Step 2: Run the Python test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sim_input.py::test_forecast_input_passes_pawn_point_when_present -q`
Expected: FAIL (point not in output).

- [ ] **Step 3: Implement**

`sim_input.py` `_pawn`: add `"point"` when present:

```python
def _pawn(p):
    out = {
        "uid": p.get("uid"), "id": int(p.get("id", 0)), "lv": int(p.get("lv", 0) or 0),
        "hp": list(p["hp"]) if p.get("hp") else None,
        "buffs": p.get("buffs") or [], "skills": p.get("skills") or [],
        "treasures": p.get("treasures") or [], "hero": p.get("hero") or None,
    }
    if p.get("point"):
        out["point"] = p["point"]
    return out
```

`frames.js` `stripArmy` — honor provided point:

```js
      .map((p) => ({
        index: army.index, uid: p.uid, id: p.id, lv: p.lv,
        hp: p.hp ? (Array.isArray(p.hp) ? p.hp.slice() : [p.hp[0]]) : undefined,
        point: p.point ? { x: p.point.x, y: p.point.y } : { x: entry.x, y: entry.y },
        equip: p.equip, portrayal: p.hero || undefined,
        attackSpeed: pawnAttackSpeed(p.id), buffs: p.buffs || [],
      }));
```

- [ ] **Step 4: Run tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sim_input.py -q` → PASS.
Run: `node --test --test-force-exit tools/battlesim/test/frames.test.js` → arriveFrame still PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/predictors/sim_input.py tools/battlesim/frames.js tests/test_sim_input.py tools/battlesim/test/frames.test.js
git commit -m "sim: carry per-pawn points so formations reach the engine"
```

---

### Task 3: per-pawn survival from `reinforce.js` + formation golden

**Files:**
- Modify: `tools/battlesim/reinforce.js`
- Modify: `tools/battlesim/test/golden.test.js`

**Interfaces:**
- `runWithReinforce(...)` result adds `survivors.pawns = [{uid, camp, alive, curHp}]` for the whole starting roster (dead pawns: alive=false, curHp=0).

- [ ] **Step 1: Write the failing golden (formation matters)**

```js
// tools/battlesim/test/golden.test.js (add)
test("formation: beefy-front survives more than squishy-front", (t) => {
  const enginePath = process.env.NTA_ENGINE_JS || "tools/re/decrypted/index.js";
  if (!fs.existsSync(enginePath)) { t.skip("engine absent"); return; }
  const { loadEngine } = require("../bundle");
  const { installAssets } = require("../assets");
  const { runWithReinforce } = require("../reinforce");
  if (!globalThis.eventCenter) globalThis.eventCenter = { emit(){}, on(){}, off(){}, once(){} };
  if (!globalThis.mc) globalThis.mc = { getModel: () => ({}) };
  const req = loadEngine();
  installAssets(undefined, req, { playerUid: "1000000000" });
  const TARGET = 109725, SEED = Math.floor(1000000000 / 100) + TARGET;
  const run = (pts) => {
    const our = { index: 109726, uid: "tank", name: "T", owner: "1000000000", state: 2,
      pawns: [
        { index: TARGET, uid: "big", id: 3101, lv: 1, attackSpeed: 6, point: pts[0], hp: [200,200] },
        { index: TARGET, uid: "mid", id: 3101, lv: 1, attackSpeed: 6, point: pts[1], hp: [80,80] },
        { index: TARGET, uid: "sml", id: 3101, lv: 1, attackSpeed: 6, point: pts[2], hp: [50,50] }] };
    const enemy = { index: TARGET, uid: "e", name: "", owner: "", state: 2,
      pawns: Array.from({length:4},(_,i)=>({ index: TARGET, uid:"e"+i, id:4101, lv:1,
        attackSpeed:7, point:{x:4+(i%3),y:6+((i/3)|0)}, hp:[60,60] })) };
    let acc = 0; const f = [];
    for (const p of our.pawns) f.push({ uid:p.uid, camp:2, attackIndex:++acc, enterIndex:acc });
    for (const p of enemy.pawns) f.push({ uid:p.uid, camp:1, attackIndex:++acc, enterIndex:acc });
    return runWithReinforce({ target:TARGET, armys:[our,enemy], fighters:f, randSeed:SEED,
      fps:20, hp:[100,100], waves:[], selfTotal:3, enemyTotal:4 }, req);
  };
  const a = run([{x:6,y:7},{x:9,y:7},{x:10,y:7}]); // big front
  const b = run([{x:10,y:7},{x:9,y:7},{x:6,y:7}]); // small front
  assert.ok(a.survivors.self.alive > b.survivors.self.alive,
    `big-front (${a.survivors.self.alive}) should outlast small-front (${b.survivors.self.alive})`);
  assert.ok(Array.isArray(a.survivors.pawns) && a.survivors.pawns.length === 3);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `node --test --test-force-exit tools/battlesim/test/golden.test.js`
Expected: FAIL (`survivors.pawns` undefined).

- [ ] **Step 3: Implement per-pawn survival in `reinforce.js`**

In the `battleEndByLocal` hook, after computing `self`/`enemy`, build the roster survival. Add before `result = {...}`:

```js
      const roster = allFighters;  // {uid, camp} for every fighter that entered
      const aliveByUid = {};
      fs.forEach((f) => { if (f.getUid) aliveByUid[f.getUid()] = f; });
      const pawns = roster.map((r) => {
        const lf = aliveByUid[r.uid];
        return { uid: r.uid, camp: r.camp,
                 alive: !!(lf && lf.isDie && !lf.isDie()),
                 curHp: lf && lf.getCurHp ? lf.getCurHp() : 0 };
      });
```

and include `pawns` in `survivors`: `survivors: { self, enemy, pawns }`.
(`allFighters` is in scope in `runWithReinforce`; the hook is a closure over it. If not, capture a `roster` array of `{uid,camp}` when building `fighters` and reference that.)

- [ ] **Step 4: Run to verify it passes**

Run: `node --test --test-force-exit tools/battlesim/test/golden.test.js`
Expected: PASS (all goldens incl. the new formation one).

- [ ] **Step 5: Commit**

```bash
git add tools/battlesim/reinforce.js tools/battlesim/test/golden.test.js
git commit -m "battlesim: per-pawn survival in result; formation golden (front tank matters)"
```

---

### Task 4: surface per-pawn survival on the Python predictor

**Files:**
- Modify: `nta_agent/execution/predictors/sim_predictor.py`
- Test: `tests/test_sim_predictor_pawns.py` (create)

**Interfaces:**
- `SimBattlePredictor.predict_armies(...)` returns a `BattlePrediction` with an added attribute `pawn_survival: list[dict] | None` (from `res["survivors"]["pawns"]`), default None when absent.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sim_predictor_pawns.py
from nta_agent.execution.predictors.sim_predictor import SimBattlePredictor
from nta_agent.state.schema import GameState


class FakeBridge:
    def __init__(self, res): self._res = res
    def forecast(self, inp): return self._res
    def available(self): return True


def test_predict_armies_exposes_pawn_survival():
    res = {"isWin": True, "lossPercent": 10.0, "lossLv": 1,
           "survivors": {"self": {"alive": 2, "total": 3},
                         "pawns": [{"uid": "big", "camp": 2, "alive": True, "curHp": 150}]}}
    st = GameState(source="api"); st.raw = {}; st.user.uid = "1"
    p = SimBattlePredictor(bridge=FakeBridge(res))
    armies = [{"uid": "a", "index": 1, "pawns": [{"uid": "big", "id": 3101, "lv": 1}]}]
    pred = p.predict_armies(st, armies, target_index=9, land_id=0, distance=1)
    assert pred.win is True
    assert pred.pawn_survival == [{"uid": "big", "camp": 2, "alive": True, "curHp": 150}]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sim_predictor_pawns.py -q`
Expected: FAIL (`pawn_survival` missing).

- [ ] **Step 3: Implement**

`BattlePrediction` is a dataclass in `predictors/battle.py`. Add an optional field `pawn_survival: list | None = None` (default keeps all existing constructors working). In `sim_predictor.predict_armies`, set it from the result:

```python
        return BattlePrediction(
            win=bool(res.get("isWin")),
            my_power=my_power, enemy_power=enemy_power, ratio=ratio,
            loss_percent=float(res.get("lossPercent", 0.0) or 0.0),
            loss_lv=int(res.get("lossLv", 0) or 0),
            pawn_survival=((res.get("survivors") or {}).get("pawns")),
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sim_predictor_pawns.py -q` → PASS.
Also run `.venv/Scripts/python.exe -m pytest tests/test_advisor.py tests/test_occupy_rule.py -q` (BattlePrediction constructors unaffected) → PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/predictors/sim_predictor.py nta_agent/execution/predictors/battle.py tests/test_sim_predictor_pawns.py
git commit -m "predictors: expose per-pawn survival on BattlePrediction"
```

---

### Task 5: `formation.py` — candidate formations (pure)

**Files:**
- Create: `nta_agent/execution/formation.py`
- Test: `tests/test_formation.py`

**Interfaces:**
- `slot_order(army, target, map_width=600) -> list[dict]`: the army's occupied points ordered front→back (front = nearest the entry approach toward `target`).
- `candidate_formations(army, target, map_width=600) -> list[tuple[str, dict]]`: `[(label, {pawn_uid: point})]`. Labels: `beefy-front` (pawns by max-HP desc onto front→back slots) and `keep` (current). Single-pawn / homogeneous → `keep` only.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_formation.py
from nta_agent.execution.formation import candidate_formations, slot_order


def _pawn(uid, hp, pt):
    return {"uid": uid, "id": 3101, "lv": 1, "hp": [hp, hp], "point": pt}


def _army(pawns, index=100):
    return {"uid": "t", "index": index, "pawns": pawns}


def test_slot_order_front_to_back_toward_target():
    # target to the LEFT (smaller x): front = smaller x. slots at x=6 and x=10.
    army = _army([_pawn("a", 50, {"x": 10, "y": 7}), _pawn("b", 50, {"x": 6, "y": 7})], index=100)
    order = slot_order(army, target=98)  # target left of index -> front is smaller x
    assert order[0]["x"] == 6 and order[1]["x"] == 10


def test_beefy_front_puts_highest_hp_on_front_slot():
    army = _army([_pawn("big", 200, {"x": 10, "y": 7}), _pawn("sml", 50, {"x": 6, "y": 7})], index=100)
    plans = dict(candidate_formations(army, target=98))
    assert "beefy-front" in plans and "keep" in plans
    # front slot is x=6; big (200hp) must be assigned there
    assert plans["beefy-front"]["big"] == {"x": 6, "y": 7}
    assert plans["beefy-front"]["sml"] == {"x": 10, "y": 7}


def test_single_pawn_is_keep_only():
    army = _army([_pawn("solo", 50, {"x": 6, "y": 7})])
    labels = [lbl for lbl, _ in candidate_formations(army, target=98)]
    assert labels == ["keep"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_formation.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# nta_agent/execution/formation.py
"""Candidate formations for a melee army: which pawn stands in front (tanks).

Enemies target the closest pawn, so the front slot draws fire. We permute pawns
among the slots they already occupy — putting the beefiest pawn in front — and
let the sim score the options.
"""
from __future__ import annotations


def _max_hp(pawn: dict) -> int:
    hp = pawn.get("hp")
    if isinstance(hp, (list, tuple)) and hp:
        return int(hp[-1] if len(hp) > 1 else hp[0])
    if isinstance(hp, dict):
        return int(hp.get("1", hp.get("0", 0)))
    return 0


def slot_order(army: dict, target: int, map_width: int = 600) -> list[dict]:
    """Occupied slots ordered front->back (front = nearer the target approach)."""
    pts = [p["point"] for p in army.get("pawns", []) if p.get("point")]
    ai = int(army.get("index", 0))
    dx = (target % map_width) - (ai % map_width)
    dy = (target // map_width) - (ai // map_width)
    # Front = toward the target: sort by the coordinate that decreases distance.
    if abs(dx) >= abs(dy):
        key = (lambda pt: pt["x"]) if dx < 0 else (lambda pt: -pt["x"])
    else:
        key = (lambda pt: pt["y"]) if dy < 0 else (lambda pt: -pt["y"])
    return sorted(pts, key=key)


def candidate_formations(army: dict, target: int, map_width: int = 600):
    """[(label, {pawn_uid: point})]: beefy-front + keep; keep-only when trivial."""
    pawns = army.get("pawns") or []
    keep = {p["uid"]: p["point"] for p in pawns if p.get("point")}
    out = [("keep", keep)]
    if len(pawns) < 2:
        return [("keep", keep)]
    slots = slot_order(army, target, map_width)
    ranked = sorted(pawns, key=_max_hp, reverse=True)  # beefiest first
    beefy = {p["uid"]: slots[i] for i, p in enumerate(ranked) if i < len(slots)}
    if beefy and beefy != keep:
        out.insert(0, ("beefy-front", beefy))
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_formation.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/formation.py tests/test_formation.py
git commit -m "execution: candidate formations (beefy pawn to the front slot)"
```

---

### Task 6: Wire formation optimization into OccupyCell

**Files:**
- Modify: `nta_agent/execution/heuristics.py` (`OccupyCell`)
- Test: `tests/test_occupy_rule.py` (extend)

**Interfaces:**
- After `best_plan`, for each melee army in `plan.armies`, pick the formation with the fewest deaths (tie → smallest max single-pawn hp loss), apply `actions.move_area_pawns(army.index, army.uid, assignment)`, emit `formation_plan{army, label, loss_percent}`; then occupy. Sim off / no gain → skip apply.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_occupy_rule.py (add)
class FormationSim:
    """predict_armies loss depends on whether 'big' pawn sits at the front slot (x=6)."""
    def predict_armies(self, state, armies, *, target_index, land_id, distance, **kw):
        from nta_agent.execution.predictors.battle import BattlePrediction
        pawns = [p for a in armies for p in a.get("pawns", [])]
        big = next((p for p in pawns if p["uid"] == "big"), None)
        front = big and big.get("point", {}).get("x") == 6
        loss = 0.0 if front else 50.0
        pred = BattlePrediction(win=True, my_power=1, enemy_power=1, ratio=1,
                                loss_percent=loss, loss_lv=0)
        pred.pawn_survival = [{"uid": p["uid"], "camp": 2, "alive": front or p["uid"] == "big",
                               "curHp": 100} for p in pawns]
        return pred


def test_occupy_optimizes_formation_before_attack():
    center = 182 * W + 526
    st = GameState(source="api"); st.user.uid = "me"; st.main_city_index = center
    st.resources.stamina = 10
    areas = {center: _cell(owner="me", city=1001),
             center - 1: _cell(owner="", pawns=[50])}
    # a melee army whose 'big' pawn currently sits at the BACK slot (x=10)
    tank = {"index": center, "uid": "tank",
            "pawns": [{"uid": "big", "id": 3101, "lv": 1, "hp": [200, 200], "point": {"x": 10, "y": 7}},
                      {"uid": "sml", "id": 3101, "lv": 1, "hp": [50, 50], "point": {"x": 6, "y": 7}}]}
    moves = []
    class Acts(FakeActions):
        def move_area_pawns(self, index, army_uid, assignment):
            moves.append((index, army_uid, assignment)); return {}
    act = Acts(areas=areas, armies=[tank])
    events = []
    rule = OccupyCell(radius=1, use_sim=True, sim=FormationSim(),
                      predictor=BattlePredictor(), on_event=lambda k, d: events.append((k, d)))
    assert rule.applies(st, act) is True
    rule.act(act)
    # optimizer moved 'big' to the front slot x=6
    assert moves and moves[0][2]["big"] == {"x": 6, "y": 7}
    assert any(k == "formation_plan" for k, d in events)
    assert act.calls and act.calls[0][0] == "occupy"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_occupy_rule.py::test_occupy_optimizes_formation_before_attack -q`
Expected: FAIL (no formation optimization / no move call).

- [ ] **Step 3: Implement in `OccupyCell`**

Add a helper and call it from `act` (formations are applied just before occupy, after the plan is chosen in `applies`). Store the chosen plan's armies in `_pending` (already the case). In `act`, before `occupy_cell`, optimize each melee army:

```python
    def _optimize_formations(self, actions, armies, target):
        from nta_agent.execution.formation import candidate_formations
        from nta_agent.execution.order_strategies import is_archer_army
        from nta_agent.execution.predictors.sim_bridge import SimUnavailable
        sim = self._sim_pred()
        if sim is None:
            return
        for army in armies:
            if is_archer_army(army) or len(army.get("pawns") or []) < 2:
                continue
            cands = candidate_formations(army, target)
            if len(cands) < 2:
                continue

            def score(assignment):
                posed = dict(army)
                posed["pawns"] = [{**p, "point": assignment.get(p["uid"], p.get("point"))}
                                  for p in army["pawns"]]
                try:
                    pred = sim.predict_armies(
                        self._state_ref, [posed], target_index=target,
                        land_id=self._land_ref, distance=self._dist(self._state_ref.main_city_index, target))
                except SimUnavailable:
                    return None
                if pred is None or not pred.win:
                    return None
                surv = pred.pawn_survival or []
                worst = max((100 - s.get("curHp", 0) for s in surv if s.get("camp") == 2), default=0)
                return (pred.loss_percent, worst)

            best = None
            for label, assignment in cands:
                sc = score(assignment)
                if sc is None:
                    continue
                if best is None or sc < best[0]:
                    best = (sc, label, assignment)
            if best is None:
                continue
            _sc, label, assignment = best
            cur = {p["uid"]: p.get("point") for p in army["pawns"]}
            if assignment == cur:
                continue
            try:
                actions.move_area_pawns(army["index"], army["uid"], assignment)
                if self.on_event:
                    self.on_event("formation_plan", {"army": army.get("name") or army.get("uid"),
                                                     "label": label, "loss_percent": round(_sc[0], 1)})
            except Exception:
                pass  # never block the occupy
```

Store `self._state_ref = state` and `self._land_ref = <candidate land_id>` in `applies` (the chosen plan's target candidate) so `act` can re-run the sim; and call the optimizer in `act`:

```python
    def act(self, actions):
        if not self._pending:
            return
        armies, target = self._pending
        self._pending = None
        self._optimize_formations(actions, armies, target)
        try:
            actions.occupy_cell(target, armies)
        except Exception:
            self._cooldown = self.fail_cooldown
            raise
```

In `applies`, when setting `_pending`, also stash context: `self._state_ref = state` and `self._land_ref = cand_by_index[plan.target].land_id`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_occupy_rule.py -q`
Expected: PASS (existing occupy tests + the new formation test). The existing tests use single-pawn or non-point armies → optimizer skips (len<2 or archer), so they are unaffected.

- [ ] **Step 5: Full suite + lint + node**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check nta_agent tests`
Run: `node --test --test-force-exit tools/battlesim/test/golden.test.js`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add nta_agent/execution/heuristics.py tests/test_occupy_rule.py
git commit -m "occupy: optimize melee formation (beefy-front) via sim before attack"
```

---

## Self-Review

**Spec coverage:** §3/§5 optimizer → Tasks 5,6. MoveAreaPawns action → Task 1. per-pawn points → Task 2. per-pawn survival → Tasks 3,4. wiring/emit → Task 6. §8 tests: formation golden → Task 3; formation.py pure → Task 5; move action → Task 1; OccupyCell fake-sim → Task 6; sim-unavailable skip → Task 6 Step 3 (sim None → return). All covered.

**Placeholder scan:** No TBD/TODO; each step has runnable commands or real code.

**Type consistency:** `move_area_pawns(index, army_uid, assignment: {uid->point})` (Task 1) consumed in Task 6. `candidate_formations -> [(label, {uid:point})]` (Task 5) consumed in Task 6. `pawn_survival` on BattlePrediction (Task 4) read in Task 6 `score`. `survivors.pawns` (Task 3) feeds Task 4. `slot_order` front=nearest target used consistently.

**Residual risk (Task 6/spec §4):** whether `HD_MoveAreaPawns` accepts a permutation of existing points for a pre-march army is validated live, not in unit tests; the wiring wraps the call in try/except so a rejection never blocks occupy (optimizer degrades to a no-op / feed note). Confirm on the live emulator after merge.
