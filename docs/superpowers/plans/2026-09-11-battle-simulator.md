# Battle Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Predict occupy/attack outcomes by running the game's *own* battle engine headless in a Node sidecar, matching the in-game forecast exactly.

**Architecture:** A Node process loads the decrypted battle modules (`FSPBattleController`/`FSPModel`/`Fighter`/…) with a minimal Cocos shim and a reconstructed `area/gameHpr/mapHelper` graph, runs `battleLocalBegin({forecast:true})` with the client's deterministic seed, and returns `{isWin, lossLv, lossPercent}`. Python talks to it over JSON-RPC/stdio and maps the result into the existing `BattlePrediction`, with the scalar stats predictor as fallback.

**Tech Stack:** Python 3.12 (pytest, ruff), Node.js (≥18, plain JS, no build step), the decrypted `tools/re/decrypted/index.js`, config tables in `nta_agent/data/config/*.json`.

**Spec:** `docs/superpowers/specs/2026-09-11-battle-simulator-design.md`

## Global Constraints

- Python 3.12; lint with `ruff`; test with `pytest`. All new code passes `ruff check` clean.
- Node.js plain JS only — no bundler/transpile step; the sidecar runs `node tools/battlesim/server.js` directly.
- **Never commit sensitive artifacts.** `tools/re/decrypted/index.js`, `nta_agent/data/config/*.json`, and the XXTEA key are gitignored and stay so. The harness reads them at runtime **by path**; it must not embed or copy them into committed files. Only `tools/battlesim/*.js` (harness code) and Python/tests are committed.
- The decrypted engine seed formula is fixed: `randSeed = Math.floor(Number(playerUid) / 100) + areaIndex`.
- The autonomous loop must never crash because the simulator is missing or errors: every sim failure falls back to `BattlePredictor.from_stats`.
- Paths the harness reads (make them configurable via env, with these defaults):
  - `NTA_ENGINE_JS` → `tools/re/decrypted/index.js`
  - `NTA_CONFIG_DIR` → `nta_agent/data/config`
- Existing predictor interface to preserve: `predict(my_pawns, enemy_pawns) -> BattlePrediction` and a `pawn_power(pawn) -> float` attribute. `BattlePrediction` fields: `win, my_power, enemy_power, ratio, loss_percent, loss_lv`.

---

### Task 1: Feasibility gate — boot the engine headless, run one battle (DISCOVERY)

This task is reverse-engineering, not pre-writable code. Its deliverable is a
working `forecast.js` that produces a real `{isWin, lossLv, lossPercent}` for
one known matchup, plus a golden test locking that result. **If the object
graph proves too deep to reconstruct, STOP and report to the user — do not
substitute a heuristic.**

**Files:**
- Create: `tools/battlesim/cc-shim.js`
- Create: `tools/battlesim/bundle.js`
- Create: `tools/battlesim/assets.js`
- Create: `tools/battlesim/area-factory.js`
- Create: `tools/battlesim/forecast.js`
- Create: `tools/battlesim/run-once.js` (throwaway CLI harness for bring-up)
- Create: `tools/battlesim/test/golden.test.js` (plain `node --test`)

**Interfaces:**
- Consumes: decrypted `index.js` registry (`window.__require({Name:[fn,deps]})`); config JSON via `assetsMgr.getJsonData(table, id)`.
- Produces:
  - `bundle.js` exports `loadEngine(engineJsPath) -> requireByName(name)`.
  - `assets.js` exports `installAssets(configDir)` (sets global `assetsMgr`, `gameHpr`, `mapHelper` reusing bundle generators where possible).
  - `area-factory.js` exports `buildArea(input) -> {area, selectArmys, targetCell}` where `input` is the Forecast Input Schema (below).
  - `forecast.js` exports `forecast(input) -> {isWin:boolean, lossLv:number, lossPercent:number, timeMs:number, survivors:{self:{alive,total}, enemy:{alive,total}}}`.

**Forecast Input Schema** (the contract every later task marshals to):
```js
{
  playerUid: "1234567890",          // string; drives seed
  targetCellIndex: 109725,          // int; area.index
  landId: 0,                        // int; target cell land type
  selfToCellDistance: 1,            // int; steps from player's nearest owned cell
  areaSize: <int|null>,             // null -> engine DEFAULT_AREA_SIZE
  armies: [                         // our attacking armies (usually one)
    { uid, name, index,             // index = the owned cell we attack FROM
      marchTime: 0,
      pawns: [ { uid, id, lv, hp:[cur,max], buffs:[], skills:[], treasures:[],
                 hero:<obj|null> } ] }
  ],
  enemyArmyConf: <obj|null>         // null -> engine generates via getAreaPawnConfInfo
}
```

- [ ] **Step 1: Bundle loader.** Write `bundle.js`: read `engineJsPath`, provide a `window` global, `eval` the file to capture the registry function, and return a `requireByName(name)` that resolves modules by their registry key (last path segment). Verify by requiring `RandomObj` and asserting `new (requireByName('RandomObj').default)(7).numn()` is deterministic (same value on repeat with a fresh seed 7). Run: `node -e "..."`. Expected: identical numbers.

- [ ] **Step 2: Cocos shim (seed).** Write `cc-shim.js` defining the minimum `cc` global to let a battle module load: `cc._RF.push/pop` (no-ops that accept args), `cc.log`/`cc.warn` (→ stderr), `cc.v2(x,y)`/`cc.Vec2` with the methods the code calls (`set2`, `sub`, `add`, `clone`, `x`/`y`), `cc.Enum` (identity). Load it before `bundle.js`. Verify `requireByName('Fighter')` and `requireByName('FSPBattleController')` load without throwing. Run: `node tools/battlesim/run-once.js --probe`. Expected: "modules loaded".

- [ ] **Step 3: Assets + gameHpr/mapHelper.** Write `assets.js`: `installAssets(configDir)` builds `global.assetsMgr.getJsonData(table, id)` reading `<configDir>/<table>.json` (cache parsed files; tables are arrays keyed by `id`, except `pawnAttr` keyed by `id*1000+lv`). Wire `global.gameHpr` and `global.mapHelper` to reuse the bundle's own helpers where the code path calls them (`getPassPoints`, `getAddArmyDir`, `getBattlePoints`, `getAreaPawnConfInfo`, `getPawnCost`), stubbing only leaf player-context accessors (`getUid` → input.playerUid, `getPlayerInfo` → `{}`, distance helpers). Iterate: run the probe, read the "X is not a function/undefined" error, add exactly that accessor, repeat.

- [ ] **Step 4: Area factory.** Write `area-factory.js`: given a Forecast Input, replicate the forecast setup read from `index.js` lines ~24680–24800 — build our army strip (`toArmyStrip`), enemy via `getEnemyArmys(enemyArmyConf, firstPawnPoint, [])`, construct `area = new AreaModel().init({index, owner:"", hp, cityId:0, armys})`. Return `{area, selectArmys, targetCell}`. Verify no throw for the known matchup input (pawn 3101 vs a low-index NPC cell). Run the probe.

- [ ] **Step 5: Forecast driver.** Write `forecast.js`: set `randSeed = Math.floor(Number(playerUid)/100) + targetCellIndex`, call `area.battleLocalBegin({camp:1, randSeed, accAttackIndex:0, fps:FPS, fighters, mul:FPS_MUL, forecast:true})`, then loop `area.getFspModel().update(dt)` (fixed `dt = 1000/FPS`) until the engine settles (reuse its own end path — `onPlaybackEnd`/`settleResult`/`onComplete` set a result; capture it via the callback the engine already calls). Extract `{isWin, lossLv, lossPercent, timeMs, survivors}` exactly as `onComplete` computes them. Add a hard frame cap (e.g. `AUTO_MAX_TIME`) to avoid infinite loops.

- [ ] **Step 6: Run the known matchup.** `node tools/battlesim/run-once.js` with a hardcoded input: our pawn `3101` lv1 attacking an NPC-defended cell (`4101` defenders) one step away. Print the result JSON. Expected: a plausible `{isWin, lossLv, lossPercent}` (given 3101 lv1 hp135/atk10 vs 4101 lv1 hp25/atk13, we expect `isWin:true`, low `lossLv`). **This is the feasibility gate.**

- [ ] **Step 7: Golden test.** Write `tools/battlesim/test/golden.test.js` (`node --test`) that calls `forecast(knownInput)` and asserts the exact `{isWin, lossLv}` observed in Step 6 (snapshot the numbers). Run: `node --test tools/battlesim/test/`. Expected: PASS.

- [ ] **Step 8: Commit.**
```bash
git add tools/battlesim/cc-shim.js tools/battlesim/bundle.js tools/battlesim/assets.js tools/battlesim/area-factory.js tools/battlesim/forecast.js tools/battlesim/run-once.js tools/battlesim/test/golden.test.js
git commit -m "battlesim: headless engine boot + forecast (feasibility gate)"
```

---

### Task 2: Node sidecar — JSON-RPC over stdio

**Files:**
- Create: `tools/battlesim/server.js`
- Create: `tools/battlesim/test/server.test.js`

**Interfaces:**
- Consumes: `forecast(input)` from Task 1's `forecast.js`.
- Produces: a process reading newline-delimited JSON requests on stdin and writing newline-delimited JSON responses on stdout. Request: `{id, method, params}`; methods `"ping"` → `{id, result:"pong"}` and `"forecast"` → `{id, result:<forecast output>}`; on error `{id, error:{message}}`. One JSON object per line, both directions. All `cc.log`/diagnostics go to **stderr** (stdout is reserved for JSON-RPC).

- [ ] **Step 1: Write the failing test.** `server.test.js` (`node --test`): spawn `node server.js`, write `{"id":1,"method":"ping"}\n`, read one line, assert parsed `{id:1, result:"pong"}`. Then send a `forecast` request with the known input and assert `result.isWin === true`.

- [ ] **Step 2: Run test to verify it fails.** Run: `node --test tools/battlesim/test/server.test.js`. Expected: FAIL (server.js missing).

- [ ] **Step 3: Implement server.** Write `server.js`: `installAssets(process.env.NTA_CONFIG_DIR || default)`, `loadEngine(process.env.NTA_ENGINE_JS || default)`, then read stdin line-by-line (`readline`), dispatch `ping`/`forecast`, write one JSON line per response to stdout, route all logs to stderr. Wrap each dispatch in try/catch → `{id, error:{message}}`.

- [ ] **Step 4: Run test to verify it passes.** Run: `node --test tools/battlesim/test/server.test.js`. Expected: PASS.

- [ ] **Step 5: Commit.**
```bash
git add tools/battlesim/server.js tools/battlesim/test/server.test.js
git commit -m "battlesim: stdio JSON-RPC sidecar (ping/forecast)"
```

---

### Task 3: Python bridge to the sidecar

**Files:**
- Create: `nta_agent/execution/predictors/sim_bridge.py`
- Test: `tests/test_sim_bridge.py`

**Interfaces:**
- Consumes: `node tools/battlesim/server.js` (JSON-RPC/stdio from Task 2).
- Produces:
  - `class SimUnavailable(Exception)`.
  - `class SimBridge` with `__init__(self, *, node="node", server_js=<default path>, env=None, timeout=10.0)`, `available() -> bool` (spawns if needed, sends `ping`), `forecast(self, input: dict) -> dict` (raises `SimUnavailable` on spawn failure/timeout/error), `close()`.
  - Module-level `get_bridge() -> SimBridge` singleton and `forecast(input: dict) -> dict` convenience.

- [ ] **Step 1: Write the failing test.** In `tests/test_sim_bridge.py`, test against a **fake** sidecar (write a tiny `echo` node/py script into a tmp path, or point `SimBridge(node=sys.executable, server_js=<fake .py>)`). The fake reads a JSON line and replies `{"id":id,"result":{"isWin":True,"lossLv":1,"lossPercent":0.0}}`.
```python
def test_forecast_roundtrip(fake_sidecar):
    b = SimBridge(node=fake_sidecar.node, server_js=fake_sidecar.script, timeout=5)
    assert b.available() is True
    out = b.forecast({"playerUid": "100", "targetCellIndex": 1})
    assert out["isWin"] is True and out["lossLv"] == 1
    b.close()

def test_unavailable_when_binary_missing():
    b = SimBridge(node="definitely-not-a-real-binary-xyz")
    assert b.available() is False
    with pytest.raises(SimUnavailable):
        b.forecast({})
```

- [ ] **Step 2: Run test to verify it fails.** Run: `pytest tests/test_sim_bridge.py -v`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement the bridge.** Write `sim_bridge.py`: manage a `subprocess.Popen` with `stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True`. `_send(method, params)` writes `json.dumps({id, method, params})+"\n"`, flushes, reads one stdout line with a timeout (use a reader thread + `queue.Queue.get(timeout=...)`), parses, returns `result` or raises `SimUnavailable` on `error`. `available()` catches spawn errors and returns False. Auto-restart once on a broken pipe. `close()` terminates the process.

- [ ] **Step 4: Run test to verify it passes.** Run: `pytest tests/test_sim_bridge.py -v`. Expected: PASS.

- [ ] **Step 5: Commit.**
```bash
git add nta_agent/execution/predictors/sim_bridge.py tests/test_sim_bridge.py
git commit -m "predictors: Python<->Node sim bridge (JSON-RPC/stdio)"
```

---

### Task 4: Marshaling — GameState + target → Forecast Input

**Files:**
- Create: `nta_agent/execution/predictors/sim_input.py`
- Test: `tests/test_sim_input.py`

**Interfaces:**
- Consumes: `GameState` (`nta_agent/state/schema.py`), an army dict (AreaArmyInfo with `uid/name/index/pawns`), and target facts.
- Produces: `build_forecast_input(state, armies, *, target_index, land_id, distance, area_size=None) -> dict` matching the Forecast Input Schema from Task 1. Pawn mapping: `{uid, id, lv, hp:[cur,max], buffs, skills, treasures, hero}` pulled from each pawn dict, defaulting missing lists to `[]` and `hero` to `None`. `playerUid = state.user.uid`.

- [ ] **Step 1: Write the failing test.**
```python
def test_build_forecast_input_minimal():
    state = _state_with_uid("100")
    army = {"uid":"a1","name":"D1","index":109726,
            "pawns":[{"uid":"p1","id":3101,"lv":1,"hp":[135,135]}]}
    inp = build_forecast_input(state, [army], target_index=109725, land_id=0, distance=1)
    assert inp["playerUid"] == "100"
    assert inp["targetCellIndex"] == 109725
    assert inp["armies"][0]["pawns"][0] == {
        "uid":"p1","id":3101,"lv":1,"hp":[135,135],
        "buffs":[], "skills":[], "treasures":[], "hero":None}
    assert inp["enemyArmyConf"] is None
```

- [ ] **Step 2: Run test to verify it fails.** Run: `pytest tests/test_sim_input.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement `build_forecast_input`.** Map fields per the Interfaces block; `marchTime` defaults to 0; `area_size` passes through (None allowed).

- [ ] **Step 4: Run test to verify it passes.** Run: `pytest tests/test_sim_input.py -v`. Expected: PASS.

- [ ] **Step 5: Commit.**
```bash
git add nta_agent/execution/predictors/sim_input.py tests/test_sim_input.py
git commit -m "predictors: marshal GameState+target -> forecast input"
```

---

### Task 5: SimBattlePredictor — map engine result to BattlePrediction

**Files:**
- Create: `nta_agent/execution/predictors/sim_predictor.py`
- Test: `tests/test_sim_predictor.py`

**Interfaces:**
- Consumes: `SimBridge` (Task 3), `build_forecast_input` (Task 4), `BattlePrediction` + `stat_pawn_power` (existing).
- Produces:
  - `class SimBattlePredictor` with attribute `pawn_power` (a stats valuer callable, for army selection) and:
    - `predict(self, my_pawns, enemy_pawns) -> BattlePrediction` — interface-compatible; requires context set via
    - `predict_target(self, state, army, *, target_index, land_id, distance, area_size=None) -> BattlePrediction` — the sim entry point.
  - Mapping: `win = result["isWin"]`, `loss_percent = result["lossPercent"]`, `loss_lv = result["lossLv"]`; `my_power/enemy_power/ratio` filled from the stats valuer for continuity.

- [ ] **Step 1: Write the failing test.** Inject a fake bridge whose `forecast` returns `{"isWin":True,"lossLv":2,"lossPercent":18.0}`.
```python
def test_predict_target_maps_engine_result():
    pred = SimBattlePredictor(bridge=FakeBridge({"isWin":True,"lossLv":2,"lossPercent":18.0}))
    out = pred.predict_target(state, army, target_index=109725, land_id=0, distance=1)
    assert out.win is True and out.loss_lv == 2 and out.loss_percent == 18.0
```

- [ ] **Step 2: Run test to verify it fails.** Run: `pytest tests/test_sim_predictor.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement `SimBattlePredictor`.** `predict_target` builds input via `build_forecast_input`, calls `bridge.forecast`, maps to `BattlePrediction`. `predict(my, enemy)` (the legacy signature) computes stats power for the continuity fields and, when no sim context is available, raises `SimUnavailable` (callers fall back). `pawn_power` = `stat_pawn_power(config)`.

- [ ] **Step 4: Run test to verify it passes.** Run: `pytest tests/test_sim_predictor.py -v`. Expected: PASS.

- [ ] **Step 5: Commit.**
```bash
git add nta_agent/execution/predictors/sim_predictor.py tests/test_sim_predictor.py
git commit -m "predictors: SimBattlePredictor maps engine forecast -> BattlePrediction"
```

---

### Task 6: Integrate into occupy with stats fallback

**Files:**
- Modify: `nta_agent/execution/actions.py` (`predict_occupy`, ~142-160)
- Modify: `nta_agent/execution/heuristics.py` (`OccupyCell._pred`, ~134-141; and `applies` prediction call, ~168-176)
- Test: `tests/test_occupy_rule.py` (extend)

**Interfaces:**
- Consumes: `SimBattlePredictor` (Task 5), `SimBridge.available()` (Task 3), existing `BattlePredictor.from_stats` fallback.
- Produces: occupy uses the sim predictor per-candidate when the bridge is available (passing `target_index`, `land_id`, `distance`), else the stats predictor; a sim failure on any candidate degrades that candidate to the stats predictor without killing the tick.

- [ ] **Step 1: Write the failing test.** Extend `tests/test_occupy_rule.py`: with a fake bridge unavailable, assert `OccupyCell` still fires using the stats predictor (existing behavior preserved). With a fake bridge available returning `isWin:false`, assert the candidate is rejected (rule does not occupy).
```python
def test_occupy_uses_sim_when_available(monkeypatch):
    # bridge available, forecast says lose -> no occupy
    ...
    assert "occupy_cell" not in engine.tick(state, actions)

def test_occupy_falls_back_when_sim_unavailable(monkeypatch):
    # bridge unavailable -> stats predictor path still works
    ...
    assert "occupy_cell" in engine.tick(state, actions)
```

- [ ] **Step 2: Run test to verify it fails.** Run: `pytest tests/test_occupy_rule.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement integration.** In `OccupyCell._pred`, prefer `SimBattlePredictor` when `get_bridge().available()`, keeping the stats predictor as `self._fallback`. In `applies`, when using the sim predictor call `predict_target(state, army, target_index=c.index, land_id=<from area>, distance=<computed>)` inside a try/except `SimUnavailable` that falls back to `self._fallback.predict(army["pawns"], c.defenders)`. `land_id` comes from the probed area (`area.get("landId")`); `distance` from `abs(dx)+abs(dy)` between owned cell and target (Manhattan, min over owned neighbors — reuse discovery data). Update `Actions.predict_occupy` similarly.

- [ ] **Step 4: Run test to verify it passes.** Run: `pytest tests/test_occupy_rule.py -v`. Expected: PASS. Then full suite: `pytest -q`. Expected: all pass.

- [ ] **Step 5: Commit.**
```bash
git add nta_agent/execution/actions.py nta_agent/execution/heuristics.py tests/test_occupy_rule.py
git commit -m "execution: occupy uses headless sim with stats fallback"
```

---

### Task 7: Live verification + docs

**Files:**
- Modify: `CLAUDE.md` (Build/lint/test — add Node sidecar note + how to run its tests)
- Modify: memory `nta-agent-re-findings.md` (battle engine reuse + seed formula)

**Interfaces:**
- Consumes: everything above.
- Produces: a verified end-to-end run and updated docs. No new code interfaces.

- [ ] **Step 1: Integration test (requires_node).** Add `tests/test_sim_integration.py` marked `@pytest.mark.requires_node` (skip if `shutil.which("node")` is None or `NTA_ENGINE_JS` file missing): run `SimBattlePredictor.predict_target` against the real sidecar for the known matchup and assert `win is True`. Run: `pytest tests/test_sim_integration.py -v`. Expected: PASS or SKIP.

- [ ] **Step 2: Live loop sanity (manual, documented).** Document the command to run one `RuleEngine.default()` tick against the live session with the sidecar up, and confirm occupy predictions now match the in-game forecast. Record the observed forecast vs sidecar result in the commit message.

- [ ] **Step 3: Update docs.** In `CLAUDE.md` add the Node requirement, `NTA_ENGINE_JS`/`NTA_CONFIG_DIR` env vars, and `node --test tools/battlesim/test/`. Update the memory file with the engine-reuse approach and seed formula.

- [ ] **Step 4: Full verification.** Run: `pytest -q` and `ruff check nta_agent tests`. Expected: all pass, ruff clean.

- [ ] **Step 5: Commit.**
```bash
git add CLAUDE.md tests/test_sim_integration.py
git commit -m "battlesim: integration test + docs; verified vs in-game forecast"
```

---

## Self-Review

**Spec coverage:**
- §2 reuse-engine headless → Task 1. Node sidecar JSON-RPC → Task 2. Deterministic client seed → Task 1 Step 5 + Global Constraints. Single run (no MC) → Task 5 mapping (one forecast call).
- §2 "what we don't supply" (direction/positions) → Task 1 Steps 3-4 reuse generators; Task 4 omits positions from the input schema. ✓
- §3.1 harness files → Task 1. §3.2 bridge → Task 3. §3.3 predictor → Task 5. §3.4 integration+fallback → Task 6. ✓
- §5 tests: JS golden → Task 1 Step 7; client parity → Task 7 Step 2 (manual record) + Task 1 golden; bridge unit → Task 3; marshaling → Task 4; integration → Task 7; fallback → Task 6. ✓
- §6 Phase 1 gate → Task 1 with explicit STOP. ✓
- §7 sensitive artifacts gitignored, read by path → Global Constraints + Task 2 Step 3. ✓

**Placeholder scan:** No TBD/TODO. The one irreducibly exploratory task (Task 1) is labeled DISCOVERY with a concrete method (error-driven stub building) and a hard, checkable gate (Step 6 result + Step 7 golden), because its exact stub code cannot be predicted from static reading — this is stated, not hidden.

**Type consistency:** Forecast Input Schema is defined once (Task 1) and referenced by Tasks 4/5/6. `forecast()` output keys `{isWin, lossLv, lossPercent, timeMs, survivors}` are consistent across Tasks 1/2/3/5. `SimBattlePredictor.predict_target(...)` signature matches between Tasks 5 and 6. `SimUnavailable` raised in Task 3, caught in Tasks 5/6. `BattlePrediction` fields match the existing dataclass.
