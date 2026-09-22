"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { loadEngine } = require("../bundle");
const { installAssets } = require("../assets");
const { summarize } = require("../record-summary");
const { counterfactual } = require("../counterfactual-core");

function load(name) {
  const raw = JSON.parse(
    fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8"));
  return raw.record || raw;
}

function boot() {
  let req;
  try { req = loadEngine(); } catch { return null; }
  if (!globalThis.eventCenter) globalThis.eventCenter = { emit() {}, on() {}, off() {}, once() {} };
  if (!globalThis.mc) globalThis.mc = { getModel: () => ({}) };
  installAssets(undefined, req, { playerUid: "1000000000" });
  return req;
}

const ORDERS = ["tank_first", "dps_first", "auto"];

test("counterfactual returns a loss per order", (t) => {
  if (!boot()) { t.skip("engine not available"); return; }
  const out = counterfactual({ record: load("battle_1tile.json"), orders: ORDERS, playerUid: "1000000000" });
  for (const o of ORDERS) {
    assert.ok(o in out.by_order, `has ${o}`);
    assert.strictEqual(typeof out.by_order[o].self_dead, "number");
    assert.strictEqual(typeof out.by_order[o].loss, "number");
  }
});

test("counterfactual is deterministic", (t) => {
  if (!boot()) { t.skip("engine not available"); return; }
  const rec = load("battle_lossy.json");
  const a = counterfactual({ record: rec, orders: ORDERS, playerUid: "1000000000" });
  const b = counterfactual({ record: rec, orders: ORDERS, playerUid: "1000000000" });
  assert.deepStrictEqual(a, b);
});

test("oracle: the 'auto' order reproduces the record's real self_dead", (t) => {
  const req = boot();
  if (!req) { t.skip("engine not available"); return; }
  const rec = load("battle_1tile.json");
  const real = summarize(rec, req, {}).summary.self_dead;
  const cf = counterfactual({ record: rec, orders: ["auto"], playerUid: "1000000000" });
  assert.strictEqual(cf.by_order.auto.self_dead, real,
    "auto counterfactual must match the record's actual losses (fidelity anchor)");
});
