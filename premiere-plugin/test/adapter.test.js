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
  const n = await adapter.importMarkers(
    [
      { name: "A", start: 0, duration: 1, color: 1, comment: "" },
      { name: "B", start: 5, duration: 1, color: 6, comment: "" },
    ],
    "start",
    (t) => lines.push(t)
  );
  assert.strictEqual(n, 2);
  assert.deepStrictEqual(colors, [["A", 1], ["B", 6]]);
});
