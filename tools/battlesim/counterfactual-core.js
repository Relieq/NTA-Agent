"use strict";
// Counterfactual: "would a different army order have lost fewer troops?"
// Rebuild a forecast input from a real battle record (our armies + the enemy),
// then run the proven forecast() with our armies reordered per candidate order.
// The record fully self-describes: init.armys carries BOTH our armies (owner set,
// camp 2) and the enemy army (camp 1); init.fighters only carries turn order.
//
// Fidelity anchor: the "auto" order (record's original ordering) reproduces the
// record's actual losses — asserted by the oracle test.

const { forecast } = require("./forecast");


// hp comes as a protobuf map {0:cur} or {0:cur,1:max}, or already an array.
function normHp(hp) {
  if (Array.isArray(hp)) return [hp[0] || 0, hp[1] || hp[0] || 0];
  if (hp && typeof hp === "object") {
    const cur = hp[0] || 0;
    return [cur, hp[1] || cur];
  }
  return [0, 0];
}

function normPawn(p) {
  return {
    uid: String(p.uid),
    id: p.id,
    lv: p.lv || 1,
    hp: normHp(p.hp),
    point: p.point ? { x: p.point.x || 0, y: p.point.y || 0 } : undefined,
  };
}

// Split a record into {ours:[army...], enemy:{pawns...}} using fighter camps.
function partition(record) {
  const frames = record.frames || [];
  const init = frames.find((f) => !f.type) || {};
  const waves = frames.filter((f) => f.type === 1);

  const campByUid = {};
  for (const f of (init.fighters || [])) campByUid[String(f.uid)] = f.camp;
  for (const w of waves)
    for (const f of (w.fighters || [])) campByUid[String(f.uid)] = f.camp;

  const armyCamp = (army) => {
    const camps = (army.pawns || []).map((p) => campByUid[String(p.uid)]).filter((c) => c != null);
    // majority camp; default enemy(1) if unknown so we never mislabel ours as enemy
    const ours = camps.filter((c) => c === 2).length;
    return ours * 2 >= camps.length && ours > 0 ? 2 : 1;
  };

  const ours = [];
  let enemyPawns = [];
  for (const army of (init.armys || [])) {
    if (armyCamp(army) === 2) {
      ours.push({ uid: String(army.uid), name: army.name || "", index: army.index,
                  pawns: (army.pawns || []).map(normPawn) });
    } else {
      enemyPawns = enemyPawns.concat((army.pawns || []).map(normPawn));
    }
  }
  // reinforcement waves are our armies too (they arrive after the lead)
  for (const w of waves) {
    const a = w.army || {};
    ours.push({ uid: String(a.uid), name: a.name || "", index: a.index,
                pawns: (a.pawns || []).map(normPawn) });
  }
  return { ours, enemyPawns, index: record.index, hp: init.hp || [0, 0] };
}

function avgHp(army) {
  const pawns = army.pawns || [];
  if (!pawns.length) return 0;
  return pawns.reduce((s, p) => s + (p.hp[1] || p.hp[0] || 0), 0) / pawns.length;
}

// Reorder our armies so the LEAD (armies[0], fights frame 0 alone) matches the order.
function ordered(ours, order) {
  const a = ours.slice();
  if (order === "tank_first") a.sort((x, y) => avgHp(y) - avgHp(x));   // beefiest leads
  else if (order === "dps_first") a.sort((x, y) => avgHp(x) - avgHp(y)); // squishiest leads
  // "auto" keeps the record's own order (lead army first, then waves)
  return a;
}

function toInput(part, armies, playerUid) {
  return {
    playerUid: String(playerUid || "1000000000"),
    targetCellIndex: part.index,
    landId: 0,
    selfToCellDistance: 1,
    areaSize: null,
    // co-located 1-tile: all arrive together, so order = the armies-array order
    armies: armies.map((a) => ({ uid: a.uid, name: a.name, index: a.index,
                                 marchTime: 0, pawns: a.pawns })),
    enemyArmyConf: {
      index: part.index,
      hp: part.hp,
      armys: [{ index: part.index, uid: "cf_enemy", state: 0, name: "", owner: "",
                pawns: part.enemyPawns }],
    },
  };
}

function counterfactual(params) {
  const { record, orders, playerUid } = params || {};
  const part = partition(record || {});
  const out = { by_order: {} };
  for (const order of (orders || ["tank_first", "dps_first", "auto"])) {
    const input = toInput(part, ordered(part.ours, order), playerUid);
    let r;
    try {
      r = forecast(input);
    } catch (e) {
      out.by_order[order] = { loss: 100, self_dead: -1, error: String(e && e.message || e) };
      continue;
    }
    const s = (r.survivors && r.survivors.self) || { alive: 0, total: 0 };
    out.by_order[order] = {
      loss: r.lossPercent != null ? r.lossPercent : 100,
      self_dead: Math.max(0, (s.total || 0) - (s.alive || 0)),
      is_win: !!r.isWin,
    };
  }
  return out;
}

module.exports = { counterfactual, partition, ordered };
