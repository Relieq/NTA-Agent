"use strict";
// Shared "record -> blow-by-blow + summary" core. Both the CLI (replay-log.js)
// and the sidecar `replay` method call this so there is ONE implementation of how
// a battle record is replayed and read. The record stores only setup + randSeed;
// the engine regenerates every turn deterministically, so this is the real fight.
// Runs at mul=1 (no fast-forward) and injects reinforcement waves like reinforce.js.

const { recordToFrames } = require("./record-replay");

const MAX_FRAMES = 20000;

// Replay a record and return both the rich event stream and a compact summary.
//   summarize(record, req, {playerUid}) ->
//     { summary:{frames,is_win,self_dead,enemy_dead,self_total,enemy_total},
//       hits:[{by,by_id,target,target_id,target_camp,dmg,hp,frame}],
//       deaths:[{uid,id,camp,frame}], events:[...], enemy_ids:[int], self_ids:[int] }
function summarize(record, req, _opts = {}) {
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
    fighters: f.fighters.slice(), mul: 1, forecast: true,
  });
  const bc = fsp.getBattleController();

  const events = [];
  const hits = [];
  const deaths = [];
  const enemyIds = new Set();
  const selfIds = new Set();
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
      const camp = fi.getCamp ? fi.getCamp() : 0;
      const id = fi.getId ? fi.getId() : 0;
      if (camp === 1 && id) enemyIds.add(id);
      if (camp === 2 && id) selfIds.add(id);
      m[fi.getUid()] = { hp: fi.getCurHp ? fi.getCurHp() : 0,
                         die: fi.isDie ? fi.isDie() : false, id, camp };
    }
    return m;
  };

  let prev = snap();
  let prevActor = null;
  let prevActorId = 0;
  const dt = 1 / (f.fps || 20);
  let n = 0;
  while (fsp.isRunning && n < MAX_FRAMES) {
    const cf = bc.currentFighter;
    const actor = cf && cf.getUid ? cf.getUid() : null;
    if (actor && actor !== prevActor) {
      prevActorId = cf.getId ? cf.getId() : 0;
      events.push({ frame: n, type: "turn", actor, actorId: prevActorId,
                    camp: cf.getCamp ? cf.getCamp() : 0 });
      prevActor = actor;
    }
    fsp.update(dt);
    const cur = snap();
    for (const uid in cur) {
      const b = prev[uid];
      if (!b) continue;
      if (cur[uid].hp < b.hp) {
        const hit = { frame: n, type: "hit", by: actor, by_id: prevActorId,
                      target: uid, target_id: cur[uid].id, target_camp: cur[uid].camp,
                      dmg: b.hp - cur[uid].hp, hp: cur[uid].hp };
        events.push(hit);
        hits.push(hit);
      }
      if (!b.die && cur[uid].die) {
        const d = { frame: n, type: "death", uid, id: cur[uid].id, camp: cur[uid].camp };
        events.push(d);
        deaths.push(d);
      }
    }
    prev = cur;
    n += 1;
  }

  const r = result || { isWin: false, aliveSelf: f.selfTotal, aliveEnemy: f.enemyTotal };
  return {
    summary: {
      frames: n,
      is_win: r.isWin,
      self_dead: f.selfTotal - r.aliveSelf,
      enemy_dead: f.enemyTotal - r.aliveEnemy,
      self_total: f.selfTotal,
      enemy_total: f.enemyTotal,
    },
    hits,
    deaths,
    events,
    enemy_ids: [...enemyIds],
    self_ids: [...selfIds],
  };
}

module.exports = { summarize };
