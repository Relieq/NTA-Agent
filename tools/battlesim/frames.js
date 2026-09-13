"use strict";
// Build the "frames" abstraction (mirrors the game's BattleRecordInfo frames)
// from a live Forecast Input: one initial wave (first-selected army + enemy) and
// zero-or-more reinforcement waves scheduled by marchTime. Verified against
// ArtofwarForecastObj.startForecast + a real battle record.

const FPS = 20;
const MS_PER_FRAME = 1000 / FPS;

// Arrival frame for a SUBSEQUENT army (i>=1). The first-selected army is frame 0
// and is not passed here. tiebreak = how many earlier armies share this delta.
function arriveFrame(marchTime, baseMarchTime, tiebreak) {
  const delta = marchTime - baseMarchTime;
  return Math.max(1, Math.floor(delta / MS_PER_FRAME)) + tiebreak;
}

function pawnAttackSpeed(id) {
  const base = globalThis.assetsMgr.getJsonData("pawnBase", id);
  return (base && base.attack_speed) || 0;
}

// Build { initial:{firstArmy,fighters,randSeed,fps,attackIndexAcc}, waves:[...], target }.
// armies are in SELECTION order; armies[0] is the frame-0 wave.
function buildFrames(input, requireByName) {
  const target = input.targetCellIndex;
  const myUid = String(input.playerUid);
  const randSeed = Math.floor(Number(myUid) / 100) + target;
  const armies = input.armies || [];

  let attackIndexAcc = 0;
  const stripArmy = (army) => {
    const pawns = (army.pawns || []).slice().sort(
      (a, b) => pawnAttackSpeed(b.id) - pawnAttackSpeed(a.id));
    const fighters = pawns.map((p) => ({
      uid: p.uid, camp: 2, attackIndex: ++attackIndexAcc, enterIndex: attackIndexAcc,
    }));
    return {
      army: { index: army.index, uid: army.uid, name: army.name || "D1",
              owner: myUid, pawns },
      fighters,
    };
  };

  const first = stripArmy(armies[0]);
  const base = armies.length ? (armies[0].marchTime || 0) : 0;
  const seenDelta = {};
  const waves = [];
  for (let i = 1; i < armies.length; i++) {
    const mt = armies[i].marchTime || 0;
    const delta = mt - base;
    const tb = seenDelta[delta] || 0;
    seenDelta[delta] = tb + 1;
    const s = stripArmy(armies[i]);
    waves.push({ currentFrameIndex: arriveFrame(mt, base, tb),
                 army: s.army, fighters: s.fighters });
  }

  return {
    initial: { firstArmy: first.army, fighters: first.fighters, randSeed,
               fps: FPS, attackIndexAcc: first.fighters.length },
    waves, target,
  };
}

module.exports = { buildFrames, arriveFrame, FPS };
