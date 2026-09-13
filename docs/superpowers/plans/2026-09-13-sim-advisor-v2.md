# Sim-Advisor v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the battle sim reproduce the game's real 1-tile turn order (later armies join as reinforcement waves), validated against a real battle record, then have the occupy rule auto-pick the selection order that wins with least predicted loss.

**Architecture:** A "frames" abstraction mirrors the game's record format (one type-0 initial wave + type-1 reinforcement waves at a `currentFrameIndex`). A Node driver (`reinforce.js`) runs it on the real engine's `AreaObj`/`battleLocalBegin`, injecting later waves the way the engine's `restartBattleWithReinforce` does. Two producers feed it: a real `BattleRecordInfo` (oracle/tests) and a live builder (`frames.js`) that schedules army arrivals from marchTime. The Python advisor evaluates a few candidate selection orders on this sim and the occupy rule applies the best.

**Tech Stack:** Python 3.12 (venv `.venv`), Node ≥ 18 (sidecar), pytest, `node --test`, ruff. Protobuf API over MQTT (existing `GameSession`).

**Spec:** `docs/superpowers/specs/2026-09-13-sim-advisor-v2-design.md`

## Global Constraints

- Python interpreter: `.venv/Scripts/python.exe` (Windows). Lint: `ruff check nta_agent tests`.
- Node sidecar reads engine via `NTA_ENGINE_JS` (default `tools/re/decrypted/index.js`) and config via `NTA_CONFIG_DIR` (default `nta_agent/data/config`); both gitignored — tests needing them are skipped when absent.
- Determinism: `randSeed = floor(playerUid/100) + targetIndex`. No Monte-Carlo.
- The event loop must never die: any predictor/sim failure falls back to the stats predictor (`SimUnavailable`).
- API route strings are case-sensitive and exact: `game/HD_GetBattleRecordsList`, `game/HD_GetBattleRecord`, `game/HD_OccupyCell`.
- Camps: 2 = our side, 1 = enemy. PawnType 3 = archer (id prefix 33xx); tank/pikeman = id 31xx (PawnType 1).
- Commit proactively at each green task (CLAUDE.md). Do not push.
- Fixture already saved: `tools/battlesim/test/fixtures/battle_1tile.json` (real 1-tile record: cung Đội 2 id3305×5 + tank Đội 3 id3101×7 vs enemy id4116×3; randSeed 686685; reinforce @frame 1; isWin=true, 0 dead).

---

### Task 1: Battle-record API actions

**Files:**
- Modify: `nta_agent/execution/actions.py` (add two methods near `get_player_armys`)
- Test: `tests/test_actions_battle_record.py` (create)

**Interfaces:**
- Consumes: `self.session.request(route, params) -> dict` (existing).
- Produces: `Actions.get_battle_records_list() -> list[dict]`; `Actions.get_battle_record(uid: str) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_actions_battle_record.py
from nta_agent.execution.actions import Actions
from nta_agent.state.schema import GameState


class FakeSession:
    def __init__(self, reply):
        self.state = GameState(source="api")
        self.state.raw = {}
        self._reply = reply
        self.sent = []

    def request(self, route, params=None, timeout=15):
        self.sent.append((route, params))
        return self._reply


def test_get_battle_records_list_sends_route_and_returns_list():
    s = FakeSession({"list": [{"uid": "b1", "index": 109725, "isWin": True}]})
    out = Actions(s).get_battle_records_list()
    assert s.sent[0] == ("game/HD_GetBattleRecordsList", {})
    assert out == [{"uid": "b1", "index": 109725, "isWin": True}]


def test_get_battle_record_sends_uid_and_returns_record():
    s = FakeSession({"record": {"uid": "b1", "frames": [{"type": 0}]}})
    out = Actions(s).get_battle_record("b1")
    assert s.sent[0] == ("game/HD_GetBattleRecord", {"uid": "b1"})
    assert out == {"uid": "b1", "frames": [{"type": 0}]}


def test_get_battle_records_list_empty_when_missing():
    s = FakeSession({})
    assert Actions(s).get_battle_records_list() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_actions_battle_record.py -q`
Expected: FAIL (AttributeError: no `get_battle_records_list`).

- [ ] **Step 3: Write minimal implementation**

Add to `nta_agent/execution/actions.py` after `get_player_armys`:

```python
    # ---- battle records (read-only ground truth) ------------------------ #
    def get_battle_records_list(self) -> list[dict]:
        """List the player's stored battles (GAME_HD_GetBattleRecordsList)."""
        reply = self.session.request("game/HD_GetBattleRecordsList", {})
        return reply.get("list", []) or []

    def get_battle_record(self, uid: str) -> dict:
        """Fetch one battle's full frame record (GAME_HD_GetBattleRecord)."""
        reply = self.session.request("game/HD_GetBattleRecord", {"uid": str(uid)})
        return reply.get("record", {}) or {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_actions_battle_record.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/actions.py tests/test_actions_battle_record.py
git commit -m "execution: read-only battle-record actions (list + fetch)"
```

---

### Task 2: Keep the cc-shim Vec2.equals fix + commit the fixture

**Files:**
- Modify: `tools/battlesim/cc-shim.js` (static `Vec2.equals` — already applied in spike)
- Add: `tools/battlesim/test/fixtures/battle_1tile.json` (already saved)
- Test: `tools/battlesim/test/shim.test.js` (create)

**Interfaces:**
- Produces: `cc.Vec2.equals(a, b) -> boolean` (static).

- [ ] **Step 1: Write the failing test**

```js
// tools/battlesim/test/shim.test.js
const { test } = require("node:test");
const assert = require("node:assert");
const { Vec2 } = require("../cc-shim");

test("Vec2.equals is a static method", () => {
  assert.strictEqual(typeof Vec2.equals, "function");
  assert.strictEqual(Vec2.equals({ x: 1, y: 2 }, { x: 1, y: 2 }), true);
  assert.strictEqual(Vec2.equals({ x: 1, y: 2 }, { x: 1, y: 3 }), false);
  assert.strictEqual(Vec2.equals(null, { x: 1, y: 2 }), false);
});
```

- [ ] **Step 2: Run test to verify it passes (fix already applied in spike)**

Run: `node --test tools/battlesim/test/shim.test.js`
Expected: PASS. If it FAILS, add to `tools/battlesim/cc-shim.js` right after the `Vec2` class body: `Vec2.equals = (a, b) => !!a && !!b && a.x === b.x && a.y === b.y;`

- [ ] **Step 3: Verify the fixture exists and is well-formed**

Run: `.venv/Scripts/python.exe -c "import json;d=json.load(open('tools/battlesim/test/fixtures/battle_1tile.json',encoding='utf-8'));f=d['record']['frames'];print('frames',len(f),'isWin',d['summary']['isWin'])"`
Expected: `frames 3 isWin True`.

- [ ] **Step 4: Commit**

```bash
git add tools/battlesim/cc-shim.js tools/battlesim/test/shim.test.js tools/battlesim/test/fixtures/battle_1tile.json
git commit -m "battlesim: static Vec2.equals (melee pathfinding) + real 1-tile record fixture"
```

---

### Task 3: `frames.js` — build the frames abstraction from a Forecast Input (live path)

**Files:**
- Create: `tools/battlesim/frames.js`
- Test: `tools/battlesim/test/frames.test.js`

**Interfaces:**
- Consumes: a Forecast Input `{playerUid, targetCellIndex, armies:[{uid,name,index,marchTime,pawns:[{uid,id,lv,hp?}]}], ...}` and `requireByName` (for `mapHelper`/`pawnBase` attack speed).
- Produces: `buildFrames(input, requireByName) -> { initial: {armys, fighters, randSeed, fps}, waves: [{currentFrameIndex, army, fighters}] }` where each `fighters[]` entry is `{uid, camp, attackIndex, enterIndex}` and `armys[]` entries carry `pawns` with `point`/`attackSpeed`. `FPS = 20`.

- [ ] **Step 1: Write the failing test (arrival scheduling)**

```js
// tools/battlesim/test/frames.test.js
const { test } = require("node:test");
const assert = require("node:assert");
const { arriveFrame, FPS } = require("../frames");

test("first army arrives at frame 0, later armies by marchTime delta", () => {
  // msPerFrame = 1000/20 = 50. delta 0 -> max(1, floor(0/50))=1 (+tiebreak).
  assert.strictEqual(arriveFrame(0, 0, 0), 0);         // baseline
  assert.strictEqual(arriveFrame(50, 0, 0), 1);        // 50ms later -> floor(1)=1
  assert.strictEqual(arriveFrame(5000, 0, 0), 100);    // 5000/50 = 100
  assert.strictEqual(arriveFrame(0, 0, 1), 1);         // equal marchTime, 2nd -> max(1,0)+... tiebreak keeps >=1
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tools/battlesim/test/frames.test.js`
Expected: FAIL (Cannot find module or `arriveFrame` undefined).

- [ ] **Step 3: Write minimal implementation**

```js
// tools/battlesim/frames.js
"use strict";
const FPS = 20;
const MS_PER_FRAME = 1000 / FPS;

// Arrival frame for an army: baseline (first-selected) is 0; later armies use
// the engine's formula O = max(1, floor(delta/msPerFrame)) + tiebreak.
// (Verified in ArtofwarForecastObj.startForecast.)
function arriveFrame(marchTime, baseMarchTime, tiebreak) {
  const delta = marchTime - baseMarchTime;
  if (delta <= 0 && tiebreak === 0) return 0;
  return Math.max(1, Math.floor(delta / MS_PER_FRAME)) + tiebreak;
}

function pawnAttackSpeed(id, requireByName) {
  const base = globalThis.assetsMgr.getJsonData("pawnBase", id);
  return (base && base.attack_speed) || 0;
}

// Build the frames abstraction. armies are in SELECTION order; index 0 = frame 0.
function buildFrames(input, requireByName) {
  const mapHelper = requireByName("MapHelper").mapHelper;
  const target = input.targetCellIndex;
  const myUid = String(input.playerUid);
  const randSeed = Math.floor(Number(myUid) / 100) + target;

  const armies = input.armies || [];
  const base = armies.length ? (armies[0].marchTime || 0) : 0;
  const seenDelta = {};
  let attackIndexAcc = 0;

  // Order pawns within an army fastest-first; assign sequential attackIndex.
  const stripArmy = (army) => {
    const pawns = (army.pawns || []).slice().sort(
      (a, b) => pawnAttackSpeed(b.id) - pawnAttackSpeed(a.id));
    const fighters = pawns.map((p) => ({
      uid: p.uid, camp: 2, attackIndex: ++attackIndexAcc, enterIndex: attackIndexAcc,
    }));
    return { army: { index: army.index, uid: army.uid, name: army.name || "D1",
                     owner: myUid, pawns }, fighters };
  };

  const first = stripArmy(armies[0]);
  const waves = [];
  for (let i = 1; i < armies.length; i++) {
    const mt = armies[i].marchTime || 0;
    const delta = mt - base;
    const tb = seenDelta[delta] || 0;
    seenDelta[delta] = tb + 1;
    const cfi = arriveFrame(mt, base, tb);
    const s = stripArmy(armies[i]);
    waves.push({ currentFrameIndex: cfi, army: s.army, fighters: s.fighters });
  }
  return { initial: { firstArmy: first.army, fighters: first.fighters, randSeed, fps: FPS,
                      attackIndexAcc }, waves, target };
}

module.exports = { buildFrames, arriveFrame, FPS };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tools/battlesim/test/frames.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/battlesim/frames.js tools/battlesim/test/frames.test.js
git commit -m "battlesim: frames abstraction with marchTime arrival scheduling"
```

---

### Task 4: `reinforce.js` driver + `record-replay.js` + oracle golden (fidelity gate)

**Files:**
- Create: `tools/battlesim/reinforce.js`
- Create: `tools/battlesim/record-replay.js`
- Modify: `tools/battlesim/test/golden.test.js` (add oracle test)

**Interfaces:**
- Consumes: `frames.js::buildFrames` output; the record fixture; engine via `bundle.js`/`assets.js`; the engine method `AreaObj.prototype.restartBattleWithReinforce` (source: remove all armys, re-add arriving army + enemies, `battleLocalBegin(..., currentFrameIndex)`).
- Produces: `runWithReinforce({initial, waves, enemyConf, target, playerUid}, requireByName) -> {isWin, lossLv, lossPercent, survivors}`; `recordToFrames(record) -> {initial, waves}`; `replayRecord(record, requireByName) -> {isWin, lossPercent, survivors}`.

- [ ] **Step 1: Write the failing oracle test**

```js
// append to tools/battlesim/test/golden.test.js
const fs = require("node:fs");
const path = require("node:path");

test("oracle: replaying the real 1-tile record reproduces its outcome", (t) => {
  if (!fs.existsSync(process.env.NTA_ENGINE_JS || "tools/re/decrypted/index.js")) {
    t.skip("engine bundle absent"); return;
  }
  const { replayRecord } = require("../record-replay");
  const fixture = JSON.parse(fs.readFileSync(
    path.join(__dirname, "fixtures", "battle_1tile.json"), "utf8"));
  const { loadEngine } = require("../bundle");
  const { installAssets } = require("../assets");
  if (!globalThis.eventCenter) globalThis.eventCenter = { emit(){}, on(){}, off(){}, once(){} };
  if (!globalThis.mc) globalThis.mc = { getModel: () => ({}) };
  const req = loadEngine();
  installAssets(undefined, req, { playerUid: "57696053" });
  const out = replayRecord(fixture.record, req);
  assert.strictEqual(out.isWin, true);
  assert.strictEqual(out.survivors.self.alive, out.survivors.self.total); // 0 dead
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tools/battlesim/test/golden.test.js`
Expected: FAIL (Cannot find module `../record-replay`).

- [ ] **Step 3: Write `reinforce.js` (engine driver)**

```js
// tools/battlesim/reinforce.js
"use strict";
const FPS = 20, FPS_MUL = 400, MAX_UPDATES = 5000;

function loss_lv(pct) {
  if (pct <= 0) return 0; if (pct <= 15) return 1;
  if (pct < 50) return 2; if (pct < 100) return 3; return 4;
}

// Build an AreaObj holding the initial wave (our first army) + enemy, then step
// frames; when elapsed frames reach a wave's currentFrameIndex, inject it the
// way the engine's restartBattleWithReinforce does (remove armys, re-add
// arriving army + enemies, battleLocalBegin with currentFrameIndex).
function runWithReinforce({ initial, waves, enemyArmys, enemyHp, target, playerUid }, req) {
  const AreaObj = req("AreaObj").default;
  const mapHelper = req("MapHelper").mapHelper;

  const ourArmys = [initial.firstArmy];
  let fighters = initial.fighters.slice();
  // append enemy fighters after ours (camp 1), continuing attackIndex
  let acc = initial.attackIndexAcc;
  for (const a of enemyArmys)
    for (const p of a.pawns)
      fighters.push({ uid: p.uid, camp: 1, attackIndex: ++acc, enterIndex: acc });

  const area = new AreaObj().init({
    index: target, owner: "", hp: enemyHp || [0, 0], cityId: 0,
    armys: [...ourArmys, ...enemyArmys],
  });
  area.updatePawnAnimationFrame = () => {};
  if (area.updateTreasureReddot) area.updateTreasureReddot = () => {};

  const selfTotalStart = initial.fighters.length +
    waves.reduce((n, w) => n + w.fighters.length, 0);
  const enemyTotal = enemyArmys.reduce((n, a) => n + a.pawns.length, 0);

  let result = null;
  const origEnd = area.battleEndByLocal.bind(area);
  area.battleEndByLocal = function () {
    if (!result) {
      const bc = area.fspModel && area.fspModel.getBattleController();
      const fs2 = (bc && bc.getFighters()) || [];
      const aliveIn = (c) => fs2.filter((f) => f.getCamp && f.getCamp() === c && f.isDie && !f.isDie()).length;
      const self = { alive: aliveIn(2), total: selfTotalStart };
      const enemy = { alive: aliveIn(1), total: enemyTotal };
      const lostPct = self.total ? (100 * (self.total - self.alive)) / self.total : 100;
      result = { isWin: !!(bc && bc.isWin()), lossLv: loss_lv(lostPct),
        lossPercent: Math.round(lostPct * 10) / 10, survivors: { self, enemy } };
    }
    return origEnd();
  };

  let fsp = area.battleLocalBegin({ camp: 1, randSeed: initial.randSeed,
    accAttackIndex: 0, fps: FPS, fighters, mul: FPS_MUL, forecast: true });

  const pending = waves.slice().sort((a, b) => a.currentFrameIndex - b.currentFrameIndex);
  const dt = 1 / FPS;
  let frame = 0, n = 0;
  while (fsp.isRunning && n < MAX_UPDATES && !result) {
    while (pending.length && pending[0].currentFrameIndex <= frame) {
      const w = pending.shift();
      // inject reinforcement: add the arriving army; continue the battle.
      for (const p of w.army.pawns) { /* pawns carry point/id/lv/hp already */ }
      area.addArmy(w.army);
      const inj = w.fighters.slice();
      fsp = area.battleLocalBegin({ camp: 1, randSeed: initial.randSeed,
        accAttackIndex: w.fighters[w.fighters.length - 1].attackIndex,
        fps: FPS, fighters: fighters.concat(inj), mul: FPS_MUL, forecast: true,
        currentFrameIndex: w.currentFrameIndex });
      fighters = fighters.concat(inj);
    }
    fsp.update(dt);
    frame += 1; n += 1;
  }
  if (!result) return { isWin: false, lossLv: 5, lossPercent: 100, survivors: null, timedOut: true };
  return result;
}

module.exports = { runWithReinforce, FPS };
```

- [ ] **Step 4: Write `record-replay.js` (record → frames → run)**

```js
// tools/battlesim/record-replay.js
"use strict";
const { runWithReinforce } = require("./reinforce");

// Split a BattleRecordInfo into our initial wave + enemy + reinforcement waves.
function recordToFrames(record) {
  const frames = record.frames || [];
  const init = frames.find((f) => !f.type);            // type 0 (omitted when 0)
  const reinforce = frames.filter((f) => f.type === 1);
  const armys = init.armys || [];
  const our0 = armys.find((a) => a.owner);             // our army (has owner)
  const enemyArmys = armys.filter((a) => !a.owner);     // enemy (owner "")
  const ourFighters = (init.fighters || []).filter((f) => f.camp === 2);
  return {
    initial: { firstArmy: our0, fighters: ourFighters,
               randSeed: init.randSeed, fps: init.fps || 20,
               attackIndexAcc: ourFighters.length },
    enemyArmys, enemyHp: init.hp || [0, 0],
    waves: reinforce.map((f) => ({ currentFrameIndex: f.currentFrameIndex,
                                   army: f.army, fighters: f.fighters })),
    target: record.index, playerUid: ( our0 && our0.owner) || "0",
  };
}

function replayRecord(record, req) {
  const f = recordToFrames(record);
  return runWithReinforce(f, req);
}

module.exports = { recordToFrames, replayRecord };
```

- [ ] **Step 5: Run the oracle test**

Run: `node --test tools/battlesim/test/golden.test.js`
Expected: PASS — `isWin===true`, self alive === total (0 dead), matching the record.
If it FAILS on outcome: the injection point/attackIndex continuation is off — compare the driver's fighter order at frame 0 against the record's `fighters` (ai 1-5 camp2, 6-8 camp1) and the reinforcement continuation (ai 9-15) and fix `runWithReinforce`'s `accAttackIndex`/enemy-append order to match, then re-run.

- [ ] **Step 6: Commit**

```bash
git add tools/battlesim/reinforce.js tools/battlesim/record-replay.js tools/battlesim/test/golden.test.js
git commit -m "battlesim: reinforcement driver + record replay; oracle golden vs real 1-tile"
```

---

### Task 5: Route the live path through frames+reinforce; slim area-factory

**Files:**
- Modify: `tools/battlesim/forecast.js`
- Modify: `tools/battlesim/area-factory.js`
- Test: `tools/battlesim/test/golden.test.js` (existing single-army goldens must stay green)

**Interfaces:**
- Consumes: `frames.js::buildFrames`, `reinforce.js::runWithReinforce`, and the enemy builder in `area-factory.js` (`getEnemyArmys` via `gameHpr.getAreaPawnConfInfo`, or `input.enemyArmyConf`).
- Produces: `forecast(input)` unchanged signature/return; multi-army inputs now use reinforcement.

- [ ] **Step 1: Write the failing test (order changes loss, multi-army routed)**

```js
// append to tools/battlesim/test/golden.test.js
test("multi-army forecast routes through reinforcement and is order-sensitive", (t) => {
  if (!fs.existsSync(process.env.NTA_ENGINE_JS || "tools/re/decrypted/index.js")) { t.skip(); return; }
  const { forecast } = require("../forecast");
  const enemy = { index: 109725, hp: [100, 100], armys: [{ index: 109725, uid: "e",
    state: 0, name: "", owner: "", pawns: Array.from({length:12},(_,i)=>(
      {uid:"e"+i,id:4101,lv:2,point:{x:6+(i%4),y:6+((i/4)|0)}})) }] };
  const cung = { uid:"ac", name:"Cung", index:109726, marchTime:0,
    pawns: Array.from({length:5},(_,i)=>({uid:"c"+i,id:3305,lv:1})) };
  const tank = { uid:"at", name:"Tank", index:109726, marchTime:0,
    pawns: Array.from({length:5},(_,i)=>({uid:"t"+i,id:3101,lv:1})) };
  const mk = (armies) => forecast({ playerUid:"1000000000", targetCellIndex:109725,
    landId:0, selfToCellDistance:1, areaSize:null, armies, enemyArmyConf: enemy });
  const a = mk([cung, tank]);   // cung first
  const b = mk([tank, cung]);   // tank first
  assert.strictEqual(a.isWin, true);
  assert.strictEqual(b.isWin, true);
  assert.ok(a.lossPercent <= b.lossPercent); // cung-first no worse (1-tile)
});
```

- [ ] **Step 2: Run test to verify it fails or is unrouted**

Run: `node --test tools/battlesim/test/golden.test.js`
Expected: FAIL (multi-army still all-at-once, or assertion mismatch).

- [ ] **Step 3: Implement routing in `forecast.js`**

Replace the body of `forecast(input)` so that when `input.armies.length > 1` it builds frames and runs the reinforcement driver; otherwise the existing single-wave path. Concretely, after `const req = bootstrap(input.playerUid);`:

```js
  const { buildFrames } = require("./frames");
  const { runWithReinforce } = require("./reinforce");
  const { enemyArmysFor } = require("./area-factory"); // extracted helper (Step 4)
  if ((input.armies || []).length > 1) {
    const f = buildFrames(input, req);
    const { armys: enemyArmys, hp: enemyHp } = enemyArmysFor(input, req, f);
    return runWithReinforce({ ...f, enemyArmys, enemyHp, playerUid: String(input.playerUid) }, req);
  }
  // ... existing single-army path unchanged ...
```

- [ ] **Step 4: Extract `enemyArmysFor` in `area-factory.js`**

Expose the existing enemy-building logic (explicit `input.enemyArmyConf` or `gameHpr.getAreaPawnConfInfo(target, landId, selfToCellDistance)`, sorted by `100*attackSpeed+(99-dist)`), returning `{armys, hp}`. Keep `buildArea` for the single-army path.

```js
function enemyArmysFor(input, requireByName, frames) {
  const mapHelper = requireByName("MapHelper").mapHelper;
  const conf = input.enemyArmyConf || requireByName("GameHelper").gameHpr
    .getAreaPawnConfInfo(input.targetCellIndex, input.landId, input.selfToCellDistance);
  // entry = first army's first pawn point (frames.initial); reuse existing sort
  const entry = (frames.initial.firstArmy.pawns[0] || {}).point || { x: 0, y: 0 };
  conf.armys.forEach((a) => { a.state = a.state || 2; a.owner = a.owner || "";
    a.pawns.sort((p, q) =>
      (100*(p.attackSpeed||0)+(99-mapHelper.getPointToPointDis(q.point, entry))) -
      (100*(q.attackSpeed||0)+(99-mapHelper.getPointToPointDis(p.point, entry)))); });
  return { armys: conf.armys, hp: conf.hp || [0, 0] };
}
module.exports = { buildArea, enemyArmysFor };
```

- [ ] **Step 5: Run all sidecar tests**

Run: `node --test tools/battlesim/test/*.test.js`
Expected: PASS — new order-sensitivity test, oracle golden, and the original single-army goldens (4/4).

- [ ] **Step 6: Commit**

```bash
git add tools/battlesim/forecast.js tools/battlesim/area-factory.js tools/battlesim/test/golden.test.js
git commit -m "battlesim: route multi-army forecasts through reinforcement path"
```

---

### Task 6: Python sim input carries selection order + marchTime (verify plumbing)

**Files:**
- Modify: `nta_agent/execution/predictors/sim_input.py` (only if a field is missing)
- Test: `tests/test_sim_input.py` (create or extend)

**Interfaces:**
- Consumes: `GameState`, armies list.
- Produces: `build_forecast_input(...)` dict whose `armies` preserves input order and each carries `marchTime` and `pawns` with `id/lv/hp`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sim_input.py
from nta_agent.execution.predictors.sim_input import build_forecast_input
from nta_agent.state.schema import GameState


def test_forecast_input_preserves_army_order_and_marchtime():
    st = GameState(source="api"); st.raw = {}
    st.user.uid = "57696053"
    armies = [
        {"uid": "cung", "name": "Cung", "index": 1, "marchTime": 0,
         "pawns": [{"uid": "c1", "id": 3305, "lv": 1}]},
        {"uid": "tank", "name": "Tank", "index": 1, "marchTime": 5000,
         "pawns": [{"uid": "t1", "id": 3101, "lv": 1}]},
    ]
    out = build_forecast_input(st, armies, target_index=109725, land_id=0, distance=1)
    assert [a["uid"] for a in out["armies"]] == ["cung", "tank"]
    assert out["armies"][1]["marchTime"] == 5000
    assert out["armies"][0]["pawns"][0]["id"] == 3305
```

- [ ] **Step 2: Run test**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sim_input.py -q`
Expected: PASS if plumbing already correct (sim_input already marshals `marchTime`); if FAIL, ensure `_army` includes `"marchTime": int(a.get("marchTime", 0) or 0)` and preserves list order (it does today — this test locks it).

- [ ] **Step 3: (only if needed) fix `_army`/`build_forecast_input`**

No change expected; if the test fails, make the minimal edit to satisfy it.

- [ ] **Step 4: Commit**

```bash
git add nta_agent/execution/predictors/sim_input.py tests/test_sim_input.py
git commit -m "predictors: lock sim_input army order + marchTime marshaling"
```

---

### Task 7: `advisor.best_plan` — pure plan scorer

**Files:**
- Modify: `nta_agent/execution/advisor.py`
- Test: `tests/test_advisor.py` (extend)

**Interfaces:**
- Consumes: `candidates` (objects with `.index`), `plans_for(cell_index) -> list[Plan]` (Plan without prediction), `predict(plan) -> BattlePrediction | None` (has `.win`, `.loss_percent`).
- Produces: `Plan` dataclass `{armies: list[dict], target: int, label: str, prediction}`; `best_plan(candidates, plans_for, predict) -> Plan | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_advisor.py (add)
from types import SimpleNamespace
from nta_agent.execution.advisor import best_plan, Plan


def _pred(win, loss):
    return SimpleNamespace(win=win, loss_percent=loss)


def test_best_plan_picks_lowest_loss_winning_plan():
    cell = SimpleNamespace(index=7)
    plans = {
        7: [
            Plan(armies=[{"uid": "a"}, {"uid": "b"}], target=7, label="archers-first", prediction=None),
            Plan(armies=[{"uid": "b"}, {"uid": "a"}], target=7, label="tanks-first", prediction=None),
            Plan(armies=[{"uid": "a"}], target=7, label="single", prediction=None),
        ]
    }
    preds = {"archers-first": _pred(True, 10), "tanks-first": _pred(True, 20),
             "single": _pred(False, 100)}
    got = best_plan([cell], lambda i: plans[i], lambda p: preds[p.label])
    assert got.label == "archers-first"
    assert got.armies == [{"uid": "a"}, {"uid": "b"}]


def test_best_plan_tie_prefers_fewer_armies():
    cell = SimpleNamespace(index=7)
    plans = {7: [
        Plan(armies=[{"uid": "a"}, {"uid": "b"}], target=7, label="two", prediction=None),
        Plan(armies=[{"uid": "a"}], target=7, label="one", prediction=None),
    ]}
    preds = {"two": _pred(True, 10), "one": _pred(True, 10)}
    got = best_plan([cell], lambda i: plans[i], lambda p: preds[p.label])
    assert got.label == "one"


def test_best_plan_none_when_no_win():
    cell = SimpleNamespace(index=7)
    plans = {7: [Plan(armies=[{"uid": "a"}], target=7, label="x", prediction=None)]}
    got = best_plan([cell], lambda i: plans[i], lambda p: _pred(False, 100))
    assert got is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_advisor.py -q`
Expected: FAIL (no `best_plan`/`Plan`).

- [ ] **Step 3: Implement in `advisor.py`**

```python
@dataclass
class Plan:
    armies: list  # ordered army dicts (selection order)
    target: int
    label: str
    prediction: object


def best_plan(candidates, plans_for, predict):
    """Best plan over candidates × candidate orderings: winnable, lowest loss,
    tie broken toward fewer armies."""
    best = None  # (loss_percent, n_armies, Plan)
    for c in candidates:
        for plan in plans_for(c.index):
            pred = predict(plan)
            if pred is None or not pred.win:
                continue
            key = (pred.loss_percent, len(plan.armies))
            if best is None or key < best[0]:
                plan.prediction = pred
                best = (key, plan)
    return best[1] if best else None
```

Keep `best_occupy` for backward compatibility (single-army callers/tests).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_advisor.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/advisor.py tests/test_advisor.py
git commit -m "advisor: best_plan scores ordered multi-army plans"
```

---

### Task 8: Candidate order strategies (archers-first / tanks-first / single)

**Files:**
- Create: `nta_agent/execution/order_strategies.py`
- Test: `tests/test_order_strategies.py`

**Interfaces:**
- Consumes: a group `list[dict]` of armies (each `{uid, pawns:[{id,...}]}`).
- Produces: `candidate_orders(group) -> list[tuple[str, list[dict]]]` (label, ordered armies); `is_archer_army(army) -> bool` (majority PawnType 3, id 33xx).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_order_strategies.py
from nta_agent.execution.order_strategies import candidate_orders, is_archer_army


def _army(uid, ids):
    return {"uid": uid, "pawns": [{"id": i} for i in ids]}


def test_is_archer_army_by_majority_pawntype():
    assert is_archer_army(_army("a", [3305, 3305, 3101])) is True
    assert is_archer_army(_army("b", [3101, 3101, 3305])) is False


def test_candidate_orders_includes_archers_first_and_tanks_first_and_singles():
    cung = _army("cung", [3305, 3305])
    tank = _army("tank", [3101, 3101])
    labels = {lbl for lbl, _ in candidate_orders([tank, cung])}
    assert "archers-first" in labels
    assert "tanks-first" in labels
    assert "single:cung" in labels and "single:tank" in labels
    # archers-first orders the archer army before the tank army
    af = next(order for lbl, order in candidate_orders([tank, cung]) if lbl == "archers-first")
    assert [a["uid"] for a in af] == ["cung", "tank"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_order_strategies.py -q`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# nta_agent/execution/order_strategies.py
"""Candidate selection-orders for the occupy planner (1-tile vs avoid)."""
from __future__ import annotations


def is_archer_army(army: dict) -> bool:
    pawns = army.get("pawns") or []
    if not pawns:
        return False
    archers = sum(1 for p in pawns if 3300 <= int(p.get("id", 0)) < 3400)
    return archers * 2 > len(pawns)


def candidate_orders(group: list[dict]) -> list[tuple[str, list[dict]]]:
    """A few tactically-meaningful orderings, not all permutations."""
    if not group:
        return []
    archers = [a for a in group if is_archer_army(a)]
    others = [a for a in group if not is_archer_army(a)]
    out: list[tuple[str, list[dict]]] = []
    if archers and others:
        out.append(("archers-first", archers + others))
        out.append(("tanks-first", others + archers))
    else:
        out.append(("as-selected", list(group)))
    for a in group:
        out.append((f"single:{a.get('uid')}", [a]))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_order_strategies.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nta_agent/execution/order_strategies.py tests/test_order_strategies.py
git commit -m "execution: candidate selection-order strategies for occupy"
```

---

### Task 9: Wire OccupyCell to auto-apply the best ordered plan

**Files:**
- Modify: `nta_agent/execution/heuristics.py` (`OccupyCell`)
- Test: `tests/test_occupy_rule.py` (extend)

**Interfaces:**
- Consumes: `advisor.best_plan`, `order_strategies.candidate_orders`, `SimBattlePredictor.predict_target(armies, candidate)`, `actions.occupy_cell(target, armies)`, and a reachable-armies source.
- Produces: `OccupyCell.tick(...)` commits `occupy_cell(target, plan.armies)` and emits `occupy_plan{target, label, order, loss_percent}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_occupy_rule.py (add)
from types import SimpleNamespace
from nta_agent.execution.heuristics import OccupyCell


def test_occupy_commits_best_order_and_emits_plan():
    cung = {"uid": "cung", "index": 5, "pawns": [{"id": 3305}, {"id": 3305}]}
    tank = {"uid": "tank", "index": 5, "pawns": [{"id": 3101}, {"id": 3101}]}
    events = []
    calls = []

    class Preds:
        # cung-first wins with 0 loss; tank-first wins with 30; singles lose.
        def predict_target(self, armies, candidate):
            first = armies[0]["uid"]
            if len(armies) == 2 and first == "cung":
                return SimpleNamespace(win=True, loss_percent=0)
            if len(armies) == 2:
                return SimpleNamespace(win=True, loss_percent=30)
            return SimpleNamespace(win=False, loss_percent=100)

    actions = SimpleNamespace(occupy_cell=lambda target, armies: calls.append((target, [a["uid"] for a in armies])))
    rule = OccupyCell(use_sim=True, on_event=events.append)
    rule.run(  # exact call shape per the rule's tick signature
        candidates=[SimpleNamespace(index=5)],
        group_for=lambda i: [tank, cung],
        predictor=Preds(),
        actions=actions,
    )
    assert calls == [(5, ["cung", "tank"])]
    assert any(e[0] == "occupy_plan" and e[1]["label"] == "archers-first" for e in events)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_occupy_rule.py -q`
Expected: FAIL (OccupyCell lacks the group/plan flow or `run` shape).

- [ ] **Step 3: Implement the plan flow in `OccupyCell`**

Add a helper the rule uses (adapt to the existing `OccupyCell` structure — it already holds `use_sim`/`on_event`; wire `candidate_orders` + `best_plan`):

```python
from nta_agent.execution.advisor import Plan, best_plan
from nta_agent.execution.order_strategies import candidate_orders

# inside OccupyCell:
def _plans_for(self, cell_index, group_for):
    group = group_for(cell_index)
    return [Plan(armies=order, target=cell_index, label=label, prediction=None)
            for label, order in candidate_orders(group)]

def run(self, *, candidates, group_for, predictor, actions):
    def predict(plan):
        cand = next(c for c in candidates if c.index == plan.target)
        return predictor.predict_target(plan.armies, cand)
    plan = best_plan(candidates, lambda i: self._plans_for(i, group_for), predict)
    if plan is None:
        return None
    self.on_event("occupy_plan", {"target": plan.target, "label": plan.label,
        "order": [a.get("uid") for a in plan.armies],
        "loss_percent": plan.prediction.loss_percent})
    actions.occupy_cell(plan.target, plan.armies)
    return plan
```

Integrate this into the existing `tick`/event path (replace the single-army `best_occupy` call site), keeping the `SimUnavailable` fallback: on predictor error, fall back to `best_occupy` with the stats predictor and a default `archers-first` order.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_occupy_rule.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite + lint**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check nta_agent tests`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add nta_agent/execution/heuristics.py tests/test_occupy_rule.py
git commit -m "occupy: auto-apply best selection-order plan via sim advisor"
```

---

## Self-Review

**Spec coverage:** §2 records → Task 1 (fetch) + Task 2 (fixture). §3/§5 reinforcement → Tasks 3–5. §4 record infra → Task 1. §6 advisor/occupy → Tasks 7–9. §9 oracle test → Task 4 (headline), frames/reinforce/advisor/occupy tests → Tasks 3,4,7,9; fallback → Task 9 Step 3; single-army goldens → Task 5. All covered.

**Placeholder scan:** No TBD/TODO; each step has runnable commands or real code. Task 6 is a lock-in test (change only if red). Task 5 Step 3/4 reference the extracted `enemyArmysFor` defined in the same task.

**Type consistency:** `Plan` (armies, target, label, prediction) consistent Tasks 7/9. `candidate_orders -> list[(label, order)]` consumed in Task 9. `runWithReinforce`/`recordToFrames`/`replayRecord` names consistent Task 4. `buildFrames`/`arriveFrame` Task 3 → used Task 5. Route strings match Global Constraints.

**Residual risk (Task 4):** the reinforcement injection's exact `accAttackIndex`/enemy-append order is validated by the oracle golden against the real record — that test is the acceptance gate; Step 5 names the concrete fix path if it mismatches.
