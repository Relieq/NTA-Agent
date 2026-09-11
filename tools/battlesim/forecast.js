"use strict";
// Drive one headless forecast: build the area, run battleLocalBegin in forecast
// mode, step frames until the engine ends the battle, and report the outcome.

const { loadEngine } = require("./bundle");
const { installAssets } = require("./assets");
const { buildArea } = require("./area-factory");

const FPS = 20;
const FPS_MUL = 400; // client's forecast fast-forward
const MAX_UPDATES = 5000; // hard cap (each update runs FPS_MUL ticks)

let _req = null;

// Minimal global collaborators the battle-end path touches.
function installGlobals() {
  if (!globalThis.eventCenter) {
    globalThis.eventCenter = { emit() {}, on() {}, off() {}, once() {} };
  }
  if (!globalThis.mc) {
    globalThis.mc = { getModel: () => ({}) };
  }
}

function bootstrap(playerUid) {
  if (!_req) {
    _req = loadEngine();
    installGlobals();
  }
  // (re)point config + player context each call — cheap, keeps uid current.
  installAssets(undefined, _req, { playerUid });
  return _req;
}

function loss_lv(pct) {
  if (pct <= 0) return 0;
  if (pct <= 15) return 1;
  if (pct < 50) return 2;
  if (pct < 100) return 3;
  return 4;
}

function forecast(input) {
  const req = bootstrap(input.playerUid);
  const { area, fighters, seed } = buildArea(input, req);

  // Rendering + reddot are no-ops headless.
  area.updatePawnAnimationFrame = () => {};
  if (area.updateTreasureReddot) area.updateTreasureReddot = () => {};

  // Snapshot the result at the moment the engine ends the battle (stop() nulls
  // the controller right after).
  let result = null;
  const origEnd = area.battleEndByLocal.bind(area);
  area.battleEndByLocal = function () {
    if (!result) {
      const bc = area.fspModel && area.fspModel.getBattleController();
      const fs = (bc && bc.getFighters()) || [];
      const aliveIn = (camp) =>
        fs.filter((f) => f.getCamp && f.getCamp() === camp && f.isDie && !f.isDie()).length;
      const self = { alive: aliveIn(2), total: selfTotal };
      const enemy = { alive: aliveIn(1), total: enemyTotal };
      const lostPct = self.total ? (100 * (self.total - self.alive)) / self.total : 100;
      result = {
        isWin: !!(bc && bc.isWin()),
        lossLv: loss_lv(lostPct),
        lossPercent: Math.round(lostPct * 10) / 10,
        survivors: { self, enemy },
      };
    }
    return origEnd();
  };

  // Initial totals per camp (dead fighters get pruned from the controller list,
  // so totals must come from the starting roster). 2 = us, 1 = enemy.
  const selfTotal = fighters.filter((f) => f.camp === 2).length;
  const enemyTotal = fighters.filter((f) => f.camp === 1).length;

  const fspModel = area.battleLocalBegin({
    camp: 1,
    randSeed: seed,
    accAttackIndex: 0,
    fps: FPS,
    fighters,
    mul: FPS_MUL,
    forecast: true,
  });

  const dt = 1 / FPS;
  let n = 0;
  while (fspModel.isRunning && n < MAX_UPDATES && !result) {
    fspModel.update(dt);
    n += 1;
  }
  if (!result) {
    return { isWin: false, lossLv: 5, lossPercent: 100, survivors: null, timedOut: true };
  }
  result.timeMs = Math.round((fspModel.getBattleTime && fspModel.getBattleTime()) || 0);
  return result;
}

module.exports = { forecast, FPS, FPS_MUL };
