"use strict";
// Load the decrypted game bundle's module registry WITHOUT booting the game.
//
// The bundle is `window.__require = (function e(t,n,i){ ...; for(entrypoints) r(i[a]); return r; })(MODULES,{},ENTRY)`.
// Evaluating it as-is runs the game entrypoints (needs the full Cocos engine).
// We neutralize just the entrypoint loop, keeping the lazy `require` (`r`) that
// closes over the module table — so we can pull individual battle modules.

const fs = require("fs");
const path = require("path");
const { install } = require("./cc-shim");

// The distinctive one-shot line that executes entrypoints at load time.
const ENTRY_LOOP =
  'for (var o = "function" == typeof __require && __require, a = 0; a < i.length; a++) r(i[a]);';

const DEFAULT_ENGINE_JS =
  process.env.NTA_ENGINE_JS ||
  path.resolve(__dirname, "..", "re", "decrypted", "index.js");

// Leaf modules that live outside the code registry (scene assets, config-gen).
// The battle path pulls them transitively but does not need their real content;
// a permissive stub keeps the graph loadable. Names are matched by last segment.
const STUBBABLE = new Set(["version"]);

function permissiveStub() {
  // Any property read returns another permissive stub; callable; sane primitives.
  const target = function () { return permissiveStub(); };
  return new Proxy(target, {
    get(_t, prop) {
      if (prop === "default") return permissiveStub();
      if (prop === Symbol.toPrimitive || prop === "toString" || prop === "valueOf")
        return () => "";
      if (prop === "version") return "0.0.0";
      return permissiveStub();
    },
    apply() { return permissiveStub(); },
  });
}

function loadEngine(engineJsPath = DEFAULT_ENGINE_JS) {
  install(globalThis); // cc + window before any module factory runs

  // Fallback resolver the loader uses for modules missing from the registry
  // (loader: `if (o) return o(lastSegment, true)`). Allowlisted → stub; else throw.
  globalThis.__require = function (name) {
    if (STUBBABLE.has(name)) return permissiveStub();
    throw new Error("bundle.js: unresolved leaf module '" + name + "'");
  };

  let src = fs.readFileSync(engineJsPath, "utf8");
  if (!src.includes(ENTRY_LOOP)) {
    throw new Error(
      "bundle.js: entrypoint loop marker not found — the bundle format changed; " +
        "re-inspect index.js head and update ENTRY_LOOP."
    );
  }
  // Drop entrypoint execution but KEEP `var o` — the require fallback closes over it.
  src = src.replace(ENTRY_LOOP, 'var o = "function" == typeof __require && __require;');

  // Evaluate in global scope so `window.__require = ...` lands on our window.
  (0, eval)(src);

  const req = globalThis.window.__require;
  if (typeof req !== "function") {
    throw new Error("bundle.js: window.__require was not assigned after eval");
  }
  // The loader resolves an unknown full path by its last segment, so a bare
  // module name (e.g. "RandomObj") works directly.
  const requireByName = (name) => req(name);

  // Bootstrap: install prototype extensions (Array/Vec/…) and the `ut` global
  // that the game normally sets up at boot (we skipped the entrypoints).
  for (const m of ["ExtendArray", "ExtendVec", "ExtendCC", "ExtendComponent", "Utils"]) {
    requireByName(m);
  }
  return requireByName;
}

module.exports = { loadEngine, DEFAULT_ENGINE_JS };
