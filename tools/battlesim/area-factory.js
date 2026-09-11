"use strict";
// Build an AreaObj + the fighter ordering list from a Forecast Input, replicating
// the client's forecast setup (ArtofwarForecastObj.toArmyStrip / getEnemyArmys)
// but without the world model — direction/entry come from pure-geometry mapHelper.

// Entry direction from attacker cell to target cell, from pure index geometry
// (avoids the world model). 0=right 1=left 2=down 3=up, clamped to passPoints.
function entryDir(fromIndex, targetIndex, mapWidth, nPassPoints) {
  const dx = (targetIndex % mapWidth) - (fromIndex % mapWidth);
  const dy = Math.floor(targetIndex / mapWidth) - Math.floor(fromIndex / mapWidth);
  let dir;
  if (Math.abs(dx) >= Math.abs(dy)) dir = dx >= 0 ? 0 : 1;
  else dir = dy >= 0 ? 2 : 3;
  return nPassPoints > 0 ? dir % nPassPoints : 0;
}

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

  // --- our army -------------------------------------------------------- //
  const army = input.armies[0];
  const dir = entryDir(army.index, target, mapWidth, passPoints.length);
  const entry = passPoints[dir] || passPoints[0];
  const ourPawns = ourPawnStrips(army, entry);
  const ourArmy = {
    index: army.index,
    uid: army.uid,
    name: army.name || "D1",
    owner: myUid,
    state: FIGHT,
    pawns: ourPawns,
    enterDir: dir,
  };

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
    armys: [ourArmy, ...enemyConf.armys],
  });

  // --- fighter ordering (attackIndex/enterIndex), our side then enemy --- //
  let acc = 0;
  const fighters = [];
  for (const p of ourPawns) fighters.push({ uid: p.uid, camp: 2, attackIndex: ++acc, enterIndex: acc });
  for (const a of enemyConf.armys)
    for (const p of a.pawns) fighters.push({ uid: p.uid, camp: 1, attackIndex: ++acc, enterIndex: acc });

  const seed = Math.floor(Number(myUid) / 100) + target;
  return { area, fighters, seed, hp };
}

module.exports = { buildArea };
