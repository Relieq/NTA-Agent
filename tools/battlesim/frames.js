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

// Entry direction from attacker cell to target cell (pure index geometry).
// 0=right 1=left 2=down 3=up, clamped to available passPoints.
function entryDir(fromIndex, targetIndex, mapWidth, nPassPoints) {
  const dx = (targetIndex % mapWidth) - (fromIndex % mapWidth);
  const dy = Math.floor(targetIndex / mapWidth) - Math.floor(fromIndex / mapWidth);
  let dir;
  if (Math.abs(dx) >= Math.abs(dy)) dir = dx >= 0 ? 0 : 1;
  else dir = dy >= 0 ? 2 : 3;
  return nPassPoints > 0 ? dir % nPassPoints : 0;
}

// Build { initial:{firstArmy,fighters,randSeed,fps,attackIndexAcc}, waves:[...], target }.
// armies are in SELECTION order; armies[0] is the frame-0 wave.
function buildFrames(input, requireByName) {
  const target = input.targetCellIndex;
  const myUid = String(input.playerUid);
  const randSeed = Math.floor(Number(myUid) / 100) + target;
  const armies = input.armies || [];

  const mapHelper = requireByName("MapHelper").mapHelper;
  const Constant = requireByName("Constant");
  const areaSize = input.areaSize || Constant.DEFAULT_AREA_SIZE || 15;
  const passPoints = mapHelper.getPassPoints(areaSize);
  const mapWidth = input.mapWidth || 600;
  const FIGHT = ((requireByName("Enums").ArmyState || {}).FIGHT) != null
    ? requireByName("Enums").ArmyState.FIGHT : 2;

  let attackIndexAcc = 0;
  const stripArmy = (army) => {
    const dir = entryDir(army.index, target, mapWidth, passPoints.length);
    const entry = passPoints[dir] || passPoints[0] || { x: 0, y: 0 };
    const pawns = (army.pawns || []).slice()
      .sort((a, b) => pawnAttackSpeed(b.id) - pawnAttackSpeed(a.id))
      .map((p) => ({
        index: army.index, uid: p.uid, id: p.id, lv: p.lv,
        hp: p.hp ? (Array.isArray(p.hp) ? p.hp.slice() : [p.hp[0]]) : undefined,
        point: p.point ? { x: p.point.x, y: p.point.y } : { x: entry.x, y: entry.y },
        equip: p.equip, portrayal: p.hero || undefined,
        attackSpeed: pawnAttackSpeed(p.id), buffs: p.buffs || [],
      }));
    const fighters = pawns.map((p) => ({
      uid: p.uid, camp: 2, attackIndex: ++attackIndexAcc, enterIndex: attackIndexAcc,
    }));
    return {
      army: { index: army.index, uid: army.uid, name: army.name || "D1",
              owner: myUid, state: FIGHT, enterDir: dir, pawns },
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
