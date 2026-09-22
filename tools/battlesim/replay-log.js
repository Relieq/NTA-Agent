"use strict";
// Replay a real battle record turn-by-turn and emit the blow-by-blow: for each
// frame, which fighter is acting, who took damage (and how much), and who died.
// The record stores only the SETUP + randSeed; the engine regenerates every turn
// deterministically, so this is the exact real fight. Runs at mul=1 (no fast-forward)
// so no turn is skipped, and injects reinforcement waves like reinforce.js.
//
// CLI:  node tools/battlesim/replay-log.js <record.json> [playerUid]
//   <record.json> is either a raw record or {record, summary} (fetch-tool output).
//   Prints a JSON {events:[...], summary:{...}} to stdout.

const { loadEngine } = require("./bundle");
const { installAssets } = require("./assets");
const { recordToFrames } = require("./record-replay");

const MAX_FRAMES = 20000;


function replayLog(record, req) {
  const f = recordToFrames(record);
  const AreaObj = req("AreaObj").default;
  const area = new AreaObj().init({
    index: f.target, owner: "", hp: f.hp || [0, 0], cityId: 0, armys: f.armys.slice(),
  });
  area.updatePawnAnimationFrame = () => {};
  if (area.updateTreasureReddot) area.updateTreasureReddot = () => {};

  // Capture the outcome at battle end, before the engine nulls the controller.
  let result = null;
  const origEnd = area.battleEndByLocal.bind(area);
  area.battleEndByLocal = function () {
    if (!result) {
      const c = area.fspModel && area.fspModel.getBattleController();
      const fs = (c && c.getFighters()) || [];
      const alive = (camp) =>
        fs.filter((x) => x.getCamp && x.getCamp() === camp && x.isDie && !x.isDie()).length;
      result = { isWin: !!(c && c.isWin && c.isWin()), aliveSelf: alive(2), aliveEnemy: alive(1) };
    }
    return origEnd();
  };

  const fsp = area.battleLocalBegin({
    camp: 1, randSeed: f.randSeed, accAttackIndex: 0, fps: f.fps || 20,
    fighters: f.fighters.slice(), mul: 1, forecast: true,   // mul=1: inspect every frame
  });
  const bc = fsp.getBattleController();

  const events = [];
  const byFrame = {};
  for (const w of (f.waves || [])) (byFrame[w.currentFrameIndex] = byFrame[w.currentFrameIndex] || []).push(w);
  fsp.setCheckHasFrameData(function (frameIndex) {
    const ws = byFrame[frameIndex];
    if (!ws) return;
    delete byFrame[frameIndex];
    for (const w of ws) {
      const acc = bc.getCurAccAttackIndex();
      w.fighters.forEach((x, i) => { x.attackIndex = acc + i + 1; x.enterIndex = acc + i + 1; });
      fsp.checkHasFrameDataItem({ type: 1, army: w.army, fighters: w.fighters });
      events.push({ frame: frameIndex, type: "reinforce", army: w.army.name });
    }
  });

  const snap = () => {
    const m = {};
    for (const fi of (bc.getFighters() || [])) {
      if (!fi.getUid) continue;
      m[fi.getUid()] = {
        hp: fi.getCurHp ? fi.getCurHp() : 0,
        die: fi.isDie ? fi.isDie() : false,
        id: fi.getId ? fi.getId() : 0,
        camp: fi.getCamp ? fi.getCamp() : 0,
      };
    }
    return m;
  };

  let prev = snap();
  let prevActor = null;
  const dt = 1 / (f.fps || 20);
  let n = 0;
  while (fsp.isRunning && n < MAX_FRAMES) {
    const cf = bc.currentFighter;
    const actor = cf && cf.getUid ? cf.getUid() : null;
    if (actor && actor !== prevActor) {   // a new fighter's turn begins
      events.push({ frame: n, type: "turn", actor,
                    actorId: cf.getId ? cf.getId() : 0,
                    camp: cf.getCamp ? cf.getCamp() : 0 });
      prevActor = actor;
    }
    fsp.update(dt);
    const cur = snap();
    for (const uid in cur) {
      const b = prev[uid];
      if (!b) continue;
      if (cur[uid].hp < b.hp) {
        events.push({ frame: n, type: "hit", by: actor, target: uid,
                      targetId: cur[uid].id, targetCamp: cur[uid].camp,
                      dmg: b.hp - cur[uid].hp, hp: cur[uid].hp });
      }
      if (!b.die && cur[uid].die) {
        events.push({ frame: n, type: "death", uid, id: cur[uid].id, camp: cur[uid].camp });
      }
    }
    prev = cur;
    n += 1;
  }

  const r = result || { isWin: false, aliveSelf: f.selfTotal, aliveEnemy: f.enemyTotal };
  return {
    events,
    summary: {
      frames: n,
      isWin: r.isWin,
      selfDead: f.selfTotal - r.aliveSelf,
      enemyDead: f.enemyTotal - r.aliveEnemy,
      selfTotal: f.selfTotal, enemyTotal: f.enemyTotal,
    },
  };
}


function main() {
  const fs = require("fs");
  const file = process.argv[2];
  const playerUid = process.argv[3] || "1000000000";
  if (!file) {
    process.stderr.write("usage: node replay-log.js <record.json> [playerUid]\n");
    process.exit(2);
  }
  const raw = JSON.parse(fs.readFileSync(file, "utf8"));
  const record = raw.record || raw;   // accept {record,...} or a raw record
  const req = loadEngine();
  if (!globalThis.eventCenter) globalThis.eventCenter = { emit() {}, on() {}, off() {}, once() {} };
  if (!globalThis.mc) globalThis.mc = { getModel: () => ({}) };
  installAssets(undefined, req, { playerUid });
  const out = replayLog(record, req);
  process.stdout.write(JSON.stringify(out, null, 2) + "\n");
  process.exit(0);   // the engine boot leaves handles open; exit cleanly
}

if (require.main === module) main();
module.exports = { replayLog };
