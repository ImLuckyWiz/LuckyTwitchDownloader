"use strict";
// Mocks the premierepro module to check the read-back: a Markers object fetched BEFORE the markers were added stays
// empty (stale snapshot), a fresh one sees them. The adapter must color the markers anyway.
const test = require("node:test");
const assert = require("node:assert");
const adapter = require("../src/premiere-adapter.js");

const tt = (s) => ({ seconds: s });
const MEDIA = "C:/vod.mp4";
const HINT = { mediaPath: MEDIA };

/**
 * clip = {S, E, I}: the one clip on V1, playing source I.. from timeline S to E (default: 0-1000 from source 0, so times are unchanged).
 * selection = project items selected in the Project panel; sequence: false = the project has no sequence at all.
 */
function makeMock({ clip = { S: 0, E: 1000, I: 0 }, selection, sequence: hasSequence = true } = {}) {
  const store = new Map(); // owner -> [marker]
  const colors = [];
  const projectItem = { getName: async () => "vod.mp4", getMediaFilePath: async () => MEDIA };
  const item = {
    getStartTime: async () => tt(clip.S), getEndTime: async () => tt(clip.E), getInPoint: async () => tt(clip.I), getOutPoint: async () => tt(clip.I + clip.E - clip.S),
    getSpeed: async () => 1, getName: async () => "vod", getProjectItem: async () => projectItem,
  };
  const P = {
    TickTime: { createWithSeconds: (s) => ({ seconds: s }) },
    Marker: { MARKER_TYPE_COMMENT: "Comment" },
    Constants: { TrackItemType: { CLIP: 1 } },
    Markers: {
      getMarkers(owner) {
        const snapshot = (store.get(owner) || []).slice(); // a copy: later additions are not visible in it
        return {
          getMarkers: () => snapshot,
          createRemoveMarkerAction: (marker) => () => store.set(owner, (store.get(owner) || []).filter((m) => m !== marker)),
          createAddMarkerAction: (name, type, start, duration) => () => {
            const m = { name, start, createSetColorByIndexAction: (c) => () => colors.push([name, c]) };
            store.set(owner, [...(store.get(owner) || []), { getName: () => name, getStart: () => start, createSetColorByIndexAction: m.createSetColorByIndexAction }]);
          },
        };
      },
    },
    Project: {
      getActiveProject: async () => ({
        getActiveSequence: async () => (hasSequence ? sequence : null),
        executeTransaction: (fn) => {
          const acts = [];
          fn({ addAction: (a) => acts.push(a) });
          acts.forEach((a) => a());
          return true;
        },
      }),
    },
  };
  if (selection) P.ProjectUtils = { getSelection: async () => ({ getItems: async () => selection }) };
  const sequence = {
    getPlayerPosition: async () => tt(0),
    getVideoTrackCount: async () => 1, getAudioTrackCount: async () => 0,
    getVideoTrack: async () => ({ getTrackItems: async () => [item] }), getAudioTrack: async () => ({ getTrackItems: async () => [] }),
    getSelection: async () => ({ getTrackItems: async () => [] }),
  };
  return { P, colors, store, sequence, projectItem };
}

const SEQ = { placement: "sequence", hint: HINT };

test("sequence import colors every marker even though the first list was taken before adding", async () => {
  const { P, colors } = makeMock();
  adapter._setPremiere(P);
  const lines = [];
  const r = await adapter.addMarkers(
    [
      { name: "A", start: 0, duration: 1, color: 1, comment: "" },
      { name: "B", start: 5, duration: 1, color: 6, comment: "" },
    ],
    SEQ,
    (t) => lines.push(t)
  );
  assert.strictEqual(r.added, 2);
  assert.strictEqual(r.skipped, 0);
  assert.deepStrictEqual(colors, [["A", 1], ["B", 6]]);
});

test("running the import twice does not add the markers twice", async () => {
  const { P } = makeMock();
  adapter._setPremiere(P);
  const items = [
    { name: "A", start: 0, duration: 1, color: 1, comment: "" },
    { name: "B", start: 5, duration: 1, color: 6, comment: "" },
  ];
  const first = await adapter.addMarkers(items, SEQ, () => {});
  const second = await adapter.addMarkers(items, SEQ, () => {});
  assert.deepStrictEqual([first.added, first.skipped], [2, 0]);
  assert.deepStrictEqual([second.added, second.skipped], [0, 2]);
  const added = await adapter.addMarkers([...items, { name: "C", start: 9, duration: 1, color: 3, comment: "" }], SEQ, () => {});
  assert.deepStrictEqual([added.added, added.skipped], [1, 2]);
});

test("remove takes away only the markers of the file, and tells how many", async () => {
  const { P } = makeMock();
  adapter._setPremiere(P);
  const items = [
    { name: "A", start: 0, duration: 1, color: 1, comment: "" },
    { name: "B", start: 5, duration: 1, color: 6, comment: "" },
  ];
  await adapter.addMarkers(items, SEQ, () => {});
  await adapter.addMarkers([{ name: "mine", start: 20, duration: 1, color: 0, comment: "" }], SEQ, () => {});
  const gone = await adapter.removeMarkers(items, SEQ, () => {});
  assert.strictEqual(gone.removed, 2);
  const again = await adapter.removeMarkers(items, SEQ, () => {});
  assert.strictEqual(again.removed, 0);
  const rest = await adapter.addMarkers([{ name: "mine", start: 20, duration: 1, color: 0, comment: "" }], SEQ, () => {});
  assert.strictEqual(rest.skipped, 1, "the unrelated marker is still there");
});

// ---- 0.6.0: markers on the sequence go where the clip that plays them has them --------------------------------
test("markers on the sequence are mapped through the clip that plays them (not an offset from the start)", async () => {
  // the timeline plays source 1000-1500 from timeline 200 (the first stretch was deleted and the rest pushed along)
  const { P, store, sequence } = makeMock({ clip: { S: 200, E: 700, I: 1000 } });
  adapter._setPremiere(P);
  const lines = [];
  const r = await adapter.addMarkers(
    [
      { name: "before", start: 900, duration: 10, color: 1, comment: "" }, // not played
      { name: "A", start: 1100, duration: 30, color: 1, comment: "" },
      { name: "straddles", start: 990, duration: 30, color: 2, comment: "" }, // 990-1020: only 1000-1020 is played
      { name: "after", start: 1600, duration: 5, color: 3, comment: "" }, // not played
    ],
    SEQ,
    (t) => lines.push(t)
  );
  assert.strictEqual(r.added, 2);
  assert.strictEqual(r.outside, 2);
  const got = store.get(sequence).map((m) => [m.getName(), m.getStart().seconds]);
  assert.deepStrictEqual(got, [["A", 300], ["straddles", 200]]);
  assert.ok(lines.some((l) => /2 markers are outside what the timeline plays/.test(l)));
});

test("markers on the sequence refuse to guess when the file's video is not on the timeline", async () => {
  const { P } = makeMock({ clip: { S: 0, E: 100, I: 0 } });
  adapter._setPremiere(P);
  await assert.rejects(
    () => adapter.addMarkers([{ name: "A", start: 5000, duration: 1, color: 1, comment: "" }], SEQ, () => {}),
    /None of the markers falls inside what the timeline plays/
  );
});

test("markers on the clip go on the clip selected in the Project panel, with no sequence at all", async () => {
  const picked = { getName: async () => "vod.mp4", getMediaFilePath: async () => MEDIA };
  const folder = { getName: async () => "Bin" }; // no media file: not a clip
  const { P, store } = makeMock({ sequence: false, selection: [folder, picked] });
  adapter._setPremiere(P);
  const lines = [];
  const r = await adapter.addMarkers([{ name: "A", start: 12, duration: 1, color: 1, comment: "" }], { placement: "clip", hint: HINT }, (t) => lines.push(t));
  assert.strictEqual(r.added, 1);
  assert.match(r.what, /vod\.mp4/);
  assert.strictEqual(store.get(picked).length, 1, "the marker is on the project item, at source time");
  assert.ok(lines.some((l) => /clip selected in the Project panel/.test(l)));
});

test("a Project-panel clip that is not the file's video loses to the file's video on the timeline", async () => {
  const other = { getName: async () => "other.mp4", getMediaFilePath: async () => "C:/other.mp4" };
  const { P, store, projectItem } = makeMock({ selection: [other] });
  adapter._setPremiere(P);
  const r = await adapter.addMarkers([{ name: "A", start: 12, duration: 1, color: 1, comment: "" }], { placement: "clip", hint: HINT }, () => {});
  assert.strictEqual(r.added, 1);
  assert.strictEqual((store.get(projectItem) || []).length, 1, "on the timeline clip's source");
  assert.strictEqual(store.get(other), undefined);
});

test("with nothing on the timeline and nothing selected, the error says what to do", async () => {
  const { P } = makeMock({ sequence: false });
  adapter._setPremiere(P);
  await assert.rejects(() => adapter.addMarkers([{ name: "A", start: 1, duration: 1, color: 1, comment: "" }], { placement: "clip", hint: HINT }, () => {}), /Select the video in the Project panel/);
});

test("checkMarkers counts what is already on the target without changing anything", async () => {
  const { P, store, projectItem } = makeMock();
  adapter._setPremiere(P);
  const items = [{ name: "A", start: 12, duration: 1, color: 1, comment: "" }, { name: "B", start: 40, duration: 1, color: 1, comment: "" }];
  const before = await adapter.checkMarkers(items, { placement: "clip", hint: HINT });
  assert.deepStrictEqual([before.total, before.present], [2, 0]);
  await adapter.addMarkers(items.slice(0, 1), { placement: "clip", hint: HINT }, () => {});
  const after = await adapter.checkMarkers(items, { placement: "clip", hint: HINT });
  assert.deepStrictEqual([after.total, after.present], [2, 1]);
  assert.strictEqual(store.get(projectItem).length, 1, "checking added nothing");
});

test("the file is found with only a Project-panel selection (no active sequence)", async () => {
  const picked = { getName: async () => "vod.mp4", getMediaFilePath: async () => "E:\\Videos\\vod.mp4" };
  const { P } = makeMock({ sequence: false, selection: [picked] });
  adapter._setPremiere(P);
  const Module = require("node:module");
  const original = Module._load;
  const wanted = "file:/E:/Videos";
  Module._load = function (request, ...rest) {
    if (request !== "uxp") return original.call(this, request, ...rest);
    return { storage: { localFileSystem: { getEntryWithUrl: async (url) => {
      if (url !== wanted) throw new Error("no access");
      return { isFolder: true, getEntries: async () => [{ isFile: true, name: "vod.markers.json", nativePath: "E:\\Videos\\vod.markers.json", read: async () => "{json}" }] };
    } } } };
  };
  try {
    const why = [];
    const found = await adapter.findMarkersFile(why);
    assert.strictEqual(found.name, "vod.markers.json");
    assert.strictEqual(found.where, "next to the clip selected in the Project panel");
    assert.ok(why.some((w) => /no active sequence/.test(w)));
  } finally {
    Module._load = original;
  }
});

test("when getSelection(project) comes back empty, the Project panel's own selection (by view id) is used", async () => {
  const picked = { getName: async () => "vod.mp4", getMediaFilePath: async () => MEDIA };
  const { P, store } = makeMock({ sequence: false });
  P.ProjectUtils = {
    getSelection: async () => null, // what the 0.6.0 probe saw on a real Premiere
    getProjectViewIds: async () => ["view-1"],
    getSelectionFromViewId: async (id) => (id === "view-1" ? { getItems: async () => [picked] } : null),
  };
  adapter._setPremiere(P);
  const r = await adapter.addMarkers([{ name: "A", start: 12, duration: 1, color: 1, comment: "" }], { placement: "clip", hint: HINT }, () => {});
  assert.strictEqual(r.added, 1);
  assert.strictEqual(store.get(picked).length, 1);
  const lines = [];
  await adapter.probeSelection((t) => lines.push(t));
  assert.ok(lines.some((l) => /getSelection\(project\) gave: nothing/.test(l)));
  assert.ok(lines.some((l) => /getSelectionFromViewId\(view-1\): 1 item/.test(l)));
  assert.ok(lines.some((l) => /Selected clips with a media file: 1/.test(l)));
  // 0.7.0: one line per selected item with name, type, the cast result and the media path
  assert.ok(lines.some((l) => /\[1\] name: "vod\.mp4"; type: .*ClipProjectItem\.cast: not offered; media path on the item: C:\/vod\.mp4/.test(l)), lines.join("\n"));
});
