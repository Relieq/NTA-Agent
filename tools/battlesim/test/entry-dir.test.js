"use strict";
// Pure (no engine): entry direction must match the server's enterDir.
const test = require("node:test");
const assert = require("node:assert/strict");
const { entryDir, dirByPoint } = require("../entry-dir");

const W = 600;
const idx = (x, y) => y * W + x;

test("engine getDirByPoint mapping", () => {
  assert.equal(dirByPoint({ x: 5, y: 5 }, { x: 5, y: 1 }), 0); // target row smaller
  assert.equal(dirByPoint({ x: 5, y: 1 }, { x: 5, y: 5 }), 2); // target row larger
  assert.equal(dirByPoint({ x: 5, y: 5 }, { x: 1, y: 5 }), 1); // target to the left
  assert.equal(dirByPoint({ x: 1, y: 5 }, { x: 5, y: 5 }), 3); // target to the right
  assert.equal(dirByPoint({ x: 0, y: 0 }, { x: 3, y: 3 }), 2); // tie -> vertical
  assert.equal(dirByPoint({ x: 0, y: 0 }, { x: 3, y: -3 }), 0);
});

test("live 2026-09-25 04:37: bridge (571,113) -> (571,109) entered from edge 0", () => {
  // the battle record carried enterDir 0 (omitted = 0) and pawns at (5,10)
  assert.equal(entryDir(idx(571, 113), idx(571, 109), W, 4), 0);
});

test("2x2 main city launches from its nearest cell", () => {
  const city = idx(572, 118); // cells (572..573, 118..119)
  // target (576,114): from (573,118) dx=3 dy=-4 -> vertical -> 0; from the
  // top-left cell alone dx=4 dy=-4 would also be 0 — pick one where it differs:
  // target (577,117): nearest city cell (573,118) dx=4 dy=-1 -> 3
  assert.equal(entryDir(city, idx(577, 117), W, 4, city), 3);
  // an index inside the block (not top-left) is the same city
  assert.equal(entryDir(city + 601, idx(577, 117), W, 4, city), 3);
  // target straight below the city: nearest is a bottom cell -> dy>0 -> 2
  assert.equal(entryDir(city, idx(572, 125), W, 4, city), 2);
});
