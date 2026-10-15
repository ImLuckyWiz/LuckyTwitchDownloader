"use strict";
// Mocks the premierepro module to check the read-back: a Markers object fetched BEFORE the markers were added stays
// empty (stale snapshot), a fresh one sees them. The adapter must color the markers anyway.
const test = require("node:test");
const assert = require("node:assert");
const adapter = require("../src/premiere-adapter.js");

function makeMock() {
  const store = new Map(); // owner -> [marker]
  const colors = [];
  const P = {
    TickTime: { createWithSeconds: (s) => ({ seconds: s }) },
    Marker: { MARKER_TYPE_COMMENT: "Comment" },
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
        getActiveSequence: async () => sequence,
        executeTransaction: (fn) => {
          const acts = [];
          fn({ addAction: (a) => acts.push(a) });
          acts.forEach((a) => a());
          return true;
        },
      }),
    },
  };
  const sequence = { getPlayerPosition: async () => ({ seconds: 0 }) };
  return { P, colors };
}

test("sequence import colors every marker even though the first list was taken before adding", async () => {
  const { P, colors } = makeMock();
  adapter._setPremiere(P);
  const lines = [];
  const r = await adapter.importMarkers(
    [
      { name: "A", start: 0, duration: 1, color: 1, comment: "" },
      { name: "B", start: 5, duration: 1, color: 6, comment: "" },
    ],
    "start",
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
  const first = await adapter.importMarkers(items, "start", () => {});
  const second = await adapter.importMarkers(items, "start", () => {});
  assert.deepStrictEqual([first.added, first.skipped], [2, 0]);
  assert.deepStrictEqual([second.added, second.skipped], [0, 2]);
  const added = await adapter.importMarkers([...items, { name: "C", start: 9, duration: 1, color: 3, comment: "" }], "start", () => {});
  assert.deepStrictEqual([added.added, added.skipped], [1, 2]);
});

test("remove takes away only the markers of the file, and tells how many", async () => {
  const { P } = makeMock();
  adapter._setPremiere(P);
  const items = [
    { name: "A", start: 0, duration: 1, color: 1, comment: "" },
    { name: "B", start: 5, duration: 1, color: 6, comment: "" },
  ];
  await adapter.importMarkers(items, "start", () => {});
  await adapter.importMarkers([{ name: "mine", start: 20, duration: 1, color: 0, comment: "" }], "start", () => {});
  const gone = await adapter.removeMarkers(items, { placement: "sequence", offsetMode: "start" }, () => {});
  assert.strictEqual(gone.removed, 2);
  const again = await adapter.removeMarkers(items, { placement: "sequence", offsetMode: "start" }, () => {});
  assert.strictEqual(again.removed, 0);
  const rest = await adapter.importMarkers([{ name: "mine", start: 20, duration: 1, color: 0, comment: "" }], "start", () => {});
  assert.strictEqual(rest.skipped, 1, "the unrelated marker is still there");
});
