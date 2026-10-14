"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const core = require("../src/markers-core.js");

// The same file the Python tests check against what the app writes.
const SAMPLE = fs.readFileSync(path.join(__dirname, "..", "..", "tests", "fixtures", "markers_sample.json"), "utf8");
const file = () => core.parseMarkersFile(SAMPLE);

test("reads the file the app writes", () => {
  const f = file();
  assert.equal(f.version, 1);
  assert.equal(f.fps, 29.97);
  assert.equal(f.part.start, 1200);
  assert.equal(f.source.streamer, "Streamer");
  assert.deepEqual(f.markers.map((m) => m.kind), ["game", "clip", "game"]);
  assert.equal(f.markers[1].views, 120);
  assert.equal(f.markers[1].clips[0].url, "https://clips.twitch.tv/c1");
  assert.equal(f.skipped, 0);
});

test("a UTF-8 BOM in front of the JSON is fine", () => {
  assert.equal(core.parseMarkersFile("\uFEFF" + SAMPLE).markers.length, 3);
});

test("rejects things that are not a markers file, with a clear message", () => {
  assert.throws(() => core.parseMarkersFile("not json"), /not valid JSON/);
  assert.throws(() => core.parseMarkersFile("[]"), /not a LuckyTwitch markers file/);
  assert.throws(() => core.parseMarkersFile('{"format":"something-else","version":1,"markers":[]}'), /not a LuckyTwitch markers file/);
  assert.throws(() => core.parseMarkersFile(`{"format":"${core.FORMAT}","version":1}`), /no "markers" list/);
  assert.throws(() => core.parseMarkersFile(`{"format":"${core.FORMAT}","markers":[]}`), /valid version/);
});

test("a file from a newer app is refused instead of half-read", () => {
  const newer = JSON.stringify({ format: core.FORMAT, version: core.SUPPORTED_VERSION + 1, markers: [] });
  assert.throws(() => core.parseMarkersFile(newer), /newer than this plugin/);
});

test("bad entries are skipped and counted, good ones are kept", () => {
  const text = JSON.stringify({
    format: core.FORMAT,
    version: 1,
    markers: [
      { kind: "game", name: "A", start: 0, end: 5 },
      { kind: "mystery", name: "B", start: 0, end: 5 },
      { kind: "clip", name: "C", start: "x", end: 5 },
      { kind: "clip", name: "D", start: -1, end: 5 },
      null,
    ],
  });
  const f = core.parseMarkersFile(text);
  assert.equal(f.markers.length, 1);
  assert.equal(f.skipped, 4);
});

test("default plan: games blue, clips colored by views, in time order", () => {
  const { items, counts } = core.planMarkers(file(), {});
  assert.deepEqual(counts, { games: 2, clips: 1, hidden: 0 });
  assert.deepEqual(items.map((i) => [i.kind, i.name, i.start, i.duration, i.color]), [
    ["game", "Just Chatting", 0, 50, core.DEFAULT_SETTINGS.gameColor],
    ["clip", "Funny moment (bob, 120 views)", 7, 23, 1], // 120 views >= 50 -> red
    ["game", "Resident Evil 2", 50, 20, core.DEFAULT_SETTINGS.gameColor],
  ]);
  assert.equal(items[1].comment, "bob · 120 views · https://clips.twitch.tv/c1");
});

test("view tiers pick the color; below mid is the low color", () => {
  const s = core.normalizeSettings({ midViews: 10, highViews: 50, lowColor: 4, midColor: 3, highColor: 1 });
  assert.equal(core.colorForClip(9, s), 4);
  assert.equal(core.colorForClip(10, s), 3);
  assert.equal(core.colorForClip(49, s), 3);
  assert.equal(core.colorForClip(50, s), 1);
});

test("with color by views off every clip uses the one clip color", () => {
  const s = core.normalizeSettings({ colorByViews: false, clipColor: 7 });
  assert.equal(core.colorForClip(0, s), 7);
  assert.equal(core.colorForClip(100000, s), 7);
});

test("turning games or clips off leaves them out and counts them as hidden", () => {
  const noGames = core.planMarkers(file(), { importGames: false });
  assert.deepEqual(noGames.items.map((i) => i.kind), ["clip"]);
  assert.equal(noGames.counts.hidden, 2);
  const noClips = core.planMarkers(file(), { importClips: false });
  assert.deepEqual(noClips.items.map((i) => i.kind), ["game", "game"]);
  assert.equal(noClips.counts.hidden, 1);
});

test("minimum views drops the small clips", () => {
  assert.equal(core.planMarkers(file(), { minViews: 121 }).counts.clips, 0);
  assert.equal(core.planMarkers(file(), { minViews: 120 }).counts.clips, 1);
});

test("the GAME: prefix is optional", () => {
  const names = (s) => core.planMarkers(file(), s).items.filter((i) => i.kind === "game").map((i) => i.name);
  assert.deepEqual(names({}), ["Just Chatting", "Resident Evil 2"]);
  assert.deepEqual(names({ gamePrefix: true }), ["GAME: Just Chatting", "GAME: Resident Evil 2"]);
});

test("the base time (playhead) shifts every marker", () => {
  const { items } = core.planMarkers(file(), {}, 100);
  assert.deepEqual(items.map((i) => i.start), [100, 107, 150]);
});

test("a marker with no length gets duration 0", () => {
  const text = JSON.stringify({ format: core.FORMAT, version: 1, markers: [{ kind: "clip", name: "x", start: 5, end: 5 }] });
  assert.equal(core.planMarkers(core.parseMarkersFile(text), {}).items[0].duration, 0);
});

test("settings from storage are repaired, never trusted", () => {
  const s = core.normalizeSettings({ gameColor: 99, midViews: "abc", highViews: "75", offsetMode: "weird", importGames: 0 });
  assert.equal(s.gameColor, core.DEFAULT_SETTINGS.gameColor);
  assert.equal(s.midViews, core.DEFAULT_SETTINGS.midViews);
  assert.equal(s.highViews, 75);
  assert.equal(s.offsetMode, "start");
  assert.equal(s.importGames, false);
  assert.deepEqual(core.normalizeSettings(null), core.DEFAULT_SETTINGS);
});

test("time and color labels", () => {
  assert.equal(core.formatTime(0), "0:00:00");
  assert.equal(core.formatTime(3725), "1:02:05");
  assert.equal(core.colorName(1), "Red");
  assert.equal(core.colorName(42), "#42");
});
