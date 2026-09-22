"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { loadEngine } = require("../bundle");
const { installAssets } = require("../assets");
const { summarize } = require("../record-summary");

function load(name) {
  const raw = JSON.parse(
    fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8"));
  return raw.record || raw;
}

test("summarize a real 1-tile record: deaths + hits + enemy ids", (t) => {
  let req;
  try {
    req = loadEngine();
  } catch {
    t.skip("engine not available");
    return;
  }
  if (!globalThis.eventCenter) globalThis.eventCenter = { emit() {}, on() {}, off() {}, once() {} };
  if (!globalThis.mc) globalThis.mc = { getModel: () => ({}) };
  installAssets(undefined, req, { playerUid: "1000000000" });

  const out = summarize(load("battle_1tile.json"), req, { playerUid: "1000000000" });
  assert.ok(out.summary.frames > 0, "ran some frames");
  assert.strictEqual(typeof out.summary.self_dead, "number");
  assert.strictEqual(typeof out.summary.enemy_dead, "number");
  assert.ok(Array.isArray(out.hits) && out.hits.length > 0, "recorded hits");
  assert.ok(out.hits.every((h) => "by_id" in h && "target_id" in h && "frame" in h));
  assert.ok(out.enemy_ids.length > 0, "found enemy pawn ids");
  assert.ok(out.self_ids.length > 0, "found our pawn ids");
});

test("summarize is deterministic (same record -> same summary)", (t) => {
  let req;
  try {
    req = loadEngine();
  } catch {
    t.skip("engine not available");
    return;
  }
  if (!globalThis.eventCenter) globalThis.eventCenter = { emit() {}, on() {}, off() {}, once() {} };
  if (!globalThis.mc) globalThis.mc = { getModel: () => ({}) };
  installAssets(undefined, req, { playerUid: "1000000000" });
  const a = summarize(load("battle_lossy.json"), req, {});
  const b = summarize(load("battle_lossy.json"), req, {});
  assert.deepStrictEqual(a.summary, b.summary);
});
