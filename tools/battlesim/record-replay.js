"use strict";
// Convert a real BattleRecordInfo into the driver's frames shape and run it —
// the fidelity oracle. The record already carries the exact fighter ordering
// (attackIndex), pawn stats, randSeed, and reinforcement schedule.

const { runWithReinforce } = require("./reinforce");

function recordToFrames(record) {
  const frames = record.frames || [];
  const init = frames.find((f) => !f.type); // type 0 (field omitted when 0)
  const reinforce = frames.filter((f) => f.type === 1);
  const armys = (init.armys || []).slice();
  const fighters = (init.fighters || []).slice();
  const selfInit = fighters.filter((f) => f.camp === 2).length;
  const enemyTotal = fighters.filter((f) => f.camp === 1).length;
  const waves = reinforce.map((f) => ({
    currentFrameIndex: f.currentFrameIndex,
    army: f.army,
    fighters: (f.fighters || []),
  }));
  const selfReinforce = waves.reduce(
    (n, w) => n + w.fighters.filter((f) => f.camp === 2).length, 0);
  return {
    target: record.index,
    armys,
    fighters,
    randSeed: init.randSeed,
    fps: init.fps || 20,
    hp: init.hp || [0, 0],
    waves,
    selfTotal: selfInit + selfReinforce,
    enemyTotal,
  };
}

function replayRecord(record, req) {
  return runWithReinforce(recordToFrames(record), req);
}

module.exports = { recordToFrames, replayRecord };
