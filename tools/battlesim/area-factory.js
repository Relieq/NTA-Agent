"use strict";
// Build an AreaObj + the fighter ordering list from a Forecast Input, replicating
// the client's forecast setup (ArtofwarForecastObj.toArmyStrip / getEnemyArmys)
// but without the world model — direction/entry come from pure-geometry mapHelper.

// Entry direction: the engine's getAddArmyDir, ported without the world model.
const { entryDir } = require("./entry-dir");

function pawnAttackSpeed(pawnBaseId) {
  const base = globalThis.assetsMgr.getJsonData("pawnBase", pawnBaseId);
  return (base && base.attack_speed) || 0;
}

// Our attacking pawns: placed at the army's entry point, sorted fastest-first.
function ourPawnStrips(army, entryPoint) {
  const strips = army.pawns.map((p) => ({
    index: army.index,
    uid: p.uid,
    id: p.id,
    lv: p.lv,
    hp: p.hp ? [p.hp[0], p.hp[1]] : undefined,
    point: { x: entryPoint.x, y: entryPoint.y },
    equip: p.equip,
    portrayal: p.hero || undefined,
    attackSpeed: pawnAttackSpeed(p.id),
    buffs: p.buffs || [],
  }));
  strips.sort((a, b) => b.attackSpeed - a.attackSpeed);
  return strips;
}

// Returns { area, fighters, seed } ready for battleLocalBegin(forecast).
function buildArea(input, requireByName) {
  const mapHelper = requireByName("MapHelper").mapHelper;
  const Enums = requireByName("Enums");
  const AreaObj = requireByName("AreaObj").default;
  const Constant = requireByName("Constant");

  const FIGHT = (Enums.ArmyState && Enums.ArmyState.FIGHT) != null ? Enums.ArmyState.FIGHT : 2;
  const areaSize = input.areaSize || Constant.DEFAULT_AREA_SIZE || 15;
  const passPoints = mapHelper.getPassPoints(areaSize);

  const target = input.targetCellIndex;
  const myUid = String(input.playerUid);
  const mapWidth = input.mapWidth || 600;

  // --- our armies (selection order preserved) -------------------------- //
  // Each selected army enters at its own entry point; pawns are ordered fastest
  // -first within an army, and attackIndex continues across armies in SELECTION
  // order (army 0's pawns act before army 1's) — this seeds the turn sequence,
  // which is what the 1-tile tactic exploits (archers selected first, tank last).
  const firstEntry = passPoints[entryDir(input.armies[0].index, target, mapWidth, passPoints.length,
    input.mainCityIndex)]
    || passPoints[0];
  const ourArmys = input.armies.map((army) => {
    const dir = entryDir(army.index, target, mapWidth, passPoints.length, input.mainCityIndex);
    const entry = passPoints[dir] || passPoints[0];
    return {
      index: army.index,
      uid: army.uid,
      name: army.name || "D1",
      owner: myUid,
      state: FIGHT,
      pawns: ourPawnStrips(army, entry),
      enterDir: dir,
    };
  });
  const entry = firstEntry;  // enemy ordering references the lead army's entry

  // --- enemy ----------------------------------------------------------- //
  // Explicit conf, or generated from land config (defenders carry their points).
  const enemyConf =
    input.enemyArmyConf ||
    requireByName("GameHelper").gameHpr.getAreaPawnConfInfo(
      target,
      input.landId,
      input.selfToCellDistance
    );
  enemyConf.armys.forEach((a) => {
    a.state = FIGHT;
    a.owner = a.owner || "";
    a.pawns.sort((p, q) => {
      const ps = 100 * pawnAttackSpeed(p.id) + (99 - mapHelper.getPointToPointDis(p.point, entry));
      const qs = 100 * pawnAttackSpeed(q.id) + (99 - mapHelper.getPointToPointDis(q.point, entry));
      return qs - ps;
    });
  });

  const hp = enemyConf.hp || [0, 0];
  const area = new AreaObj().init({
    index: target,
    owner: "",
    hp,
    cityId: 0,
    armys: [...ourArmys, ...enemyConf.armys],
  });

  // --- fighter ordering (attackIndex/enterIndex): our armies (selection order),
  //     then enemy --- //
  let acc = 0;
  const fighters = [];
  for (const a of ourArmys)
    for (const p of a.pawns) fighters.push({ uid: p.uid, camp: 2, attackIndex: ++acc, enterIndex: acc });
  for (const a of enemyConf.armys)
    for (const p of a.pawns) fighters.push({ uid: p.uid, camp: 1, attackIndex: ++acc, enterIndex: acc });

  const seed = Math.floor(Number(myUid) / 100) + target;
  return { area, fighters, seed, hp };
}

// Enemy defenders for a target, as {armys, hp}: explicit conf or generated from
// land config; sorted by the engine's key (100*attackSpeed + (99-dist to entry)).
// `entry` is the entry point our lead army funnels to.
function enemyArmysFor(input, requireByName, entry) {
  const mapHelper = requireByName("MapHelper").mapHelper;
  const conf =
    input.enemyArmyConf ||
    requireByName("GameHelper").gameHpr.getAreaPawnConfInfo(
      input.targetCellIndex, input.landId, input.selfToCellDistance);
  conf.armys.forEach((a) => {
    a.state = a.state || 2;
    a.owner = a.owner || "";
    a.pawns.sort((p, q) => {
      const ps = 100 * pawnAttackSpeed(p.id) + (99 - mapHelper.getPointToPointDis(p.point, entry));
      const qs = 100 * pawnAttackSpeed(q.id) + (99 - mapHelper.getPointToPointDis(q.point, entry));
      return qs - ps;
    });
  });
  return { armys: conf.armys, hp: conf.hp || [0, 0] };
}

module.exports = { buildArea, enemyArmysFor };
