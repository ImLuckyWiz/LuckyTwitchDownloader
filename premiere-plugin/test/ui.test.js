"use strict";
// Smoke test of the panel wiring (main.js) with a fake DOM and a stub adapter: labels, counts, and what the buttons send to the adapter.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const core = require("../src/markers-core.js");
const SAMPLE = fs.readFileSync(path.join(__dirname, "fixtures", "markers_sample.json"), "utf8");

function makePanel({ timeline } = {}) {
  const els = new Map();
  const el = (id) => {
    if (!els.has(id)) {
      const handlers = {};
      els.set(id, {
        id, style: {}, className: "", textContent: "", value: "", checked: false, disabled: false, innerHTML: "",
        addEventListener: (ev, fn) => { (handlers[ev] = handlers[ev] || []).push(fn); },
        click: async () => { for (const fn of handlers.click || []) await fn(); },
        handlers,
      });
    }
    return els.get(id);
  };
  const calls = { cut: [], inspect: 0 };
  const stub = {
    inspectTimeline: async () => { calls.inspect++; if (!timeline) throw new Error("no clip"); return timeline; },
    cutAtClipEdges: async (items, opts) => { calls.cut.push({ items, opts }); return { cuts: 2, skipped: 0, points: 2, rounds: 1, clips: 1 }; },
    findMarkersFile: async () => null,
  };
  const storage = new Map();
  const win = {
    LTCore: core, LTAdapter: stub, __ltLog: () => {},
    addEventListener: () => {},
  };
  const sandbox = {
    window: win, document: { getElementById: el, readyState: "complete", addEventListener: () => {} },
    localStorage: { getItem: (k) => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, v) },
    require: (m) => { if (m === "uxp") throw new Error("no uxp"); return require(path.join(__dirname, "..", "src", m)); },
    setTimeout: () => 0, setInterval: () => 0, console, Date, Math, JSON, Number, String, Array, Set, Promise,
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "src", "main.js"), "utf8"), sandbox);
  return { el, calls };
}

const load = async (p) => {
  p.el("pasted").value = SAMPLE;
  await p.el("usePasted").click();
};
const tick = () => new Promise((r) => setImmediate(r));

test("panel: a loaded file shows a one-line summary and live counts on the buttons", async () => {
  const p = makePanel();
  await load(p);
  assert.match(p.el("fileSummary").textContent, /2 games · 1 clip/);
  assert.strictEqual(p.el("add").textContent, "Add 3 markers");
  assert.strictEqual(p.el("cutClips").textContent, "Cut at 1 clip");
  assert.strictEqual(p.el("cutChapters").textContent, "Cut at 2 chapters");
  assert.strictEqual(p.el("cutClips").disabled, false);
  assert.strictEqual(p.el("pickRow").style.display, "none");
  assert.strictEqual(p.el("pick2").style.display, "inline-block");
});

test("panel: counts follow what the timeline plays", async () => {
  // the sample has chapters 0-50 and 50-70 and a clip 7-30; the timeline plays source 40-100: the clip is outside
  const p = makePanel({ timeline: { descs: [{ start: 0, end: 60, inPoint: 40, outPoint: 100, speed: 1 }], mediaName: "v.mp4", trackIndex: 0, elsewhere: 0, reversed: 0 } });
  await load(p);
  await tick(); await tick();
  assert.strictEqual(p.el("cutClips").disabled, true, "the only clip is outside the timeline");
  assert.strictEqual(p.el("cutClips").textContent, "Cut at 0 of 1 clips");
  assert.strictEqual(p.el("cutChapters").textContent, "Cut at 2 chapters");
  assert.match(p.el("timelineInfo").textContent, /playing 0:00:40–0:01:40/);
});

test("panel: Cut at chapters sends the games even when games are not imported as markers", async () => {
  const p = makePanel();
  await load(p);
  p.el("importGames").checked = false;
  await p.el("importGames").handlers.change[0]();
  assert.strictEqual(p.el("cutChapters").textContent, "Cut at 2 chapters");
  await p.el("cutChapters").click();
  const call = p.calls.cut[0];
  assert.strictEqual(call.opts.chapters, true);
  assert.strictEqual(call.opts.clips, false);
  assert.strictEqual(call.opts.backup, true);
  assert.deepStrictEqual(call.items.filter((i) => i.kind === "game").map((i) => i.name), ["Just Chatting", "Resident Evil 2"]);
  assert.match(p.el("status").textContent, /Done: 2 cuts made/);
});

test("panel: Cut at clips sends padding, merge gap and the backup choice", async () => {
  const p = makePanel();
  await load(p);
  p.el("padBefore").value = "2";
  p.el("padAfter").value = "1.5";
  p.el("mergeGap").value = "4";
  p.el("backup").checked = false;
  await p.el("backup").handlers.change[0]();
  await p.el("cutClips").click();
  const o = p.calls.cut[0].opts;
  assert.deepStrictEqual([o.clips, o.chapters, o.backup], [true, false, false]);
  assert.deepStrictEqual(JSON.parse(JSON.stringify(o.plan)), { padBefore: 2, padAfter: 1.5, mergeGap: 4 });
  assert.strictEqual(o.hint.fileName, undefined, "pasted text has no file name to match a video by");
});
