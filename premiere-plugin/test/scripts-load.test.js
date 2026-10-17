"use strict";
// The panel loads boot.js, markers-core.js, premiere-adapter.js and main.js as CLASSIC <script> tags: they share one global scope, so a
// top-level const / let / function name declared in two of them is a SyntaxError that Node's require() never shows (every file is its own
// module there). This loads them the way the panel does.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

test("core and adapter load together in one global scope (no top-level name declared twice)", () => {
  const ctx = { console, require: (m) => { if (m === "premierepro" || m === "uxp") return {}; throw new Error("no " + m); } };
  ctx.window = ctx;
  vm.createContext(ctx);
  for (const f of ["markers-core.js", "premiere-adapter.js"]) {
    assert.doesNotThrow(() => vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "src", f), "utf8"), ctx, { filename: f }), f);
  }
  assert.ok(ctx.LTCore && ctx.LTAdapter && typeof ctx.LTAdapter.deleteGaps === "function");
});
