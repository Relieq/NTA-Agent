"use strict";
// Reinforcement-aware battle driver. Runs an initial wave on the real engine's
// AreaObj, and injects later waves at their currentFrameIndex by adding the
// arriving army and re-beginning the battle from that frame (mirrors the
// engine's restartBattleWithReinforce, but keeps the running battle's pawns so
// survivors carry over). Returns {isWin, lossLv, lossPercent, survivors}.

const FPS = 20;
const FPS_MUL = 400;
const MAX_UPDATES = 5000;

function loss_lv(pct) {
  if (pct <= 0) return 0;
  if (pct <= 15) return 1;
  if (pct < 50) return 2;
  if (pct < 100) return 3;
  return 4;
}

// frames = { armys, fighters, randSeed, fps, hp, waves:[{currentFrameIndex,army,fighters}],
//            selfTotal, enemyTotal }
function runWithReinforce(frames, req) {
  const AreaObj = req("AreaObj").default;
  const area = new AreaObj().init({
    index: frames.target, owner: "", hp: frames.hp || [0, 0], cityId: 0,
    armys: frames.armys.slice(),
  });
  area.updatePawnAnimationFrame = () => {};
  if (area.updateTreasureReddot) area.updateTreasureReddot = () => {};

  const selfTotal = frames.selfTotal;
  const enemyTotal = frames.enemyTotal;

  let result = null;
  const origEnd = area.battleEndByLocal.bind(area);
  area.battleEndByLocal = function () {
    if (!result) {
      const bc = area.fspModel && area.fspModel.getBattleController();
      const fs = (bc && bc.getFighters()) || [];
      const aliveIn = (c) =>
        fs.filter((f) => f.getCamp && f.getCamp() === c && f.isDie && !f.isDie()).length;
      // Only pawns that ENTERED can die; reinforcements that never arrived (the
      // battle ended first) are fully alive — don't count them as casualties.
      const entered = (c) => allFighters.filter((r) => r.camp === c).length;
      const deadSelf = entered(2) - aliveIn(2);
      const deadEnemy = entered(1) - aliveIn(1);
      const self = { alive: selfTotal - deadSelf, total: selfTotal };
      const enemy = { alive: enemyTotal - deadEnemy, total: enemyTotal };
      const lostPct = self.total ? (100 * deadSelf) / self.total : 100;
      // Per-pawn survival: entered fighters (cross-ref) + un-arrived waves (alive).
      const aliveByUid = {};
      fs.forEach((f) => { if (f.getUid) aliveByUid[f.getUid()] = f; });
      const pawns = allFighters.map((r) => {
        const lf = aliveByUid[r.uid];
        return { uid: r.uid, camp: r.camp,
                 alive: !!(lf && lf.isDie && !lf.isDie()),
                 curHp: lf && lf.getCurHp ? lf.getCurHp() : 0 };
      });
      for (const w of pending)
        for (const wf of w.fighters)
          pawns.push({ uid: wf.uid, camp: wf.camp, alive: true, curHp: null });
      result = {
        isWin: !!(bc && bc.isWin()),
        lossLv: loss_lv(lostPct),
        lossPercent: Math.round(lostPct * 10) / 10,
        survivors: { self, enemy, pawns },
      };
    }
    return origEnd();
  };

  let allFighters = frames.fighters.slice();
  const maxAi = () => allFighters.reduce((m, f) => Math.max(m, f.attackIndex || 0), 0);

  let fsp = area.battleLocalBegin({
    camp: 1, randSeed: frames.randSeed, accAttackIndex: 0, fps: frames.fps || FPS,
    fighters: allFighters, mul: FPS_MUL, forecast: true,
  });

  const pending = (frames.waves || []).slice()
    .sort((a, b) => a.currentFrameIndex - b.currentFrameIndex);
  const dt = 1 / (frames.fps || FPS);
  let frame = 0;
  let n = 0;
  while (fsp.isRunning && n < MAX_UPDATES && !result) {
    while (pending.length && pending[0].currentFrameIndex <= frame && !result) {
      const w = pending.shift();
      area.addArmy(w.army);
      allFighters = allFighters.concat(w.fighters);
      fsp = area.battleLocalBegin({
        camp: 1, randSeed: frames.randSeed, accAttackIndex: maxAi(),
        fps: frames.fps || FPS, fighters: allFighters, mul: FPS_MUL,
        forecast: true, currentFrameIndex: w.currentFrameIndex,
      });
    }
    fsp.update(dt);
    frame += 1;
    n += 1;
  }
  if (!result) {
    return { isWin: false, lossLv: 5, lossPercent: 100, survivors: null, timedOut: true };
  }
  return result;
}

module.exports = { runWithReinforce, FPS };
