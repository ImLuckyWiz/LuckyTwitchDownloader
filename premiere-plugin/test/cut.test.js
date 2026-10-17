"use strict";
// A fake timeline (tracks, track items, clone / trim / remove actions) to check the cut logic of cutAtClipEdges
// without Premiere. `mode` says how the fake Premiere treats setStart / setInPoint, because that is not documented:
//   A: setStart trims the head and moves the in point along      B: setStart only moves the edge, setInPoint only sets the in point
//   C: like B, but setInPoint also shifts the start (the bug another developer reported) -> the plugin must refuse and stop
const test = require("node:test");
const assert = require("node:assert");
const adapter = require("../src/premiere-adapter.js");

const TPS = 254016000000;
const tt = (s) => ({ seconds: s, ticks: String(Math.round(s * TPS)) });

// 0.7.0: createRemoveItemsAction(selection, ripple, mediaType, shiftOverLapping) has ripple semantics. `ripple` says how the fake
// Premiere treats ripple = true:
//   selected   the tracks that lost a piece close the gap (V1 and A1 when both were selected), other tracks stay where they are
//   all        every track closes the gap (sync lock on everywhere)
//   ignore     the second argument does nothing: the piece goes and the gap stays (what "my guess about the argument" being wrong looks like)
//   short      every removed piece is closed one frame short (the log of the first real run: a 1-frame hole before every kept piece)
//   audio-stays  video closes the gap, audio does not (video and audio drift apart)
//   mixed      0.7.3: the real log: each removed piece is closed 0 or 1 frame short (about 72% of them 1 frame, a fixed pattern)
//   frac       each removed piece is closed a pseudo-random part of a frame short (never more than one frame)
//   far        each removed piece is closed 3 frames short (more than Premiere was seen to do: the engine must refuse)
//   over       each removed piece is closed one frame too far (pieces would overlap: the engine must refuse)
// mediaType: a selection of video and audio items with MediaType.VIDEO removes only the video items (and AUDIO the audio ones).
function makeTimeline(mode, { videoTracks = 2, audioTracks = 3, len = 1000, fps = 30, initial, other = [], selected, guid, ripple: rippleBehavior = "selected" } = {}) {
  const tracks = { video: Array.from({ length: videoTracks }, () => []), audio: Array.from({ length: audioTracks }, () => []) };
  const mk = (kind, track, S, E, I, media = "vod.mp4") => {
    const it = { kind, track, S, E, I, O: I + (E - S), media };
    it.getStartTime = async () => tt(it.S);
    it.getEndTime = async () => tt(it.E);
    it.getInPoint = async () => tt(it.I);
    it.getOutPoint = async () => tt(it.O);
    it.getSpeed = async () => 1;
    it.getName = async () => media;
    it.getProjectItem = async () => ({ getName: async () => media, getMediaFilePath: async () => `C:/${media}` });
    it.createSetEndAction = (t) => () => { it.E = t.seconds; it.O = it.I + (it.E - it.S); };
    it.createSetStartAction = (t) => () => {
      if (mode === "A") { const d = t.seconds - it.S; it.S = t.seconds; it.I += d; } else it.S = t.seconds;
      it.O = it.I + (it.E - it.S);
    };
    it.createSetInPointAction = (t) => () => {
      if (mode === "C") { const d = t.seconds - it.I; it.I = t.seconds; it.S += d; } else it.I = t.seconds;
      it.O = it.I + (it.E - it.S);
    };
    tracks[kind][track].push(it);
    return it;
  };
  for (const [S, E, I] of initial || [[0, len, 0]]) {
    mk("video", 0, S, E, I);
    mk("audio", 0, S, E, I);
  }
  for (const [S, E, I, media] of other) {
    mk("video", 0, S, E, I, media);
    mk("audio", 0, S, E, I, media);
  }
  const trackObj = (kind, i) => ({ getTrackItems: async () => tracks[kind][i].slice() });
  const sequence = {
    getPlayerPosition: async () => tt(0),
    getVideoTrackCount: async () => tracks.video.length,
    getAudioTrackCount: async () => tracks.audio.length,
    getVideoTrack: async (i) => trackObj("video", i),
    getAudioTrack: async (i) => trackObj("audio", i),
    getTimebase: async () => String(Math.round(TPS / fps)),
    getSelection: async () => ({ getTrackItems: async () => (selected ? selected(tracks) : [tracks.video[0][0], tracks.audio[0][0]]) }),
    createCloneAction: () => () => { stats.backups++; },
  };
  if (guid) sequence.guid = guid;
  const editor = {
    createCloneTrackItemAction: (item, off, vOff, aOff) => () => {
      const dest = item.track + (item.kind === "video" ? vOff : aOff);
      const S = item.S + off.seconds, E = item.E + off.seconds;
      for (const o of tracks[item.kind][dest]) if (o.S < E - 1e-6 && o.E > S + 1e-6) throw new Error(`fake: clone would overwrite ${o.S}-${o.E} on track ${dest}`);
      mk(item.kind, dest, S, E, item.I, item.media);
    },
    createRemoveItemsAction: (sel, ripple, mediaType, shiftOverLapping) => () => {
      const id = mediaType && mediaType.id;
      const items = sel.items.filter((it) => !id || id === "any" || id === it.kind);
      stats.removes.push({ n: items.length, ripple, media: id, shiftOverLapping });
      const ranges = [];
      for (const it of items) if (!ranges.some((r) => Math.abs(r.S - it.S) < 1e-6 && Math.abs(r.E - it.E) < 1e-6)) ranges.push({ S: it.S, E: it.E });
      const touched = new Set(items.map((it) => `${it.kind}:${it.track}`));
      for (const it of items) tracks[it.kind][it.track] = tracks[it.kind][it.track].filter((x) => x !== it);
      if (ripple !== true || rippleBehavior === "ignore") return;
      for (const kind of ["video", "audio"]) {
        if (rippleBehavior === "audio-stays" && kind === "audio") continue;
        tracks[kind].forEach((list, i) => {
          if (rippleBehavior !== "all" && !touched.has(`${kind}:${i}`)) return;
          for (const x of list) {
            const lack = (r, n) => {
              if (rippleBehavior === "short") return 1 / fps;
              if (rippleBehavior === "far") return 3 / fps;
              if (rippleBehavior === "over") return -1 / fps;
              const h = Math.abs(Math.sin((r.S + 1) * 12.9898 + n)) * 43758.5453 % 1; // deterministic pseudo-random in [0, 1)
              if (rippleBehavior === "mixed") return h < 0.72 ? 1 / fps : 0;
              if (rippleBehavior === "frac") return (h * 0.95) / fps;
              return 0;
            };
            const shift = require("../src/markers-core.js").shiftAfter(x.S, ranges.map((r, n) => ({ S: r.S, E: r.E - lack(r, n) })));
            x.S -= shift;
            x.E -= shift;
          }
        });
      }
    },
  };
  const stats = { tx: 0, backups: 0, removes: [] };
  const P = {
    TickTime: { createWithSeconds: (s) => tt(s) },
    Constants: { TrackItemType: { CLIP: 1 }, MediaType: { ANY: { id: "any" }, VIDEO: { id: "video" }, AUDIO: { id: "audio" } } },
    SequenceEditor: { getEditor: async () => editor },
    TrackItemSelection: { createEmptySelection: (cb) => { const sel = { items: [], addItem: (i) => sel.items.push(i) }; cb(sel); return true; } },
    Project: {
      getActiveProject: async () => ({
        getActiveSequence: async () => sequence,
        executeTransaction: (fn) => { stats.tx++; const acts = []; fn({ addAction: (a) => acts.push(a) }); acts.forEach((a) => a()); return true; },
      }),
    },
  };
  return { P, tracks, stats };
}

const clipItems = (list) => list.map(([start, duration], i) => ({ kind: "clip", name: `c${i}`, start, duration }));
const pieces = (arr) => arr.slice().sort((a, b) => a.S - b.S).map((x) => [Math.round(x.S * 1000) / 1000, Math.round(x.E * 1000) / 1000, Math.round(x.I * 1000) / 1000]);

for (const mode of ["A", "B"]) {
  test(`cutAtClipEdges splits video and audio at every clip start and end (fake Premiere, mode ${mode})`, async () => {
    const { P, tracks, stats } = makeTimeline(mode);
    adapter._setPremiere(P);
    const r = await adapter.cutAtClipEdges(clipItems([[100.5, 29.5], [200.2, 49.8], [900, 50]]), { backup: true }, () => {});
    assert.strictEqual(r.points, 6);
    assert.strictEqual(r.cuts, 6);
    assert.strictEqual(r.rounds, 3, "6 cut points need 3 halving rounds");
    assert.ok(stats.tx <= 1 + 5 * 3, `few timeline edits, got ${stats.tx}`);
    const expected = [[0, 100.5, 0], [100.5, 130, 100.5], [130, 200.2, 130], [200.2, 250, 200.2], [250, 900, 250], [900, 950, 900], [950, 1000, 950]];
    assert.deepStrictEqual(pieces(tracks.video[0]), expected);
    assert.deepStrictEqual(pieces(tracks.audio[0]), expected);
    assert.strictEqual(tracks.video[1].length, 0, "no temp copy left on V2");
    assert.strictEqual(tracks.audio[1].length, 0, "no temp copy left on A2");
  });
}

test("cutAtClipEdges stops and says so when Premiere puts the second half in the wrong place (mode C)", async () => {
  const { P } = makeTimeline("C");
  adapter._setPremiere(P);
  await assert.rejects(() => adapter.cutAtClipEdges(clipItems([[100, 30]]), {}, () => {}), /check failed|Stopped after 0 of/);
});

test("cutAtClipEdges asks for an empty track when there is none above", async () => {
  const { P } = makeTimeline("A", { videoTracks: 1 });
  adapter._setPremiere(P);
  await assert.rejects(() => adapter.cutAtClipEdges(clipItems([[100, 30]]), {}, () => {}), /no empty video track/i);
});

test("cutAtClipEdges snaps to frames and ignores clips outside the target clip", async () => {
  const { P, tracks } = makeTimeline("A", { len: 500 });
  adapter._setPremiere(P);
  const r = await adapter.cutAtClipEdges(clipItems([[100.01, 20], [600, 30]]), {}, () => {});
  assert.strictEqual(r.cuts, 2);
  assert.strictEqual(tracks.video[0].length, 3);
});

test("38 cut points take 6 rounds and about 25 timeline edits instead of 300", async () => {
  const { P, tracks, stats } = makeTimeline("A", { len: 5000 });
  adapter._setPremiere(P);
  const list = [];
  for (let i = 0; i < 19; i++) list.push([100 + i * 200, 50 + (i % 5)]);
  const r = await adapter.cutAtClipEdges(clipItems(list), { backup: true }, () => {});
  assert.strictEqual(r.points, 38);
  assert.strictEqual(r.cuts, 38);
  assert.strictEqual(r.rounds, 6);
  assert.ok(stats.tx <= 1 + 4 * 6, `edits: ${stats.tx}`);
  assert.strictEqual(tracks.video[0].length, 39);
  assert.strictEqual(tracks.audio[0].length, 39);
  assert.strictEqual(tracks.video[1].length + tracks.audio[1].length, 0, "workspace tracks are empty again");
  // every piece plays the source that matches its place on the timeline (no slip anywhere)
  for (const x of [...tracks.video[0], ...tracks.audio[0]]) assert.ok(Math.abs(x.I - x.S) < 0.02, `piece ${x.S} plays source ${x.I}`);
  // and the pieces tile the clip with no gap or overlap
  const v = tracks.video[0].slice().sort((a, b) => a.S - b.S);
  for (let i = 1; i < v.length; i++) assert.ok(Math.abs(v[i].S - v[i - 1].E) < 0.001);
  assert.ok(Math.abs(v[0].S) < 0.001 && Math.abs(v[v.length - 1].E - 5000) < 0.001);
});

// ---- 0.5.0: every clip of the markers file's video, chapters, padding, already-cut timelines ----------------------
const chapterItems = (list) => list.map(([start, duration], i) => ({ kind: "game", name: `g${i}`, start, duration }));

test("a timeline whose first part was deleted: cuts land by source time, earlier markers are ignored", async () => {
  // the clip plays source 1800-2400 from timeline 0 (the first hour of the stream was deleted)
  const { P, tracks } = makeTimeline("A", { initial: [[0, 600, 1800]] });
  adapter._setPremiere(P);
  const r = await adapter.cutAtClipEdges(clipItems([[1700, 150], [2000, 100], [2500, 50]]), {}, () => {});
  assert.strictEqual(r.points, 3, "1850 (end of the clamped first clip), 2000 and 2100");
  const expected = [[0, 50, 1800], [50, 200, 1850], [200, 300, 2000], [300, 600, 2100]];
  assert.deepStrictEqual(pieces(tracks.video[0]), expected);
  assert.deepStrictEqual(pieces(tracks.audio[0]), expected);
});

test("running the cut twice is harmless: points that already have a cut are not cut again", async () => {
  const { P, tracks } = makeTimeline("A");
  adapter._setPremiere(P);
  const items = clipItems([[100, 30], [300, 40]]);
  const first = await adapter.cutAtClipEdges(items, {}, () => {});
  assert.strictEqual(first.cuts, 4);
  const second = await adapter.cutAtClipEdges(items, {}, () => {});
  assert.strictEqual(second.cuts, 0);
  assert.strictEqual(second.points, 0, "every point is now the edge of a piece");
  assert.strictEqual(tracks.video[0].length, 5);
  assert.strictEqual(tracks.audio[0].length, 5);
});

test("an already cut timeline (several pieces of the same video) is cut again only where a cut is missing", async () => {
  // pieces: 0-100 (src 0), 100-400 (src 100), 400-1000 (src 400): there are cuts at 100 and 400 already
  const { P, tracks } = makeTimeline("A", { initial: [[0, 100, 0], [100, 400, 100], [400, 1000, 400]] });
  adapter._setPremiere(P);
  const r = await adapter.cutAtClipEdges(clipItems([[100, 150], [600, 50]]), {}, () => {});
  assert.strictEqual(r.points, 3, "250, 600 and 650; 100 is already a cut");
  assert.strictEqual(r.cuts, 3);
  assert.deepStrictEqual(pieces(tracks.video[0]).map((x) => x[0]), [0, 100, 250, 400, 600, 650]);
  assert.strictEqual(tracks.video[1].length + tracks.audio[1].length, 0);
});

test("chapters only, and chapters + clips together in one run", async () => {
  const items = [...clipItems([[100, 30]]), ...chapterItems([[0, 400], [400, 600]])];
  const a = makeTimeline("A");
  adapter._setPremiere(a.P);
  const onlyChapters = await adapter.cutAtClipEdges(items, { clips: false, chapters: true }, () => {});
  assert.strictEqual(onlyChapters.points, 1, "0 and 1000 are the clip's own edges, 400 is the only boundary inside");
  assert.deepStrictEqual(pieces(a.tracks.video[0]).map((x) => x[0]), [0, 400]);
  const b = makeTimeline("A");
  adapter._setPremiere(b.P);
  const both = await adapter.cutAtClipEdges(items, { clips: true, chapters: true }, () => {});
  assert.strictEqual(both.points, 3);
  assert.deepStrictEqual(pieces(b.tracks.video[0]).map((x) => x[0]), [0, 100, 130, 400]);
  assert.deepStrictEqual(pieces(b.tracks.audio[0]).map((x) => x[0]), [0, 100, 130, 400]);
});

test("padding grows the clips and merges the ones that end up touching", async () => {
  const { P, tracks } = makeTimeline("A");
  adapter._setPremiere(P);
  const r = await adapter.cutAtClipEdges(clipItems([[100, 20], [124, 10], [500, 10]]), { plan: { padBefore: 3, padAfter: 3 } }, () => {});
  assert.strictEqual(r.points, 4, "97-137 (merged) and 497-513");
  assert.deepStrictEqual(pieces(tracks.video[0]).map((x) => x[0]), [0, 97, 137, 497, 513]);
});

test("only clips of the markers file's video are cut; another video on the timeline is left alone", async () => {
  const { P, tracks } = makeTimeline("A", { initial: [[0, 500, 0]], other: [[500, 900, 0, "other.mp4"]] });
  adapter._setPremiere(P);
  const r = await adapter.cutAtClipEdges(clipItems([[100, 30], [600, 30]]), { hint: { mediaPath: "C:/vod.mp4" } }, () => {});
  assert.strictEqual(r.points, 2, "the second clip is at source 600 but vod.mp4 only plays 0-500");
  assert.deepStrictEqual(pieces(tracks.video[0]).map((x) => x[0]), [0, 100, 130, 500]);
});

test("the markers file name picks the video, even when another clip is selected", async () => {
  const { P, tracks } = makeTimeline("A", {
    initial: [[0, 500, 0]],
    other: [[500, 900, 0, "other-video.mp4"]],
    selected: (t) => [t.video[0][1]], // the other video is the selected clip
  });
  adapter._setPremiere(P);
  const r = await adapter.cutAtClipEdges(clipItems([[100, 30]]), { hint: { fileName: "vod.markers.json" } }, () => {});
  assert.strictEqual(r.points, 2);
  assert.deepStrictEqual(pieces(tracks.video[0]).map((x) => x[0]), [0, 100, 130, 500], "vod.mp4 is cut; the other clip (starts at 500) is untouched");
});

test("inspectTimeline reports the source windows the timeline plays", async () => {
  const { P } = makeTimeline("A", { initial: [[0, 100, 1800], [100, 300, 1900]] });
  adapter._setPremiere(P);
  const t = await adapter.inspectTimeline({ mediaPath: "C:/vod.mp4" });
  assert.strictEqual(t.descs.length, 2);
  assert.deepStrictEqual(require("../src/markers-core.js").coverage([], t.descs).windows, [{ start: 1800, end: 2100 }]);
});

// ---- 0.6.0: progress, Stop, one backup per run, workspace facts, failure state ---------------------------------
const core = require("../src/markers-core.js");

test("progress: the plan, then every round, ending with all cuts done", async () => {
  const { P } = makeTimeline("A");
  adapter._setPremiere(P);
  const events = [];
  await adapter.cutAtClipEdges(clipItems([[100.5, 29.5], [200.2, 49.8], [900, 50]]), { onProgress: (e) => events.push(e) }, () => {});
  assert.deepStrictEqual([events[0].phase, events[0].total, events[0].rounds, events[0].done], ["plan", 6, 3, 0]);
  const starts = events.filter((e) => e.phase === "round-start").map((e) => e.round);
  assert.deepStrictEqual(starts, [1, 2, 3]);
  const last = events[events.length - 1];
  assert.deepStrictEqual([last.phase, last.round, last.done, last.total], ["round-done", 3, 6, 6]);
  assert.strictEqual(core.progressText({ step: 2, steps: 2, label: "cutting", ...last }), "Step 2/2 · cutting · round 3/3 · 6 of 6 cuts");
});

test("a broken progress callback never stops the cut", async () => {
  const { P, tracks } = makeTimeline("A");
  adapter._setPremiere(P);
  const r = await adapter.cutAtClipEdges(clipItems([[100, 30]]), { onProgress: () => { throw new Error("ui broke"); } }, () => {});
  assert.strictEqual(r.cuts, 2);
  assert.strictEqual(tracks.video[0].length, 3);
});

test("Stop finishes the current round, leaves a consistent timeline, and a second run finishes the job", async () => {
  const { P, tracks } = makeTimeline("A", { len: 5000 });
  adapter._setPremiere(P);
  const list = [];
  for (let i = 0; i < 19; i++) list.push([100 + i * 200, 50 + (i % 5)]);
  const items = clipItems(list);
  let stop = false;
  const first = await adapter.cutAtClipEdges(items, { shouldStop: () => stop, onProgress: (e) => { if (e.phase === "round-done" && e.round === 2) stop = true; } }, () => {});
  assert.strictEqual(first.stopped, true);
  assert.strictEqual(first.rounds, 2, "round 2 was finished, round 3 never started");
  assert.strictEqual(first.cuts, 3, "1 + 2 cuts in the first two rounds");
  assert.strictEqual(first.points, 38);
  assert.strictEqual(tracks.video[0].length, 4);
  assert.strictEqual(tracks.audio[0].length, 4);
  assert.strictEqual(tracks.video[1].length + tracks.audio[1].length, 0, "no temp copy left behind");
  const second = await adapter.cutAtClipEdges(items, {}, () => {});
  assert.strictEqual(second.stopped, false);
  assert.strictEqual(second.points, 35, "the 3 points already cut are not pending any more");
  assert.strictEqual(tracks.video[0].length, 39);
  for (const x of [...tracks.video[0], ...tracks.audio[0]]) assert.ok(Math.abs(x.I - x.S) < 0.02);
});

test("Stop asked before the first round touches nothing, not even the backup", async () => {
  const { P, tracks, stats } = makeTimeline("A", { guid: "seq-stop" });
  adapter._setPremiere(P);
  const r = await adapter.cutAtClipEdges(clipItems([[100, 30]]), { backup: true, shouldStop: () => true }, () => {});
  assert.deepStrictEqual([r.stopped, r.cuts, r.points], [true, 0, 2]);
  assert.strictEqual(stats.backups, 0);
  assert.strictEqual(tracks.video[0].length, 1);
});

test("one backup per run: Do it all makes one and its cut makes none", async () => {
  const { P, stats } = makeTimeline("A", { guid: "seq-doitall" });
  adapter._setPremiere(P);
  assert.strictEqual(await adapter.backupSequence(() => {}), true);
  await adapter.cutAtClipEdges(clipItems([[100, 30], [300, 30]]), { backup: false }, () => {});
  assert.strictEqual(stats.backups, 1);
});

test("the individual cut buttons skip their backup when one was made a moment ago in this session", async () => {
  const { P, stats } = makeTimeline("A", { guid: "seq-buttons" });
  adapter._setPremiere(P);
  const lines = [];
  await adapter.cutAtClipEdges(clipItems([[100, 30]]), { backup: true }, (t) => lines.push(t));
  await adapter.cutAtClipEdges(clipItems([[300, 30]]), { backup: true }, (t) => lines.push(t));
  assert.strictEqual(stats.backups, 1, "the second button press reused the first backup");
  assert.ok(lines.some((l) => /Skipped the backup: one was made \d+ min ago/.test(l)));
  // another sequence is not covered by that backup
  const other = makeTimeline("A", { guid: "seq-other" });
  adapter._setPremiere(other.P);
  await adapter.cutAtClipEdges(clipItems([[100, 30]]), { backup: true }, () => {});
  assert.strictEqual(other.stats.backups, 1);
});

test("when the sequence cannot be told apart, every backup box press still makes a backup (the 0.5.0 behavior)", async () => {
  const { P, stats } = makeTimeline("A");
  adapter._setPremiere(P);
  await adapter.cutAtClipEdges(clipItems([[100, 30]]), { backup: true }, () => {});
  await adapter.cutAtClipEdges(clipItems([[300, 30]]), { backup: true }, () => {});
  assert.strictEqual(stats.backups, 2);
});

test("inspectTimeline reports the workspace tracks and the frame length, and the pre-flight reads them", async () => {
  const ok = makeTimeline("A");
  adapter._setPremiere(ok.P);
  const t = await adapter.inspectTimeline({ mediaPath: "C:/vod.mp4" });
  assert.deepStrictEqual(JSON.parse(JSON.stringify(t.workspace)), { videoTrack: 0, video: 1, audio: [{ track: 0, free: 1 }] });
  assert.ok(Math.abs(t.frame - 1 / 30) < 1e-6);

  const noV2 = makeTimeline("A", { videoTracks: 1 });
  adapter._setPremiere(noV2.P);
  const t2 = await adapter.inspectTimeline({ mediaPath: "C:/vod.mp4" });
  assert.strictEqual(t2.workspace.video, -1);
  const pre = core.evaluatePreflight({
    loaded: true, recipe: { markers: false, clips: true, chapters: false }, minClips: 1, markerCount: 0, timeline: t2, workspace: t2.workspace,
    clipsInside: 3, clipsTotal: 3, chaptersInside: 0, chaptersTotal: 0, pending: 6, rounds: 3, backup: true,
  });
  assert.strictEqual(pre.ok, false);
  assert.match(pre.problems[0], /No empty video track above V1/);
});

test("an occupied V2 is not a workspace: the pre-flight sees it before the run does", async () => {
  const { P, tracks } = makeTimeline("A", { videoTracks: 2 });
  tracks.video[1].push({ kind: "video", track: 1, S: 50, E: 60, I: 0, O: 10, media: "title.png", getStartTime: async () => tt(50), getEndTime: async () => tt(60), getInPoint: async () => tt(0), getOutPoint: async () => tt(10), getSpeed: async () => 1, getName: async () => "title", getProjectItem: async () => ({ getName: async () => "title.png", getMediaFilePath: async () => "C:/title.png" }) });
  adapter._setPremiere(P);
  const t = await adapter.inspectTimeline({ mediaPath: "C:/vod.mp4" });
  assert.strictEqual(t.workspace.video, -1);
});

test("a failed cut says how far it got and how many temporary copies are still on the workspace tracks", async () => {
  const { P } = makeTimeline("C");
  adapter._setPremiere(P);
  await assert.rejects(
    () => adapter.cutAtClipEdges(clipItems([[100, 30]]), {}, () => {}),
    (e) => {
      assert.match(e.message, /Stopped after 0 of 2 cuts \(round 1\)/);
      assert.deepStrictEqual([e.state.done, e.state.total, e.state.round], [0, 2, 1]);
      assert.ok(e.state.leftover >= 1, `leftover ${e.state.leftover}`);
      return true;
    }
  );
});

test("a full Do it all run on the fake timeline: one backup, markers step, cut step, progress, outcome text", async () => {
  const { P, tracks, stats } = makeTimeline("A", { guid: "seq-full" });
  adapter._setPremiere(P);
  const steps = core.recipeSteps({});
  const items = clipItems([[100.5, 29.5], [200.2, 49.8]]);
  const seen = [];
  const out = await core.runRecipe(steps, {
    backup: () => adapter.backupSequence(() => {}),
    markers: async () => ({ added: 2, skipped: 0, what: "the clip" }),
    cut: () => adapter.cutAtClipEdges(items, { backup: false, onProgress: (e) => seen.push(e.phase) }, () => {}),
    shouldStop: () => false, onStep: () => {},
  });
  assert.strictEqual(out.ok, true);
  assert.strictEqual(stats.backups, 1);
  assert.strictEqual(tracks.video[0].length, 5);
  assert.ok(seen.includes("round-done"));
  assert.match(core.outcomeText(out, steps), /^Done: 2 markers added to the clip; 4 cuts made\./);
});

test("the cut plan probe on an already cut timeline says nothing is left, and shows each stretch as one line", async () => {
  const { P } = makeTimeline("A");
  adapter._setPremiere(P);
  const items = clipItems([[100, 30], [300.4, 40]]);
  const before = [];
  await adapter.probeCutPlan(items, (t) => before.push(t), undefined, { mediaPath: "C:/vod.mp4" });
  assert.ok(before.some((l) => /The cut would still make 4 cuts/.test(l)));
  await adapter.cutAtClipEdges(items, {}, () => {});
  const after = [];
  await adapter.probeCutPlan(items, (t) => after.push(t), undefined, { mediaPath: "C:/vod.mp4" });
  assert.ok(after.some((l) => /No cut left to make/.test(l)), after.join("\n"));
  const lines = after.filter((l) => /^\s+#\d+ timeline/.test(l));
  assert.strictEqual(lines.length, 2, "two clips, not one line per piece: " + lines.join(" | "));
});

// ---- 0.7.0: delete the gaps (ripple) ---------------------------------------------------------------------------
const HINT = { mediaPath: "C:/vod.mp4" };
const cutFirst = async (opts, list = [[100, 30], [300, 40], [600, 50]], mode = "A") => {
  const tl = makeTimeline(mode, opts);
  adapter._setPremiere(tl.P);
  const items = clipItems(list);
  await adapter.cutAtClipEdges(items, { hint: HINT }, () => {});
  return { ...tl, items };
};
const KEPT = [[0, 30, 100], [30, 70, 300], [70, 120, 600]];

test("deleteGaps: the clips end up back to back on V1 and A1, with ONE forced backup and MediaType.ANY + ripple=true", async () => {
  const { tracks, stats, items } = await cutFirst({ guid: "seq-del" });
  assert.strictEqual(tracks.video[0].length, 7);
  await adapter.backupSequence(() => {}); // a fresh backup exists: the delete must make its own anyway
  const before = stats.backups;
  const lines = [];
  const r = await adapter.deleteGaps(items, { hint: HINT, backup: true }, (t) => lines.push(t));
  assert.strictEqual(stats.backups, before + 1, "forced: the 30-minute skip does not apply");
  assert.deepStrictEqual([r.deleted, r.total, r.stopped, r.chunks], [4, 4, false, 1]);
  assert.deepStrictEqual(pieces(tracks.video[0]), KEPT);
  assert.deepStrictEqual(pieces(tracks.audio[0]), KEPT);
  const last = stats.removes[stats.removes.length - 1];
  assert.deepStrictEqual([last.n, last.ripple, last.media], [8, true, "any"], "4 video + 4 audio gap pieces, one action");
  assert.strictEqual(tracks.video[1].length + tracks.audio[1].length, 0);
  assert.ok(Math.abs(r.deletedSeconds - 880) < 0.01 && Math.abs(r.keepSeconds - 120) < 0.01, `${r.deletedSeconds} / ${r.keepSeconds}`);
  assert.ok(lines.some((l) => /^Gap plan: 4 pieces, 880 s, 88\.0%; keep 3 pieces, 120 s/.test(l)), lines.join("\n"));
  assert.ok(lines.some((l) => /Every remaining piece checked/.test(l)), lines.join("\n"));
  const again = await adapter.deleteGaps(items, { hint: HINT }, () => {});
  assert.deepStrictEqual([again.deleted, again.total], [0, 0], "nothing left to delete the second time");
});

test("deleteGaps in batches: progress per batch, Stop finishes the batch it is in, and a second run finishes the job", async () => {
  const { tracks, items } = await cutFirst();
  const ev = [];
  let stop = false;
  const first = await adapter.deleteGaps(items, { hint: HINT, chunk: 2, shouldStop: () => stop, onProgress: (e) => { ev.push([e.phase, e.round, e.rounds, e.done, e.total]); if (e.phase === "round-done" && e.round === 1) stop = true; } }, () => {});
  assert.deepStrictEqual([first.deleted, first.total, first.stopped, first.rounds, first.chunks], [2, 4, true, 1, 2]);
  assert.deepStrictEqual(ev, [["plan", 0, 2, 0, 4], ["round-start", 1, 2, 0, 4], ["round-done", 1, 2, 2, 4]]);
  assert.strictEqual(tracks.video[0].length, 5);
  assert.strictEqual(tracks.audio[0].length, 5);
  const second = await adapter.deleteGaps(items, { hint: HINT, chunk: 2 }, () => {});
  assert.deepStrictEqual([second.deleted, second.total, second.stopped, second.chunks], [2, 2, false, 1], "it works out what is left");
  assert.deepStrictEqual(pieces(tracks.video[0]), KEPT);
  assert.deepStrictEqual(pieces(tracks.audio[0]), KEPT);
});

test("deleteGaps asked to stop before the first batch touches nothing, not even the backup", async () => {
  const { stats, tracks, items } = await cutFirst({ guid: "seq-del-stop" });
  const removesBefore = stats.removes.length;
  const b = stats.backups;
  const r = await adapter.deleteGaps(items, { hint: HINT, backup: true, shouldStop: () => true }, () => {});
  assert.deepStrictEqual([r.stopped, r.deleted, r.total], [true, 0, 4]);
  assert.strictEqual(stats.removes.length, removesBefore);
  assert.strictEqual(stats.backups, b);
  assert.strictEqual(tracks.video[0].length, 7);
});

test("deleteGaps refuses before touching anything: uncut timeline, percentage limit, too few to keep, stale preview", async () => {
  const uncut = makeTimeline("A", { guid: "seq-refuse" });
  adapter._setPremiere(uncut.P);
  const items = clipItems([[100, 30], [300, 40], [600, 50]]);
  await assert.rejects(() => adapter.deleteGaps(items, { hint: HINT, backup: true }, () => {}), /Nothing was deleted\. 1 piece is only partly inside a clip .*Run the cut first/);
  assert.strictEqual(uncut.stats.backups, 0, "no backup for a run that refuses");
  assert.strictEqual(uncut.stats.removes.length, 0);

  const cut = await cutFirst({ guid: "seq-refuse2" });
  const n = cut.stats.removes.length;
  const refuse = (opts, re) => assert.rejects(() => adapter.deleteGaps(cut.items, { hint: HINT, backup: true, ...opts }, () => {}), re);
  await refuse({ maxDeletePct: 50 }, /limit in Settings is 50%/);
  await refuse({ minKeep: 5 }, /Only 3 pieces would be kept \(need at least 5\)/);
  await refuse({ expect: { deleteCount: 9, keepCount: 3 } }, /not what the preview showed/);
  assert.strictEqual(cut.stats.removes.length, n);
  assert.strictEqual(cut.stats.backups, 0);
  assert.strictEqual(cut.tracks.video[0].length, 7);
  const ok = await adapter.deleteGaps(cut.items, { hint: HINT, expect: { deleteCount: 4, keepCount: 3 } }, () => {});
  assert.strictEqual(ok.deleted, 4);
});

test("deleteGaps stops at the first batch that does not behave and says what is left: ripple ignored, audio left behind", async () => {
  for (const [behavior, re] of [["ignore", /V1: .*piece/], ["audio-stays", /A1: .*piece/]]) {
    const { tracks, items } = await cutFirst({ ripple: behavior });
    await assert.rejects(
      () => adapter.deleteGaps(items, { hint: HINT }, () => {}),
      (e) => {
        assert.match(e.message, /^Stopped in batch 1 of 1 after 0 of 4 gap pieces were deleted: after the ripple delete the timeline is not what it should be/);
        assert.match(e.message, re);
        assert.match(e.message, /Test ripple delete/);
        assert.deepStrictEqual([e.state.kind, e.state.deleted, e.state.total], ["delete", 0, 4]);
        assert.match(e.state.note, /partly applied/);
        return true;
      }
    );
    assert.ok(tracks.video[0].length < 7, "the pieces are gone, which is why it says to look at the timeline");
  }
});

test("deleteGaps leaves other media on the track alone (it just moves with the ripple) and notes items on other tracks", async () => {
  const tl = makeTimeline("A", { initial: [[0, 500, 0]], other: [[500, 900, 0, "other.mp4"]] });
  adapter._setPremiere(tl.P);
  const items = clipItems([[100, 30]]);
  await adapter.cutAtClipEdges(items, { hint: HINT }, () => {});
  tl.tracks.video[1].push({ kind: "video", track: 1, S: 50, E: 60, I: 0, O: 10, media: "title.png", getStartTime: async () => tt(50), getEndTime: async () => tt(60), getInPoint: async () => tt(0), getOutPoint: async () => tt(10), getSpeed: async () => 1, getName: async () => "title", getProjectItem: async () => ({ getName: async () => "title.png", getMediaFilePath: async () => "C:/title.png" }) });
  const lines = [];
  const r = await adapter.deleteGaps(items, { hint: HINT }, (t) => lines.push(t));
  assert.strictEqual(r.deleted, 2);
  assert.deepStrictEqual(pieces(tl.tracks.video[0]), [[0, 30, 100], [30, 430, 0]], "the other video moved 470 s to the left and is still there");
  assert.ok(lines.some((l) => /Note: 1 item on other tracks/.test(l)), lines.join("\n"));
});

test("deleteGaps at the size of the real VOD: 108 clips, 217 pieces, every batch verified", async () => {
  const list = [];
  for (let i = 0; i < 108; i++) list.push([100 + i * 318, 30.4]);
  const tl = makeTimeline("A", { len: 34379.862, fps: 60 });
  adapter._setPremiere(tl.P);
  const items = clipItems(list);
  await adapter.cutAtClipEdges(items, { hint: HINT }, () => {});
  assert.strictEqual(tl.tracks.video[0].length, 217);
  const r = await adapter.deleteGaps(items, { hint: HINT }, () => {});
  assert.deepStrictEqual([r.deleted, r.total, r.chunks], [109, 109, 2], "60 + 49");
  assert.strictEqual(tl.tracks.video[0].length, 108);
  assert.strictEqual(tl.tracks.audio[0].length, 108);
  const v = tl.tracks.video[0].slice().sort((a, b) => a.S - b.S);
  for (let i = 1; i < v.length; i++) assert.ok(Math.abs(v[i].S - v[i - 1].E) < 0.0001, "back to back");
  assert.ok(Math.abs(v[107].E - 108 * 30.4) < 0.5, `${v[107].E}`);
});

test("probeGapPlan describes the verdict without changing anything", async () => {
  const { stats, items } = await cutFirst();
  const n = stats.removes.length;
  const out = [];
  await adapter.probeGapPlan(items, (t) => out.push(t), { maxDeletePct: 99, minKeep: 1 }, HINT);
  assert.ok(out.some((l) => /Keep 3 pieces \(120\.0 s\), delete 4 pieces \(880\.0 s, 88\.0%\), 0 uncertain/.test(l)), out.join("\n"));
  assert.ok(out.some((l) => /Verdict: the safety guard lets this through/.test(l)));
  assert.strictEqual(stats.removes.length, n);
  const strict = [];
  await adapter.probeGapPlan(items, (t) => strict.push(t), { maxDeletePct: 50 }, HINT);
  assert.ok(strict.some((l) => /Verdict: REFUSED\. It would delete 88\.0%/.test(l)));
});

test("inspectTimeline reports video pieces without linked audio", async () => {
  const { P, tracks } = makeTimeline("A");
  adapter._setPremiere(P);
  assert.strictEqual((await adapter.inspectTimeline(HINT)).audioUnmatched, 0);
  tracks.audio[0].length = 0;
  assert.strictEqual((await adapter.inspectTimeline(HINT)).audioUnmatched, 0, "no audio at all is fine: nothing to leave behind");
});

// ---- the Test ripple delete experiment ---------------------------------------------------------------------------
async function runRipple(behavior) {
  const list = [];
  for (let i = 0; i < 60; i++) list.push([20 + i * 40, 10]);
  const tl = makeTimeline("A", { len: 2500, ripple: behavior });
  adapter._setPremiere(tl.P);
  await adapter.cutAtClipEdges(clipItems(list), { hint: HINT }, () => {});
  const lines = [];
  await adapter.testRippleDelete((t) => lines.push(t), HINT);
  return { ...tl, lines, text: lines.join("\n") };
}

test("Test ripple delete on a Premiere that behaves: every answer is YES, other tracks stay, test clips are removed again", async () => {
  const r = await runRipple("selected");
  assert.match(r.text, /1\. Later V pieces moved left by exactly the piece's length \(A, ripple=true\): YES\./);
  assert.match(r.text, /2\. A1: the linked audio piece was removed with it and later audio pieces moved too \(A\): YES/);
  assert.match(r.text, /3\. Other tracks .*: V2 STAYED, A2 STAYED/);
  assert.match(r.text, /4\. The second argument is really "ripple": YES \(true closed the gap: YES; false left a gap: YES\)/);
  assert.match(r.text, /5\. 10 NON-adjacent pieces in one action closed every gap correctly: V YES, A YES/);
  assert.match(r.text, /2 ADJACENT pieces in one action: V YES, A YES/);
  assert.match(r.text, /6\. Time of one remove action: 1 piece: \d+ ms; 10 pieces: \d+ ms; \d+ pieces: \d+ ms/);
  assert.match(r.text, /7\. .*MediaType\.VIDEO: V ripple YES; audio: its pieces stayed/);
  assert.match(r.text, /8\. Video-only selection with MediaType\.ANY: V ripple YES; audio: untouched/);
  assert.match(r.text, /Removed the 2 test clip\(s\) again/);
  assert.strictEqual(r.tracks.video[1].length + r.tracks.audio[1].length, 0);
  const sizes = r.stats.removes.map((x) => [x.n, x.ripple, x.media, !!x.shiftOverLapping]);
  assert.deepStrictEqual(sizes[sizes.length - 1].slice(1), [false, "any", false], "the clean-up is a plain remove");
  assert.ok(sizes.some((x) => x[0] >= 2 * 11), "the big scenario really removed many pieces in one action");
});

test("Test ripple delete tells the truth when Premiere does something else", async () => {
  const all = await runRipple("all");
  assert.match(all.text, /3\. Other tracks .*: V2 MOVED left, A2 MOVED left/);
  const ign = await runRipple("ignore");
  assert.match(ign.text, /1\. Later V pieces moved left by exactly the piece's length \(A, ripple=true\): NO\./);
  assert.match(ign.text, /4\. The second argument is really "ripple": NO/);
  const drift = await runRipple("audio-stays");
  assert.match(drift.text, /1\. .*: YES\./);
  assert.match(drift.text, /2\. A1: .*\(A\): NO/);
});

test("Test ripple delete refuses a timeline that is not cut, before changing anything", async () => {
  const { P, stats } = makeTimeline("A");
  adapter._setPremiere(P);
  await assert.rejects(() => adapter.testRippleDelete(() => {}, HINT), /at least 8 pieces/);
  assert.strictEqual(stats.removes.length, 0);
});

// ---- 0.7.3: Premiere closes each removed piece 0 to 1 frame short; the delete closes the holes and checks everything ------------
const FR = 1 / 60;
const sorted = (list) => list.slice().sort((x, y) => x.S - y.S);
const assertContiguous = (list, label) => {
  const v = sorted(list);
  assert.ok(Math.abs(v[0].S) < 0.0015, `${label}: starts at 0 (${v[0].S})`);
  for (let i = 1; i < v.length; i++) assert.ok(Math.abs(v[i].S - v[i - 1].E) < 0.0015, `${label}: piece ${i + 1} starts ${v[i].S}, the one before ends ${v[i - 1].E}`);
};

test("deleteGaps: each removed piece closed one frame short (the first real run) leaves holes that get closed; the clips end up exactly back to back", async () => {
  const { tracks, items } = await cutFirst({ ripple: "short", fps: 60 });
  const lines = [];
  const r = await adapter.deleteGaps(items, { hint: HINT }, (t) => lines.push(t));
  assert.deepStrictEqual([r.deleted, r.total, r.holes], [4, 4, 3], "3 holes: in front of each of the 3 clips (nothing follows the last gap)");
  assert.ok(Math.abs(r.holeSeconds - 3 * FR) < 1e-6);
  for (const kind of ["video", "audio"]) {
    const v = sorted(tracks[kind][0]);
    assert.strictEqual(v.length, 3);
    assertContiguous(v, kind);
    // the sources are the clips: only the in point of the first piece moved back and each out point grew, by one frame at most per hole
    assert.deepStrictEqual(v.map((x) => Math.round(x.I * 1000) / 1000), [99.983, 300, 600].map((x) => Math.round(x * 1000) / 1000));
    assert.ok(v[0].O - 130 > FR / 2 && v[0].O - 130 <= 1.01 * FR, `first clip's out point grew by about 1 frame: ${v[0].O}`);
    assert.ok(Math.abs(v[1].O - (340 + FR)) < 1e-6 && Math.abs(v[2].O - 650) < 1e-6, "the last clip's end is not touched");
  }
  assert.ok(lines.some((l) => /Batch 1 done in \d+ ms: 4 of 4 gap pieces deleted\. Premiere left 3 holes \(50\.0 ms = 3\.0 frames in all, for 4 removed pieces\); closed by lengthening the piece in front of each/.test(l)), lines.join("\n"));
  const again = await adapter.deleteGaps(items, { hint: HINT }, () => {});
  assert.deepStrictEqual([again.deleted, again.total], [0, 0], "the lengthened pieces still count as the clips: nothing to delete the second time");
});

test("deleteGaps closes a lone one-frame hole in front of the only kept piece (the start of the timeline)", async () => {
  const { tracks, items } = await cutFirst({ ripple: "short", fps: 60 }, [[100, 30]]);
  const r = await adapter.deleteGaps(items, { hint: HINT }, () => {});
  assert.strictEqual(r.holes, 1);
  const v = tracks.video[0];
  assert.strictEqual(v.length, 1);
  assert.ok(Math.abs(v[0].S) < 1e-6 && Math.abs(v[0].E - (30 + FR)) < 1e-6, `${v[0].S} -> ${v[0].E}`);
  assert.ok(Math.abs(v[0].I - (100 - FR)) < 1e-6 && Math.abs(v[0].O - 130) < 1e-6, "the source in point moved back with the start, the end of the clip is where it was");
});

test("deleteGaps at the size of the real VOD with the real pattern (0 or 1 frame short per removed piece): 2 batches, every one verified and closed", async () => {
  const list = [];
  for (let i = 0; i < 108; i++) list.push([100 + i * 318, 30.4]);
  const tl = makeTimeline("A", { len: 34379.862, fps: 60, ripple: "mixed" });
  adapter._setPremiere(tl.P);
  const items = clipItems(list);
  await adapter.cutAtClipEdges(items, { hint: HINT }, () => {});
  const lines = [];
  const r = await adapter.deleteGaps(items, { hint: HINT }, (t) => lines.push(t));
  assert.deepStrictEqual([r.deleted, r.total, r.chunks], [109, 109, 2]);
  assert.ok(r.holes > 50 && r.holes <= 108, `holes: ${r.holes}`);
  for (const kind of ["video", "audio"]) {
    const v = sorted(tl.tracks[kind][0]);
    assert.strictEqual(v.length, 108);
    assertContiguous(v, kind);
    v.forEach((x, i) => {
      const len = x.E - x.S;
      assert.ok(len >= 30.4 - 1e-6 && len <= 30.4 + 2 * FR + 1e-6, `piece ${i + 1} is ${len} s long`);
    });
  }
  assert.strictEqual(lines.filter((l) => /^Batch \d+ done/.test(l)).length, 2);
});

test("deleteGaps with fractions of a frame left by Premiere: holes under a millisecond stay, everything else is closed", async () => {
  const { tracks, items } = await cutFirst({ ripple: "frac", fps: 60 }, [[100, 30], [300, 40], [600, 50], [800, 10]]);
  await adapter.deleteGaps(items, { hint: HINT }, () => {});
  const v = sorted(tracks.video[0]);
  assert.strictEqual(v.length, 4);
  for (let i = 1; i < v.length; i++) assert.ok(Math.abs(v[i].S - v[i - 1].E) <= 0.001 + 1e-9, `gap before piece ${i + 1}: ${v[i].S - v[i - 1].E}`);
});

test("deleteGaps refuses what is worse than Premiere was seen to do: 3 frames short per removed piece, or closed too far (overlap)", async () => {
  for (const [behavior, re] of [["far", /3\.00 frames/], ["over", /-16\.7 ms|-1\.00 frames|-16\.7/]]) {
    const { items } = await cutFirst({ ripple: behavior, fps: 60 });
    await assert.rejects(
      () => adapter.deleteGaps(items, { hint: HINT }, () => {}),
      (e) => {
        assert.match(e.message, /^Stopped in batch 1 of 1 after 0 of 4 gap pieces were deleted: after the ripple delete the timeline is not what it should be/);
        assert.match(e.message, re, e.message);
        assert.strictEqual(e.state.deleted, 0);
        return true;
      }
    );
  }
});

test("deleteGaps in batches with holes: Stop after batch 1 leaves no hole behind, and the next run finishes", async () => {
  const list = [];
  for (let i = 0; i < 10; i++) list.push([100 + i * 50, 20]);
  const tl = makeTimeline("A", { len: 1000, fps: 60, ripple: "mixed" });
  adapter._setPremiere(tl.P);
  const items = clipItems(list);
  await adapter.cutAtClipEdges(items, { hint: HINT }, () => {});
  let batches = 0;
  const r1 = await adapter.deleteGaps(items, { hint: HINT, chunk: 4, onProgress: (e) => { if (e.phase === "round-done") batches++; }, shouldStop: () => batches >= 1 }, () => {});
  assert.strictEqual(r1.stopped, true);
  assert.strictEqual(r1.deleted, 4);
  const mid = sorted(tl.tracks.video[0]);
  const kept = mid.filter((x) => x.E - x.S < 25 && x.E - x.S > 15);
  for (let i = 1; i < kept.length; i++) if (Math.abs(kept[i].S - kept[i - 1].E) < 0.0015 === false) assert.ok(kept[i].S - kept[i - 1].E > 1, "only the gaps still to delete sit between the clips");
  assert.ok(Math.abs(kept[0].S) < 0.0015 || kept[0].S > 0, "the first clip starts at 0 after the lead hole is closed");
  const r2 = await adapter.deleteGaps(items, { hint: HINT, chunk: 4 }, () => {});
  assert.strictEqual(r2.stopped, false);
  assertContiguous(tl.tracks.video[0], "video");
  assertContiguous(tl.tracks.audio[0], "audio");
  assert.strictEqual(tl.tracks.video[0].length, 10);
});

test("deleteGaps stops with a clear message when closing the holes does not do what was asked", async () => {
  const { tracks, items } = await cutFirst({ ripple: "short", fps: 60 });
  for (const it of tracks.video[0]) it.createSetEndAction = () => () => {}; // Premiere accepts the edit and does nothing
  await assert.rejects(
    () => adapter.deleteGaps(items, { hint: HINT }, () => {}),
    (e) => {
      assert.match(e.message, /^Stopped in batch 1 of 1 after 4 of 4 gap pieces were deleted: 4 gap pieces are deleted, but after closing the holes Premiere left the timeline different from what was asked: V1 piece 1 of 3 reads/);
      assert.strictEqual(e.state.deleted, 4);
      assert.match(e.state.note, /holes may be only partly closed/);
      return true;
    }
  );
});

test("deleteGaps stops when setStart on this Premiere does not carry the source in point along (the lead hole cannot be closed safely)", async () => {
  const { items } = await cutFirst({ ripple: "short", fps: 60 }, [[100, 30], [300, 40]], "B");
  await assert.rejects(() => adapter.deleteGaps(items, { hint: HINT }, () => {}), /closing the holes/);
});

test("Test ripple delete measures the holes per removed piece and closes them (scenario I), on the real pattern", async () => {
  const r = await runRipple("mixed");
  assert.match(r.text, /Drift: first remaining piece [\d.]+ ms, last [\d.]+ ms/);
  assert.match(r.text, /5\. 10 NON-adjacent pieces in one action closed every gap correctly: V NO/, "with holes a plain ripple is not exact");
  assert.match(r.text, /9\. Hole left by Premiere's ripple, in frames per removed piece: .*A \d\.\d\d.*within one frame per removed piece.*: YES\./);
  assert.match(r.text, /--- I: 3 non-adjacent pieces, ripple=true, then close the holes/);
  assert.match(r.text, /10\. Closing the holes by lengthening the piece in front .*: YES/);
  assert.strictEqual(r.tracks.video[1].length + r.tracks.audio[1].length, 0, "test clips removed again");
});

test("Test ripple delete says so when Premiere closes more than a frame short per piece", async () => {
  const r = await runRipple("far");
  assert.match(r.text, /NOT within one frame per removed piece/);
  assert.match(r.text, /9\. Hole left .*: NO\./);
  assert.match(r.text, /10\. Closing the holes .*: NO \(ripple outside one frame per removed piece\)/);
});

test("Test ripple delete measures the per-piece drift", async () => {
  const r = await runRipple("short");
  assert.match(r.text, /Drift: first remaining piece [\d.]+ ms, last [\d.]+ ms .*per removed piece = 1\.00 frames\./);
  assert.match(r.text, /1\. Later V pieces moved left by exactly the piece's length \(A, ripple=true\): NO/);
});
