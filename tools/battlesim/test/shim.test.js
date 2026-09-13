const { test } = require("node:test");
const assert = require("node:assert");
const { Vec2 } = require("../cc-shim");

test("Vec2.equals is a static method", () => {
  assert.strictEqual(typeof Vec2.equals, "function");
  assert.strictEqual(Vec2.equals({ x: 1, y: 2 }, { x: 1, y: 2 }), true);
  assert.strictEqual(Vec2.equals({ x: 1, y: 2 }, { x: 1, y: 3 }), false);
  assert.strictEqual(Vec2.equals(null, { x: 1, y: 2 }), false);
});
