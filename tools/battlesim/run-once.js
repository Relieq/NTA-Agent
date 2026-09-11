"use strict";
// Bring-up harness: run one known matchup and print the forecast JSON.
// Our pawn 3101 (lv1 hp135/atk10) attacks an NPC 4101 (lv1 hp25/atk13) one cell away.

const { forecast } = require("./forecast");

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
      index: 109726, // adjacent owned cell
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

const out = forecast(KNOWN_INPUT);
process.stdout.write(JSON.stringify(out, null, 2) + "\n");
process.exit(0); // engine leaves lingering handles; forecast is done, exit cleanly
