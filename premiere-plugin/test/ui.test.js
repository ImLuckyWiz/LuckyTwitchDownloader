"use strict";
// Smoke test of the panel wiring (main.js) with a fake DOM and a stub adapter: labels, counts, and what the buttons send to the adapter.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const core = require("../src/markers-core.js");
const SAMPLE = fs.readFileSync(path.join(__dirname, "fixtures", "markers_sample.json"), "utf8");

const okTimeline = () => ({
  descs: [{ start: 0, end: 100, inPoint: 0, outPoint: 100, speed: 1 }], mediaName: "v.mp4", trackIndex: 0, elsewhere: 0, reversed: 0, frame: 0,
  workspace: { videoTrack: 0, video: 1, audio: [{ track: 0, free: 1 }] },
});

function makePanel({ timeline, found, detectError, markersFact, hooks = {} } = {}) {
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
  const calls = { cut: [], add: [], del: [], gapProbe: [], ripple: 0, inspect: 0, backup: 0, order: [], detect: 0 };
  const logs = [];
  const stub = {
    inspectTimeline: async () => { calls.inspect++; if (!timeline) throw new Error("no clip"); return timeline; },
    checkMarkers: async () => markersFact || { what: 'the clip "v.mp4"', total: 3, present: 0 },
    backupSequence: async () => { calls.backup++; calls.order.push("backup"); return true; },
    addMarkers: async (items, opts) => { calls.add.push({ items, opts }); calls.order.push("markers"); return { added: items.length, skipped: 0, what: 'the clip "v.mp4"' }; },
    cutAtClipEdges: async (items, opts) => {
      calls.cut.push({ items, opts });
      calls.order.push("cut");
      if (hooks.cut) return hooks.cut(opts);
      return { cuts: 2, skipped: 0, points: 2, rounds: 1, clips: 1, stopped: false };
    },
    deleteGaps: async (items, opts) => {
      calls.del.push({ items, opts });
      calls.order.push("delete");
      if (hooks.del) return hooks.del(opts);
      return { deleted: 2, total: 2, rounds: 1, chunks: 1, stopped: false, deletedSeconds: 77, keepPieces: 1, keepSeconds: 23 };
    },
    probeGapPlan: async (...a) => { calls.gapProbe.push(a); },
    testRippleDelete: async () => { calls.ripple++; },
    findMarkersFile: async () => { calls.detect++; if (detectError) throw new Error(detectError); return found || null; },
  };
  const storage = new Map();
  const winHandlers = {};
  const intervals = [];
  const win = {
    LTCore: core, LTAdapter: stub, __ltLog: (t) => logs.push(t),
    addEventListener: (ev, fn) => { (winHandlers[ev] = winHandlers[ev] || []).push(fn); },
  };
  const sandbox = {
    window: win, document: { getElementById: el, readyState: "complete", addEventListener: () => {} },
    localStorage: { getItem: (k) => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, v) },
    require: (m) => { if (m === "uxp") throw new Error("no uxp"); return require(path.join(__dirname, "..", "src", m)); },
    setTimeout: () => 0, setInterval: (fn) => { intervals.push(fn); return 0; }, console, Date, Math, JSON, Number, String, Array, Set, Promise,
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "src", "main.js"), "utf8"), sandbox);
  const change = async (id, patch) => { Object.assign(el(id), patch); for (const fn of el(id).handlers.change || []) await fn(); };
  return { el, calls, logs, stub, change, focus: async () => { for (const fn of winHandlers.focus || []) await fn(); }, poll: async () => { for (const fn of intervals) await fn(); } };
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

const settle = async () => { for (let i = 0; i < 8; i++) await tick(); };

test("panel: the Do it all label is a live summary of the saved recipe", async () => {
  const p = makePanel({ timeline: okTimeline() });
  await load(p);
  await settle();
  assert.strictEqual(p.el("doAll").textContent, "Do it all: 3 markers + cut 1 clip");
  assert.strictEqual(p.el("doAll").disabled, false);
  await p.change("recipeCutChapters", { checked: true });
  assert.strictEqual(p.el("doAll").textContent, "Do it all: 3 markers + cut 1 clip + cut 2 chapters");
  await p.change("recipeMarkers", { checked: false });
  assert.strictEqual(p.el("doAll").textContent, "Do it all: cut 1 clip + cut 2 chapters");
  await p.change("recipeCutClips", { checked: false });
  await p.change("recipeCutChapters", { checked: false });
  assert.match(p.el("doAll").textContent, /nothing ticked/);
  assert.strictEqual(p.el("doAll").disabled, true);
});

test("panel: Do it all runs pre-flight, ONE backup, markers, then the cut without its own backup", async () => {
  const p = makePanel({ timeline: okTimeline() });
  await load(p);
  await p.el("doAll").click();
  assert.deepStrictEqual(p.calls.order, ["backup", "markers", "cut"]);
  assert.strictEqual(p.calls.backup, 1);
  const c = p.calls.cut[0].opts;
  assert.deepStrictEqual([c.backup, c.clips, c.chapters], [false, true, false], "the cut leaves the backup to Do it all");
  assert.strictEqual(p.calls.add[0].items.length, 3);
  assert.strictEqual(p.calls.add[0].opts.placement, "clip");
  assert.match(p.el("status").textContent, /^Done: 3 markers added to the clip "v.mp4"; 2 cuts made\. Look at the timeline\./);
  assert.strictEqual(p.el("status").className, "ok");
  assert.strictEqual(p.el("runBox").style.display, "none", "the progress box is gone again");
  assert.strictEqual(p.el("doAll").disabled, false);
});

test("panel: with the backup box off, Do it all makes none; chapters + clips go in the same single cut", async () => {
  const p = makePanel({ timeline: okTimeline() });
  await load(p);
  await p.change("backup", { checked: false });
  await p.change("recipeCutChapters", { checked: true });
  await p.el("doAll").click();
  assert.strictEqual(p.calls.backup, 0);
  assert.strictEqual(p.calls.cut.length, 1);
  assert.deepStrictEqual([p.calls.cut[0].opts.clips, p.calls.cut[0].opts.chapters], [true, true]);
});

test("panel: a failed pre-flight touches nothing and says why (no empty V2)", async () => {
  const tl = okTimeline();
  tl.workspace.video = -1;
  const p = makePanel({ timeline: tl });
  await load(p);
  await p.el("doAll").click();
  assert.deepStrictEqual(p.calls.order, [], "no backup, no markers, no cut");
  assert.match(p.el("status").textContent, /Nothing was changed\. No empty video track above V1/);
  assert.strictEqual(p.el("status").className, "err");
  assert.match(p.el("preSummary").textContent, /^Not ready: No empty video track above V1/);
  assert.match(p.el("preChecks").textContent, /✗ No empty video track above V1/);
  assert.match(p.el("preChecks").textContent, /✓ A markers file is loaded/);
});

test("panel: the pre-flight line is shown before anything is pressed, with the matching summary", async () => {
  const p = makePanel({ timeline: okTimeline() });
  await load(p);
  await settle();
  assert.match(p.el("preSummary").textContent, /^Will add 3 markers, then cut at clips: 2 cuts in 2 rounds, after one backup of the sequence\./);
  assert.strictEqual(p.el("preLinks").style.display, "flex");
});

test("panel: a failure in the cut says what is done and what is left on the timeline", async () => {
  const p = makePanel({
    timeline: okTimeline(),
    hooks: { cut: async () => { throw Object.assign(new Error("Stopped after 1 of 2 cuts (round 2): check failed"), { state: { done: 1, total: 2, round: 2, leftover: 1 } }); } },
  });
  await load(p);
  await p.el("doAll").click();
  const t = p.el("status").textContent;
  assert.match(t, /Stopped at step 2\/2 \(cut\)/);
  assert.match(t, /Done before that: 3 markers added/);
  assert.match(t, /1 of 2 cuts are made, and 1 temporary copy is still on the workspace tracks/);
  assert.match(t, /backup copy/);
  assert.strictEqual(p.el("status").className, "err");
});

test("panel: progress shows step and round, Stop is passed to the engine and ends the run after the round", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const p = makePanel({
    timeline: okTimeline(),
    hooks: {
      cut: async (opts) => {
        opts.onProgress({ phase: "round-start", round: 4, rounds: 6, done: 14, total: 38 });
        await gate;
        return { cuts: 14, skipped: 0, points: 38, rounds: 4, clips: 1, stopped: opts.shouldStop() };
      },
    },
  });
  await load(p);
  const run = p.el("doAll").click();
  await settle();
  assert.strictEqual(p.el("runBox").style.display, "block");
  assert.strictEqual(p.el("progressText").textContent, "Step 2/2 · cutting · round 4/6 · 14 of 38 cuts");
  assert.strictEqual(p.el("progressFill").style.width, "37%");
  assert.strictEqual(p.el("doAll").disabled, true, "the other buttons are locked while it runs");
  assert.strictEqual(p.el("add").disabled, true);
  await p.el("stop").click();
  assert.strictEqual(p.el("stop").disabled, true);
  assert.match(p.el("stop").textContent, /Stopping after this round/);
  release();
  await run;
  assert.match(p.el("status").textContent, /^Stopped by you\. Done: 3 markers added.*The cut stopped after round 4: 14 of 38 cuts are made, 24 not yet/);
  assert.strictEqual(p.el("runBox").style.display, "none");
});

test("panel: the single Cut buttons also show progress and obey Stop", async () => {
  let seen;
  const p = makePanel({
    timeline: okTimeline(),
    hooks: { cut: async (opts) => { opts.onProgress({ round: 1, rounds: 3, done: 1, total: 5 }); seen = p.el("progressText").textContent; return { cuts: 1, skipped: 0, points: 5, rounds: 1, clips: 1, stopped: true }; } },
  });
  await load(p);
  await p.el("cutClips").click();
  assert.strictEqual(seen, "cutting · round 1/3 · 1 of 5 cuts", "no 'Step n/m' for a single button");
  assert.match(p.el("status").textContent, /Stopped on request after round 1: 1 of 5 cuts are made/);
  assert.strictEqual(p.calls.cut[0].opts.backup, true, "individual buttons ask for a backup; the adapter skips it when a recent one exists");
});

test("panel: Only in chapter limits the markers, the counts and the cut range", async () => {
  const p = makePanel({ timeline: okTimeline() });
  await load(p);
  await settle();
  assert.strictEqual(p.el("limitRow").style.display, "block");
  assert.match(p.el("limitChapter").innerHTML, /1\. Just Chatting \(0:00:00–0:00:50\)/);
  assert.match(p.el("limitChapter").innerHTML, /2\. Resident Evil 2 \(0:00:50–0:01:10\)/);
  await p.change("limitChapter", { value: "1" }); // Resident Evil 2: 50-70, the only clip (7-30) is not in it
  await settle();
  assert.strictEqual(p.el("add").textContent, "Add 1 markers");
  assert.strictEqual(p.el("cutClips").disabled, true);
  assert.strictEqual(p.el("cutChapters").textContent, "Cut at 1 chapter");
  await p.el("cutChapters").click();
  assert.deepStrictEqual([p.calls.cut[0].opts.plan.min, p.calls.cut[0].opts.plan.max], [50, 70]);
  await p.el("add").click();
  assert.deepStrictEqual(p.calls.add[0].items.map((i) => i.name), ["Resident Evil 2"]);
  await p.change("limitChapter", { value: "" });
  assert.strictEqual(p.el("add").textContent, "Add 3 markers");
});

const FOUND = () => ({ text: SAMPLE, name: "v.markers.json", path: "E:/v.markers.json", where: "next to the video", how: "same name as the video", mediaPath: "C:/v.mp4" });

test("auto-run: off by default, nothing runs when a file is found", async () => {
  const p = makePanel({ timeline: okTimeline(), found: FOUND() });
  await p.focus();
  await settle();
  assert.match(p.el("fileSummary").textContent, /v\.markers\.json/);
  assert.deepStrictEqual(p.calls.order, []);
});

test("auto-run: when ticked it runs the recipe once per detected file, not again on the next look", async () => {
  const p = makePanel({ timeline: okTimeline(), found: FOUND() });
  await p.change("autoRun", { checked: true });
  await p.focus();
  await settle();
  assert.deepStrictEqual(p.calls.order, ["backup", "markers", "cut"]);
  await p.poll();
  await p.focus();
  await settle();
  assert.strictEqual(p.calls.cut.length, 1, "once per file");
});

test("auto-run: skipped (with the reason) when the pre-flight fails, and it runs later when the timeline is ready", async () => {
  const bad = okTimeline();
  bad.workspace.video = -1;
  let current = bad;
  const p = makePanel({ found: FOUND() });
  // the stub reads `timeline` once at creation: swap what inspect returns through the closure-free route below
  p.el("autoRun").checked = true;
  const stubTimeline = () => current;
  const adapter = p.stub;
  adapter.inspectTimeline = async () => stubTimeline();
  await p.change("autoRun", { checked: true });
  await p.focus();
  await settle();
  assert.deepStrictEqual(p.calls.order, []);
  assert.ok(p.logs.some((l) => /Auto-run skipped: No empty video track above V1/.test(l)));
  current = okTimeline();
  await p.change("placement", { value: "clip" }); // any change re-reads the timeline
  await settle();
  assert.deepStrictEqual(p.calls.order, ["backup", "markers", "cut"]);
});

test("auto-run: skipped when everything in the recipe is already done", async () => {
  const done = okTimeline();
  done.descs = [{ start: 0, end: 7, inPoint: 0, outPoint: 7, speed: 1 }, { start: 7, end: 30, inPoint: 7, outPoint: 30, speed: 1 }, { start: 30, end: 100, inPoint: 30, outPoint: 100, speed: 1 }];
  const p = makePanel({ timeline: done, found: FOUND(), markersFact: { what: "the clip", total: 3, present: 3 } });
  await p.change("autoRun", { checked: true });
  await p.focus();
  await settle();
  assert.deepStrictEqual(p.calls.order, []);
  assert.ok(p.logs.some((l) => /Auto-run skipped: everything in the recipe is already done/.test(l)));
  assert.match(p.el("preSummary").textContent, /already done/);
});

test("auto-run: a file chosen by hand is never run for you", async () => {
  const p = makePanel({ timeline: okTimeline() });
  await p.change("autoRun", { checked: true });
  await load(p);
  await settle();
  assert.deepStrictEqual(p.calls.order, []);
});

test("detect: 'No project is open' is not logged every 4 seconds, other errors are logged once", async () => {
  const p = makePanel({ detectError: "No project is open." });
  for (let i = 0; i < 4; i++) { await p.poll(); await settle(); }
  assert.strictEqual(p.calls.detect, 4, "it keeps looking");
  assert.ok(!p.logs.some((l) => /No project is open/.test(l)), "but says nothing in the log");
  assert.match(p.el("fileEmpty").textContent, /Open or create a project/);
  const q = makePanel({ detectError: "disk on fire" });
  for (let i = 0; i < 4; i++) { await q.poll(); await settle(); }
  assert.strictEqual(q.logs.filter((l) => /\(detect\) stopped: disk on fire/.test(l)).length, 1);
});

// ---- 0.7.0: Delete the gaps ---------------------------------------------------------------------------------------
// The sample file has one clip at 7-30 s. A timeline already cut at its edges has three pieces: 0-7 (gap), 7-30 (keep), 30-100 (gap).
const cutTimeline = () => ({ ...okTimeline(), descs: [{ start: 0, end: 7, inPoint: 0, outPoint: 7, speed: 1 }, { start: 7, end: 30, inPoint: 7, outPoint: 30, speed: 1 }, { start: 30, end: 100, inPoint: 30, outPoint: 100, speed: 1 }] });

test("delete: the red button shows the preview of what it would delete; an uncut timeline says why it cannot", async () => {
  const p = makePanel({ timeline: cutTimeline() });
  await load(p);
  await settle();
  assert.strictEqual(p.el("deleteGaps").disabled, false);
  assert.strictEqual(p.el("deleteGaps").textContent, "Delete the gaps: 2 pieces");
  assert.strictEqual(p.el("gapPreview").textContent, "Will delete 2 pieces, 77 s, 77.0%; keep 1 piece, 23 s, after one backup.");
  const u = makePanel({ timeline: okTimeline() });
  await load(u);
  await settle();
  assert.strictEqual(u.el("deleteGaps").disabled, true);
  assert.match(u.el("gapPreview").textContent, /1 piece is only partly inside a clip .*Run the cut first/);
  const none = makePanel();
  await load(none);
  assert.strictEqual(none.el("deleteGaps").disabled, true, "no timeline looked at: nothing to delete");
});

test("delete: two clicks. The first only shows the preview, the second one runs it with what the preview showed", async () => {
  const p = makePanel({ timeline: cutTimeline() });
  await load(p);
  await settle();
  await p.el("deleteGaps").click();
  await settle();
  assert.deepStrictEqual(p.calls.order, [], "nothing runs on the first click");
  assert.strictEqual(p.el("deleteGaps").textContent, "Click again to delete 2 pieces");
  assert.match(p.el("status").textContent, /^Will delete 2 pieces, 77 s, 77\.0%; keep 1 piece, 23 s\. Click the red button again to confirm \(one backup of the sequence first\)\./);
  await p.el("deleteGaps").click();
  await settle();
  assert.deepStrictEqual(p.calls.order, ["delete"]);
  const o = p.calls.del[0].opts;
  assert.deepStrictEqual([o.backup, o.expect.deleteCount, o.expect.keepCount, o.maxDeletePct, o.minKeep], [true, 2, 1, 99, 1]);
  assert.strictEqual(o.hint.mediaPath, undefined);
  assert.ok(p.calls.del[0].items.some((i) => i.kind === "clip"), "it gets the same planned items as the cut");
  assert.match(p.el("status").textContent, /^Done: 2 gap pieces deleted \(77 s\)\. 1 clip left back to back \(23 s\)\./);
  assert.strictEqual(p.el("runBox").style.display, "none");
  assert.strictEqual(p.el("deleteGaps").textContent, "Delete the gaps: 2 pieces", "disarmed again");
});

test("delete: when Premiere left holes and they were closed, the Done line says so (0.7.3)", async () => {
  const p = makePanel({ timeline: cutTimeline(), hooks: { del: async () => ({ deleted: 2, total: 2, rounds: 1, chunks: 1, stopped: false, deletedSeconds: 77, keepPieces: 1, keepSeconds: 23, holes: 3, holeSeconds: 0.05 }) } });
  await load(p);
  await settle();
  await p.el("deleteGaps").click();
  await settle();
  await p.el("deleteGaps").click();
  await settle();
  assert.match(p.el("status").textContent, /^Done: 2 gap pieces deleted \(77 s\)\. 1 clip left back to back \(23 s\)\. Premiere's ripple left 3 holes of up to one frame \(50 ms in all\); each was closed by lengthening the clip in front of it, so a clip can end up to one frame longer at its end\. Look at the timeline\./);
});

test("delete: changing a setting, or waiting too long, cancels the confirmation", async () => {
  const p = makePanel({ timeline: cutTimeline() });
  await load(p);
  await settle();
  await p.el("deleteGaps").click();
  await settle();
  assert.strictEqual(p.el("deleteGaps").textContent, "Click again to delete 2 pieces");
  await p.change("maxDeletePct", { value: "95" });
  assert.strictEqual(p.el("deleteGaps").textContent, "Delete the gaps: 2 pieces");
  await p.el("deleteGaps").click();
  await settle();
  assert.deepStrictEqual(p.calls.order, [], "the second click after a setting change is a first click again");
  const real = Date.now;
  Date.now = () => real() + 60000;
  try {
    await p.el("deleteGaps").click();
    await settle();
    assert.deepStrictEqual(p.calls.order, [], "a confirmation older than 30 s counts for nothing");
  } finally {
    Date.now = real;
  }
  await p.el("deleteGaps").click();
  await settle();
  await p.el("deleteGaps").click();
  await settle();
  assert.strictEqual(p.calls.del[0].opts.maxDeletePct, 95, "the limit from Settings goes to the adapter");
});

test("delete: the percentage limit and the pieces-to-keep setting disable the button and say why", async () => {
  const p = makePanel({ timeline: cutTimeline() });
  await load(p);
  await settle();
  await p.change("maxDeletePct", { value: "50" });
  assert.strictEqual(p.el("deleteGaps").disabled, true);
  assert.match(p.el("gapPreview").textContent, /It would delete 77\.0% of the timeline; the limit in Settings is 50%/);
  await p.change("maxDeletePct", { value: "99" });
  await p.change("minKeepPieces", { value: "2" });
  assert.match(p.el("gapPreview").textContent, /Only 1 piece would be kept \(need at least 2\)/);
  await p.change("minKeepPieces", { value: "1" });
  assert.strictEqual(p.el("deleteGaps").disabled, false);
});

test("delete: no backup box means the preview says so; progress shows batches of gap pieces and Stop says batch", async () => {
  let seen = "", stopLabel = "";
  const p = makePanel({
    timeline: cutTimeline(),
    hooks: { del: async (opts) => { opts.onProgress({ phase: "round-start", round: 1, rounds: 3, done: 60, total: 109 }); seen = p.el("progressText").textContent; stopLabel = p.el("stop").textContent; return { deleted: 60, total: 109, rounds: 1, chunks: 3, stopped: true, deletedSeconds: 1, keepPieces: 1, keepSeconds: 1 }; } },
  });
  await load(p);
  await p.change("backup", { checked: false });
  await settle();
  assert.match(p.el("gapPreview").textContent, /NO backup: the box is off in Settings\.$/);
  await p.el("deleteGaps").click();
  await settle();
  assert.match(p.el("status").textContent, /\(NO backup: the box is off in Settings\)/);
  await p.el("deleteGaps").click();
  await settle();
  assert.strictEqual(seen, "deleting gaps · batch 1/3 · 60 of 109 gap pieces");
  assert.strictEqual(stopLabel, "Stop after this batch");
  assert.strictEqual(p.calls.del[0].opts.backup, false);
  assert.match(p.el("status").textContent, /^Stopped on request after batch 1: 60 of 109 gap pieces are deleted\. Press the red button again to finish/);
});

test("delete: a failure inside the run is shown as an error with what is left", async () => {
  const p = makePanel({
    timeline: cutTimeline(),
    hooks: { del: async () => { throw Object.assign(new Error("Stopped in batch 1 of 1 after 0 of 2 gap pieces were deleted: V1: piece 1 is off"), { state: { kind: "delete", deleted: 0, total: 2 } }); } },
  });
  await load(p);
  await settle();
  await p.el("deleteGaps").click();
  await settle();
  await p.el("deleteGaps").click();
  await settle();
  assert.match(p.el("status").textContent, /Stopped in batch 1 of 1 after 0 of 2 gap pieces were deleted/);
  assert.strictEqual(p.el("status").className, "err");
  assert.strictEqual(p.el("runBox").style.display, "none");
});

test("Do it all with the delete step: the first press shows the preview from the pieces the cut WILL make, the second one runs everything", async () => {
  const p = makePanel({ timeline: okTimeline() }); // not cut yet: one piece 0-100
  await load(p);
  await p.change("recipeDeleteGaps", { checked: true });
  await settle();
  assert.strictEqual(p.el("doAll").textContent, "Do it all: 3 markers + cut 1 clip + delete 2 gaps");
  assert.match(p.el("preSummary").textContent, /^Will add 3 markers, then cut at clips: 2 cuts in 2 rounds, then delete the gaps: 2 pieces, 77 s, 77\.0%; keep 1 piece, 23 s, after one backup of the sequence\./);
  await p.el("doAll").click();
  await settle();
  assert.deepStrictEqual(p.calls.order, [], "the confirmation happens BEFORE anything is touched");
  assert.match(p.el("status").textContent, /^This run will delete the gaps at the end: 2 pieces, 77 s, 77\.0%; keep 1 piece, 23 s\. Press Do it all again to confirm \(one backup of the sequence first\)\./);
  assert.strictEqual(p.el("doAll").textContent, "Click again to confirm: Do it all: 3 markers + cut 1 clip + delete 2 gaps");
  await p.el("doAll").click();
  await settle();
  assert.deepStrictEqual(p.calls.order, ["backup", "markers", "cut", "delete"], "one backup, delete last");
  assert.strictEqual(p.calls.backup, 1);
  const d = p.calls.del[0].opts;
  assert.deepStrictEqual([d.backup, d.expect.deleteCount, d.expect.keepCount], [false, 2, 1], "the run checks the timeline against the preview it showed");
  assert.match(p.el("status").textContent, /^Done: 3 markers added to the clip "v\.mp4"; 2 cuts made; 2 gap pieces deleted \(77 s\)\. Look at the timeline\. The clips are back to back/);
  assert.strictEqual(p.el("doAll").textContent, "Do it all: 3 markers + cut 1 clip + delete 2 gaps");
});

test("Do it all with the delete step: a failing delete says what is done and what is left; a changed setting asks for the confirmation again", async () => {
  const p = makePanel({
    timeline: okTimeline(),
    hooks: { del: async () => { throw Object.assign(new Error("ripple did not move A1"), { state: { kind: "delete", deleted: 1, total: 2, note: "The failed batch may be partly applied." } }); } },
  });
  await load(p);
  await p.change("recipeDeleteGaps", { checked: true });
  await settle();
  await p.el("doAll").click();
  await settle();
  await p.change("padAfter", { value: "1" });
  await settle();
  await p.el("doAll").click();
  await settle();
  assert.deepStrictEqual(p.calls.order, [], "after a setting changed the next press is a first press again");
  await p.el("doAll").click();
  await settle();
  const t = p.el("status").textContent;
  assert.match(t, /Stopped at step 3\/3 \(delete the gaps\): ripple did not move A1\. Done before that: 3 markers added.*2 cuts made\./);
  assert.match(t, /On the timeline: 1 of 2 gap pieces are deleted, 1 are still there\. The failed batch may be partly applied\./);
  assert.strictEqual(p.el("status").className, "err");
});

test("Do it all that only deletes on an already cut timeline: backup, then delete, after one confirmation", async () => {
  const p = makePanel({ timeline: cutTimeline() });
  await load(p);
  await p.change("recipeMarkers", { checked: false });
  await p.change("recipeCutClips", { checked: false });
  await p.change("recipeDeleteGaps", { checked: true });
  await settle();
  assert.strictEqual(p.el("doAll").textContent, "Do it all: delete 2 gaps");
  await p.el("doAll").click();
  await settle();
  await p.el("doAll").click();
  await settle();
  assert.deepStrictEqual(p.calls.order, ["backup", "delete"]);
});

test("auto-run never runs a recipe that deletes", async () => {
  const p = makePanel({ timeline: okTimeline(), found: FOUND() });
  await p.change("recipeDeleteGaps", { checked: true });
  await p.change("autoRun", { checked: true });
  await p.focus();
  await settle();
  assert.deepStrictEqual(p.calls.order, []);
  assert.ok(p.logs.some((l) => /Auto-run skipped: the recipe deletes the gaps, which always needs your confirmation/.test(l)), p.logs.join("\n"));
});

test("Troubleshooting: the Gap plan probe gets the same settings, and Test ripple delete needs two presses", async () => {
  const p = makePanel({ timeline: cutTimeline() });
  await load(p);
  await p.el("probeGapPlan").click();
  assert.strictEqual(p.calls.gapProbe.length, 1);
  assert.deepStrictEqual([p.calls.gapProbe[0][2].maxDeletePct, p.calls.gapProbe[0][2].minKeep], [99, 1]);
  await p.el("testRipple").click();
  assert.strictEqual(p.calls.ripple, 0, "the first press only arms it");
  assert.strictEqual(p.el("testRipple").textContent, "Click again: changes THIS project");
  assert.ok(p.logs.some((l) => /run it on a COPY of the project/.test(l)));
  await p.el("testRipple").click();
  assert.strictEqual(p.calls.ripple, 1);
  assert.strictEqual(p.el("testRipple").textContent, "Test ripple delete");
});
