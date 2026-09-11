"use strict";
// Golden/deterministic test: the known matchup must always produce the same
// outcome. Locks the headless engine boot + determinism (Task 1 feasibility gate).
// Run: node --test tools/battlesim/test/

const test = require("node:test");
const assert = require("node:assert");
const { forecast } = require("../forecast");

const KNOWN_INPUT = {
  playerUid: "1000000000",
  targetCellIndex: 109725,
  landId: 0,
  selfToCellDistance: 1,
  areaSize: null,
  armies: [
    {
      uid: "army_ours",
      name: "D1",
      index: 109726,
      marchTime: 0,
      pawns: [{ uid: "p_3101_a", id: 3101, lv: 1, hp: [135, 135] }],
    },
  ],
  enemyArmyConf: {
    index: 109725,
    hp: [25, 25],
    armys: [
      {
        index: 109725,
        uid: "army_enemy",
        state: 0,
        name: "",
        owner: "",
        pawns: [{ uid: "e_4101_a", id: 4101, lv: 1, hp: [25, 25], point: { x: 7, y: 7 } }],
      },
    ],
  },
};

test("known matchup 3101 vs 4101: deterministic win, no loss", () => {
  const out = forecast(KNOWN_INPUT);
  assert.strictEqual(out.isWin, true, "our 3101 should beat a lone 4101");
  assert.strictEqual(out.lossLv, 0, "no pawns lost");
  assert.strictEqual(out.lossPercent, 0);
  assert.deepStrictEqual(out.survivors.self, { alive: 1, total: 1 });
  assert.deepStrictEqual(out.survivors.enemy, { alive: 0, total: 1 });
});

test("determinism: same input yields identical result", () => {
  const a = forecast(KNOWN_INPUT);
  const b = forecast(KNOWN_INPUT);
  assert.deepStrictEqual(a, b);
});
