"use strict";
// Minimal Cocos (`cc`) global so the game's battle modules load & run headless.
// Built up from real "missing symbol" errors — keep it as small as it can be.

// The engine logs per-frame; silence unless tracing (keeps forecasts fast + stdout clean).
function log(...a) { if (process.env.NTA_CC_LOG) process.stderr.write("[cc] " + a.join(" ") + "\n"); }

// A tiny 2D vector with the ops the battle path uses.
class Vec2 {
  constructor(x = 0, y = 0) { this.x = x; this.y = y; }
  set2(x, y) { this.x = x; this.y = y; return this; }
  set(o) { this.x = o.x; this.y = o.y; return this; }
  clone() { return new Vec2(this.x, this.y); }
  add(o, out) { const r = out || new Vec2(); r.x = this.x + o.x; r.y = this.y + o.y; return r; }
  addSelf(o) { this.x += o.x; this.y += o.y; return this; }
  sub(o, out) { const r = out || new Vec2(); r.x = this.x - o.x; r.y = this.y - o.y; return r; }
  subSelf(o) { this.x -= o.x; this.y -= o.y; return this; }
  mul(n, out) { const r = out || new Vec2(); r.x = this.x * n; r.y = this.y * n; return r; }
  mulSelf(n) { this.x *= n; this.y *= n; return this; }
  div(n, out) { const r = out || new Vec2(); r.x = this.x / n; r.y = this.y / n; return r; }
  divSelf(n) { this.x /= n; this.y /= n; return this; }
  scale(o, out) { const r = out || new Vec2(); r.x = this.x * o.x; r.y = this.y * o.y; return r; }
  floor(out) { const r = out || new Vec2(); r.x = Math.floor(this.x); r.y = Math.floor(this.y); return r; }
  floorSelf() { this.x = Math.floor(this.x); this.y = Math.floor(this.y); return this; }
  neg(out) { const r = out || new Vec2(); r.x = -this.x; r.y = -this.y; return r; }
  negSelf() { this.x = -this.x; this.y = -this.y; return this; }
  dot(o) { return this.x * o.x + this.y * o.y; }
  equals(o) { return !!o && this.x === o.x && this.y === o.y; }
  mag() { return Math.sqrt(this.x * this.x + this.y * this.y); }
  magSqr() { return this.x * this.x + this.y * this.y; }
  len() { return this.mag(); }
  normalize() { const m = this.mag() || 1; this.x /= m; this.y /= m; return this; }
  Join() { return this.x + "," + this.y; }
}
// Static helpers the engine calls as cc.Vec2.equals(a, b) etc. (pathfinding).
Vec2.equals = (a, b) => !!a && !!b && a.x === b.x && a.y === b.y;

class Vec3 {
  constructor(x = 0, y = 0, z = 0) { this.x = x; this.y = y; this.z = z; }
  set3(x, y, z) { this.x = x; this.y = y; this.z = z; return this; }
  clone() { return new Vec3(this.x, this.y, this.z); }
  add(o, out) { const r = out || new Vec3(); r.x = this.x + o.x; r.y = this.y + o.y; r.z = this.z + (o.z || 0); return r; }
  sub(o, out) { const r = out || new Vec3(); r.x = this.x - o.x; r.y = this.y - o.y; r.z = this.z - (o.z || 0); return r; }
}

function makeEnum(obj) { return obj; }

// A decorator that works both bare (`@ccclass`) and called (`@ccclass("X")`).
function decorator(...args) {
  // Called as a factory: @property(type) -> returns a decorator.
  if (args.length === 0 || typeof args[0] !== "function") {
    return function () {};
  }
  // Used bare on a class/target.
  return args[0];
}
const _decorator = new Proxy(
  { ccclass: decorator, property: decorator },
  { get: (t, p) => (p in t ? t[p] : decorator) }
);

const cc = {
  _RF: { push() {}, pop() {} },
  v2: (x = 0, y = 0) => new Vec2(x, y),
  Vec2,
  v3: (x = 0, y = 0, z = 0) => new Vec3(x, y, z),
  Vec3,
  mat4: () => ({}),
  misc: {
    clampf: (v, mn, mx) => Math.max(mn, Math.min(mx, v)),
    clamp01: (v) => Math.max(0, Math.min(1, v)),
    lerp: (a, b, t) => a + (b - a) * t,
    degreesToRadians: (d) => (d * Math.PI) / 180,
    radiansToDegrees: (r) => (r * 180) / Math.PI,
  },
  _decorator,
  size: (width = 0, height = 0) => ({ width, height }),
  rect: (x = 0, y = 0, width = 0, height = 0) => ({ x, y, width, height }),
  sys: { isBrowser: false, isNative: true, os: "nta", platform: 0 },
  log,
  warn: log,
  error: log,
  Enum: makeEnum,
  js: {
    // occasional utility surface; expand on demand
    isNumber: (v) => typeof v === "number",
  },
};

// Unknown `cc.*` members (mostly UI/engine classes pulled in incidentally by the
// battle graph) resolve to a universal dummy: callable, constructable, and a
// usable base class. These modules only need to *define*, never run, in forecast
// mode. Explicit members above stay authoritative.
function universal() {
  class Dummy {}
  return new Proxy(Dummy, {
    get(t, p) {
      if (p in t) return t[p];
      if (p === Symbol.hasInstance) return () => false;
      if (typeof p === "symbol") return undefined;
      return universal();
    },
    apply() { return universal(); },
    construct() { return {}; },
  });
}

const ccProxy = new Proxy(cc, {
  get(t, p) {
    if (p in t) return t[p];
    if (typeof p === "symbol") return undefined;
    return universal();
  },
});

function install(g = globalThis) {
  g.cc = ccProxy;
  if (!g.window) g.window = g;
  return ccProxy;
}

module.exports = { cc: ccProxy, Vec2, Vec3, install };
