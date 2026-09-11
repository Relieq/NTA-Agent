"use strict";
// Wire the globals the game reads at runtime: `assetsMgr` (config tables) and the
// player-context accessors on the real `gameHpr` (GameHelper) singleton that the
// battle/forecast path touches. Reuses the bundle's own generators where present.

const fs = require("fs");
const path = require("path");

const DEFAULT_CONFIG_DIR =
  process.env.NTA_CONFIG_DIR ||
  path.resolve(__dirname, "..", "..", "nta_agent", "data", "config");

function makeAssetsMgr(configDir) {
  const rawCache = new Map(); // table -> array of rows
  const idCache = new Map(); // table -> Map(id -> row)

  function rows(table) {
    if (!rawCache.has(table)) {
      const file = path.join(configDir, table + ".json");
      const data = JSON.parse(fs.readFileSync(file, "utf8"));
      rawCache.set(table, Array.isArray(data) ? data : Object.values(data));
    }
    return rawCache.get(table);
  }

  function index(table) {
    if (!idCache.has(table)) {
      const m = new Map();
      for (const r of rows(table)) if (r && r.id != null) m.set(r.id, r);
      idCache.set(table, m);
    }
    return idCache.get(table);
  }

  return {
    // Whole table wrapper: the game reads `.datas` (an array with Array extensions).
    getJson(table) {
      return { datas: rows(table) };
    },
    // One row by id (pawnAttr is keyed by id*1000+lv, already the row's `id`).
    getJsonData(table, id) {
      return index(table).get(id) || null;
    },
  };
}

// Install into globals + patch the real gameHpr with the leaf accessors the
// forecast path needs. `playerUid` sets what getUid() returns.
function installAssets(configDir = DEFAULT_CONFIG_DIR, requireByName, { playerUid = "0" } = {}) {
  globalThis.assetsMgr = makeAssetsMgr(configDir);

  // The real GameHelper singleton.
  const gameHpr = requireByName("GameHelper").gameHpr;
  gameHpr.uid = String(playerUid);
  gameHpr.isNoviceMode = false;
  // Player/user context accessors the pawn-init + cost path reads. `user` is a
  // getter returning the user model — patch methods onto it, don't reassign.
  let userModel;
  try { userModel = gameHpr.user; } catch (_e) { userModel = null; }
  if (userModel) {
    if (typeof userModel.getUid !== "function") userModel.getUid = () => String(playerUid);
    if (typeof userModel.getSid !== "function") userModel.getSid = () => 1;
    if (typeof userModel.getMainCityIndex !== "function") userModel.getMainCityIndex = () => 0;
  }
  // Pawn cost is a server-provided map (0 when absent) — safe to stub as 0.
  for (const key of ["world", "lobby"]) {
    let model;
    try { model = gameHpr[key]; } catch (_e) { model = null; }
    if (model && typeof model.getPawnBaseCost !== "function") model.getPawnBaseCost = () => 0;
  }
  if (!globalThis.viewHelper) {
    globalThis.viewHelper = { isInGameScene: () => false, gotoWind() {}, showAlert() {} };
  }
  // Guide model: report the tutorial finished so novice special-casing is skipped.
  let guide;
  try { guide = gameHpr.guide; } catch (_e) { guide = null; }
  if (guide && typeof guide.getIsFinishGuideID !== "function") guide.getIsFinishGuideID = () => true;

  // Model accessors the pawn HP-recovery/attr path reads; null => normal branch.
  const patch = (obj, methods) => {
    for (const [m, fn] of Object.entries(methods)) {
      if (obj && typeof obj[m] !== "function") obj[m] = fn;
    }
  };
  let areaCenter, world, player;
  try { areaCenter = gameHpr.areaCenter; } catch (_e) { areaCenter = null; }
  try { world = gameHpr.world; } catch (_e) { world = null; }
  try { player = gameHpr.player; } catch (_e) { player = null; }
  patch(areaCenter, { getArmy: () => null, getLookArea: () => null, getArea: () => null });
  patch(world, { getMapCellByIndex: () => null });
  patch(player, {
    recordKillCount: () => {},
    setBattleForecastRetMap: () => {},
    getBattleForecastRetData: () => null,
    getMainCityIndex: () => 0,
  });
  // Equip lookups for config-generated enemies (beasts/caterans); benign defaults.
  if (!gameHpr.noviceServer) {
    gameHpr.noviceServer = { getEnemyEquipById: () => null, setEnemyEquip: () => {} };
  }
  // Policy buffs are optional for a bare forecast; neutral season (no seasonal attr).
  gameHpr.getPolicyBattleBuffs = () => [];
  gameHpr.getCurrSeasonType = () => 0;
  return { assetsMgr: globalThis.assetsMgr, gameHpr };
}

module.exports = { installAssets, makeAssetsMgr, DEFAULT_CONFIG_DIR };
