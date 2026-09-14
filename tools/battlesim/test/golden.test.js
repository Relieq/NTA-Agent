"use strict";
// Golden/deterministic test: the known matchup must always produce the same
// outcome. Locks the headless engine boot + determinism (Task 1 feasibility gate).
// Run: node --test tools/battlesim/test/

const test = require("node:test");
const assert = require("node:assert");
const { forecast } = require("../forecast");

const KNOWN_INPUT = {
  playerUid: "1000000000",
  targetCellIndex: 109725,
  landId: 0,
  selfToCellDistance: 1,
  areaSize: null,
  armies: [
    {
      uid: "army_ours",
      name: "D1",
      index: 109726,
      marchTime: 0,
      pawns: [{ uid: "p_3101_a", id: 3101, lv: 1, hp: [135, 135] }],
    },
  ],
  enemyArmyConf: {
    index: 109725,
    hp: [25, 25],
    armys: [
      {
        index: 109725,
        uid: "army_enemy",
        state: 0,
        name: "",
        owner: "",
        pawns: [{ uid: "e_4101_a", id: 4101, lv: 1, hp: [25, 25], point: { x: 7, y: 7 } }],
      },
    ],
  },
};

test("known matchup 3101 vs 4101: deterministic win, no loss", () => {
  const out = forecast(KNOWN_INPUT);
  assert.strictEqual(out.isWin, true, "our 3101 should beat a lone 4101");
  assert.strictEqual(out.lossLv, 0, "no pawns lost");
  assert.strictEqual(out.lossPercent, 0);
  assert.deepStrictEqual(out.survivors.self, { alive: 1, total: 1 });
  assert.deepStrictEqual(out.survivors.enemy, { alive: 0, total: 1 });
});

test("determinism: same input yields identical result", () => {
  const a = forecast(KNOWN_INPUT);
  const b = forecast(KNOWN_INPUT);
  assert.deepStrictEqual(a, b);
});

const fs = require("node:fs");
const path = require("node:path");

test("oracle: replaying the real 1-tile record reproduces its outcome", (t) => {
  const enginePath = process.env.NTA_ENGINE_JS || "tools/re/decrypted/index.js";
  if (!fs.existsSync(enginePath)) {
    t.skip("engine bundle absent");
    return;
  }
  const { replayRecord } = require("../record-replay");
  const fixture = JSON.parse(
    fs.readFileSync(path.join(__dirname, "fixtures", "battle_1tile.json"), "utf8"));
  const { loadEngine } = require("../bundle");
  const { installAssets } = require("../assets");
  if (!globalThis.eventCenter) globalThis.eventCenter = { emit() {}, on() {}, off() {}, once() {} };
  if (!globalThis.mc) globalThis.mc = { getModel: () => ({}) };
  const req = loadEngine();
  installAssets(undefined, req, { playerUid: "57696053" });
  const out = replayRecord(fixture.record, req);
  assert.strictEqual(out.isWin, true, "record says win");
  assert.strictEqual(out.survivors.self.alive, out.survivors.self.total, "record has 0 dead");
});

test("oracle: replaying a real lossy record matches its win + dead count", (t) => {
  const enginePath = process.env.NTA_ENGINE_JS || "tools/re/decrypted/index.js";
  if (!fs.existsSync(enginePath)) { t.skip("engine absent"); return; }
  const { replayRecord } = require("../record-replay");
  const fixture = JSON.parse(
    fs.readFileSync(path.join(__dirname, "fixtures", "battle_lossy.json"), "utf8"));
  const { loadEngine } = require("../bundle");
  const { installAssets } = require("../assets");
  if (!globalThis.eventCenter) globalThis.eventCenter = { emit() {}, on() {}, off() {}, once() {} };
  if (!globalThis.mc) globalThis.mc = { getModel: () => ({}) };
  const req = loadEngine();
  installAssets(undefined, req, { playerUid: "57696053" });
  const out = replayRecord(fixture.record, req);
  const realDead = (fixture.summary.deadInfo || []).length;
  assert.strictEqual(out.isWin, fixture.summary.isWin, "win must match the record");
  const simDead = out.survivors.self.total - out.survivors.self.alive;
  assert.strictEqual(simDead, realDead, `sim dead (${simDead}) must match real (${realDead})`);
});

test("oracle: real reinforcement record — un-arrived wave counts alive, not dead", (t) => {
  const enginePath = process.env.NTA_ENGINE_JS || "tools/re/decrypted/index.js";
  if (!fs.existsSync(enginePath)) { t.skip("engine absent"); return; }
  const { replayRecord } = require("../record-replay");
  const fixture = JSON.parse(
    fs.readFileSync(path.join(__dirname, "fixtures", "battle_reinforce.json"), "utf8"));
  const { loadEngine } = require("../bundle");
  const { installAssets } = require("../assets");
  if (!globalThis.eventCenter) globalThis.eventCenter = { emit() {}, on() {}, off() {}, once() {} };
  if (!globalThis.mc) globalThis.mc = { getModel: () => ({}) };
  const req = loadEngine();
  installAssets(undefined, req, { playerUid: "57696053" });
  const out = replayRecord(fixture.record, req);
  // real: win, exactly 1 dead (the 2nd army arrived after the fight was won).
  assert.strictEqual(out.isWin, fixture.summary.isWin);
  const simDead = out.survivors.self.total - out.survivors.self.alive;
  assert.strictEqual(simDead, (fixture.summary.deadInfo || []).length);
});

test("multi-army forecast routes through reinforcement and is order-sensitive", (t) => {
  const enginePath = process.env.NTA_ENGINE_JS || "tools/re/decrypted/index.js";
  if (!fs.existsSync(enginePath)) {
    t.skip("engine bundle absent");
    return;
  }
  const enemy = {
    index: 109725, hp: [100, 100],
    armys: [{
      index: 109725, uid: "e", state: 0, name: "", owner: "",
      pawns: Array.from({ length: 12 }, (_, i) => ({
        uid: "e" + i, id: 4101, lv: 2, point: { x: 6 + (i % 4), y: 6 + ((i / 4) | 0) } })),
    }],
  };
  const cung = { uid: "ac", name: "Cung", index: 109726, marchTime: 0,
    pawns: Array.from({ length: 5 }, (_, i) => ({ uid: "c" + i, id: 3305, lv: 1 })) };
  const tank = { uid: "at", name: "Tank", index: 109726, marchTime: 0,
    pawns: Array.from({ length: 5 }, (_, i) => ({ uid: "t" + i, id: 3101, lv: 1 })) };
  const mk = (armies) => forecast({ playerUid: "1000000000", targetCellIndex: 109725,
    landId: 0, selfToCellDistance: 1, areaSize: null, armies, enemyArmyConf: enemy });
  const a = mk([cung, tank]); // cung first (1-tile)
  const b = mk([tank, cung]); // tank first
  assert.strictEqual(a.isWin, true, "cung-first should win");
  assert.strictEqual(b.isWin, true, "tank-first should win");
  assert.ok(a.lossPercent <= b.lossPercent,
    `cung-first (${a.lossPercent}) should be <= tank-first (${b.lossPercent})`);
});

test("formation: beefy-front survives more than squishy-front", (t) => {
  const enginePath = process.env.NTA_ENGINE_JS || "tools/re/decrypted/index.js";
  if (!fs.existsSync(enginePath)) { t.skip("engine absent"); return; }
  const { loadEngine } = require("../bundle");
  const { installAssets } = require("../assets");
  const { runWithReinforce } = require("../reinforce");
  if (!globalThis.eventCenter) globalThis.eventCenter = { emit() {}, on() {}, off() {}, once() {} };
  if (!globalThis.mc) globalThis.mc = { getModel: () => ({}) };
  const req = loadEngine();
  installAssets(undefined, req, { playerUid: "1000000000" });
  const TARGET = 109725, SEED = Math.floor(1000000000 / 100) + TARGET;
  const run = (pts) => {
    const our = { index: 109726, uid: "tank", name: "T", owner: "1000000000", state: 2,
      pawns: [
        { index: TARGET, uid: "big", id: 3101, lv: 1, attackSpeed: 6, point: pts[0], hp: [200, 200] },
        { index: TARGET, uid: "mid", id: 3101, lv: 1, attackSpeed: 6, point: pts[1], hp: [80, 80] },
        { index: TARGET, uid: "sml", id: 3101, lv: 1, attackSpeed: 6, point: pts[2], hp: [50, 50] }] };
    const enemy = { index: TARGET, uid: "e", name: "", owner: "", state: 2,
      pawns: Array.from({ length: 4 }, (_, i) => ({ index: TARGET, uid: "e" + i, id: 4101, lv: 1,
        attackSpeed: 7, point: { x: 4 + (i % 3), y: 6 + ((i / 3) | 0) }, hp: [60, 60] })) };
    let acc = 0; const f = [];
    for (const p of our.pawns) f.push({ uid: p.uid, camp: 2, attackIndex: ++acc, enterIndex: acc });
    for (const p of enemy.pawns) f.push({ uid: p.uid, camp: 1, attackIndex: ++acc, enterIndex: acc });
    return runWithReinforce({ target: TARGET, armys: [our, enemy], fighters: f, randSeed: SEED,
      fps: 20, hp: [100, 100], waves: [], selfTotal: 3, enemyTotal: 4 }, req);
  };
  const a = run([{ x: 6, y: 7 }, { x: 9, y: 7 }, { x: 10, y: 7 }]); // big front
  const b = run([{ x: 10, y: 7 }, { x: 9, y: 7 }, { x: 6, y: 7 }]); // small front
  assert.ok(a.survivors.self.alive > b.survivors.self.alive,
    `big-front (${a.survivors.self.alive}) should outlast small-front (${b.survivors.self.alive})`);
  assert.ok(Array.isArray(a.survivors.pawns));
  assert.strictEqual(a.survivors.pawns.filter((p) => p.camp === 2).length, 3);
});
