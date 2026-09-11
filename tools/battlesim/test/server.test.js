"use strict";
// Spawn the sidecar and exercise the JSON-RPC protocol over stdio.
// Run: node --test tools/battlesim/test/server.test.js

const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");
const { spawn } = require("node:child_process");

const SERVER = path.resolve(__dirname, "..", "server.js");

const KNOWN_INPUT = {
  playerUid: "1000000000",
  targetCellIndex: 109725,
  armies: [{ uid: "a", name: "D1", index: 109726, pawns: [{ uid: "p", id: 3101, lv: 1, hp: [135, 135] }] }],
  enemyArmyConf: {
    index: 109725,
    hp: [25, 25],
    armys: [{ index: 109725, uid: "e", state: 0, name: "", owner: "", pawns: [{ uid: "e1", id: 4101, lv: 1, hp: [25, 25], point: { x: 7, y: 7 } }] }],
  },
};

// A tiny promise-based JSON-RPC client over the child's stdio.
function client() {
  const child = spawn(process.execPath, [SERVER], { stdio: ["pipe", "pipe", "pipe"] });
  let buf = "";
  const waiters = new Map();
  child.stdout.on("data", (d) => {
    buf += d.toString();
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (!line) continue;
      const msg = JSON.parse(line);
      const w = waiters.get(msg.id);
      if (w) { waiters.delete(msg.id); w(msg); }
    }
  });
  let nextId = 1;
  return {
    call(method, params) {
      const id = nextId++;
      return new Promise((resolve) => {
        waiters.set(id, resolve);
        child.stdin.write(JSON.stringify({ id, method, params }) + "\n");
      });
    },
    close() { child.stdin.end(); child.kill(); },
  };
}

test("ping returns pong", async () => {
  const c = client();
  const res = await c.call("ping", {});
  assert.strictEqual(res.result, "pong");
  c.close();
});

test("forecast returns the known win", async () => {
  const c = client();
  const res = await c.call("forecast", KNOWN_INPUT);
  assert.ok(res.result, "should carry a result");
  assert.strictEqual(res.result.isWin, true);
  assert.strictEqual(res.result.lossLv, 0);
  c.close();
});
