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

function makeTimeline(mode, { videoTracks = 2, audioTracks = 3, len = 1000, fps = 30, initial, other = [], selected } = {}) {
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
    createCloneAction: () => () => {},
  };
  const editor = {
    createCloneTrackItemAction: (item, off, vOff, aOff) => () => {
      const dest = item.track + (item.kind === "video" ? vOff : aOff);
      const S = item.S + off.seconds, E = item.E + off.seconds;
      for (const o of tracks[item.kind][dest]) if (o.S < E - 1e-6 && o.E > S + 1e-6) throw new Error(`fake: clone would overwrite ${o.S}-${o.E} on track ${dest}`);
      mk(item.kind, dest, S, E, item.I, item.media);
    },
    createRemoveItemsAction: (sel) => () => {
      for (const it of sel.items) tracks[it.kind][it.track] = tracks[it.kind][it.track].filter((x) => x !== it);
    },
  };
  const stats = { tx: 0 };
  const P = {
    TickTime: { createWithSeconds: (s) => tt(s) },
    Constants: { TrackItemType: { CLIP: 1 }, MediaType: { ANY: {} } },
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
