"use strict";
// Replay a real battle record turn-by-turn and emit the blow-by-blow: for each
// frame, which fighter is acting, who took damage (and how much), and who died.
// The record stores only the SETUP + randSeed; the engine regenerates every turn
// deterministically, so this is the exact real fight. Runs at mul=1 (no fast-forward)
// so no turn is skipped, and injects reinforcement waves like reinforce.js.
//
// CLI:  node tools/battlesim/replay-log.js <record.json> [playerUid]
//   <record.json> is either a raw record or {record, summary} (fetch-tool output).
//   Prints a JSON {events:[...], summary:{...}} to stdout.

const { loadEngine } = require("./bundle");
const { installAssets } = require("./assets");
const { summarize } = require("./record-summary");


// Thin wrapper over the shared summarize() core, kept for the CLI + its historical
// output shape ({events, summary} with camelCase summary keys).
function replayLog(record, req) {
  const out = summarize(record, req);
  return {
    events: out.events,
    summary: {
      frames: out.summary.frames,
      isWin: out.summary.is_win,
      selfDead: out.summary.self_dead,
      enemyDead: out.summary.enemy_dead,
      selfTotal: out.summary.self_total,
      enemyTotal: out.summary.enemy_total,
    },
  };
}


function main() {
  const fs = require("fs");
  const file = process.argv[2];
  const playerUid = process.argv[3] || "1000000000";
  if (!file) {
    process.stderr.write("usage: node replay-log.js <record.json> [playerUid]\n");
    process.exit(2);
  }
  const raw = JSON.parse(fs.readFileSync(file, "utf8"));
  const record = raw.record || raw;   // accept {record,...} or a raw record
  const req = loadEngine();
  if (!globalThis.eventCenter) globalThis.eventCenter = { emit() {}, on() {}, off() {}, once() {} };
  if (!globalThis.mc) globalThis.mc = { getModel: () => ({}) };
  installAssets(undefined, req, { playerUid });
  const out = replayLog(record, req);
  process.stdout.write(JSON.stringify(out, null, 2) + "\n");
  process.exit(0);   // the engine boot leaves handles open; exit cleanly
}

if (require.main === module) main();
module.exports = { replayLog };
