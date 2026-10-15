"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const core = require("../src/markers-core.js");

// The same file the Python tests check against what the app writes.
const repoCopy = path.join(__dirname, "..", "..", "tests", "fixtures", "markers_sample.json");
const SAMPLE = fs.readFileSync(fs.existsSync(repoCopy) ? repoCopy : path.join(__dirname, "fixtures", "markers_sample.json"), "utf8");
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

test("placement defaults to the clip and is repaired", () => {
  assert.equal(core.DEFAULT_SETTINGS.placement, "clip");
  assert.equal(core.normalizeSettings({ placement: "sequence" }).placement, "sequence");
  assert.equal(core.normalizeSettings({ placement: "x" }).placement, "clip");
});

test("the settings summary says what matters in one line", () => {
  assert.equal(core.summarizeSettings({}), "Games Blue · Clips by views (Yellow/Orange/Red) · on the clip");
  assert.equal(
    core.summarizeSettings({ importGames: false, colorByViews: false, clipColor: 7, minViews: 5, placement: "sequence" }),
    "No games · Clips Cyan · min 5 views · on the sequence"
  );
  assert.equal(core.summarizeSettings({ importClips: false }), "Games Blue · no clips · on the clip");
});

test("path helpers work for Windows and Mac paths", () => {
  const win = "E:\\VideosGuini\\IlloJuan\\2026 - DÚO\\part1.mp4";
  assert.equal(core.baseName(win), "part1.mp4");
  assert.equal(core.dirName(win), "E:\\VideosGuini\\IlloJuan\\2026 - DÚO");
  assert.equal(core.baseName("/Users/a/b/part1.mp4"), "part1.mp4");
  assert.equal(core.dirName("/Users/a/b/part1.mp4"), "/Users/a/b");
  assert.equal(core.dirName("part1.mp4"), "");
  assert.equal(core.stripExtension("a.b.mp4"), "a.b");
});

test("folder paths become file URLs with accents and spaces encoded", () => {
  const forms = core.fileUrlForms("E:\\Videos Guini\\DÚO");
  assert.equal(forms[0], "file:/E:/Videos%20Guini/D%C3%9AO");
  assert.equal(forms[1], "file:///E:/Videos%20Guini/D%C3%9AO");
  assert.equal(forms[2], "E:\\Videos Guini\\DÚO");
  assert.equal(core.fileUrlForms("/Users/a b")[0], "file:/Users/a%20b");
  assert.deepEqual(core.fileUrlForms(""), []);
});

test("picks the markers file that belongs to the video", () => {
  const names = ["x - part1.mp4", "x - part1.markers.json", "x - part2.markers.json", "x - part1.markers.xml", "x - part1.clips.json"];
  assert.deepEqual(core.pickMarkersFile(names, "x - part1.mp4"), { name: "x - part1.markers.json", how: "same name as the video" });
  assert.equal(core.pickMarkersFile(names, "x - part2.mp4").name, "x - part2.markers.json");
  assert.equal(core.pickMarkersFile(names, "X - PART1.MP4").name, "x - part1.markers.json", "case does not matter");
  // two files and a video that matches neither: not guessed
  assert.equal(core.pickMarkersFile(names, "other.mp4"), null);
  assert.equal(core.pickMarkersFile(names), null);
  // a single file is accepted even if the name differs, and says so
  assert.deepEqual(core.pickMarkersFile(["a.markers.json", "a.mp4"], "b.mp4"), { name: "a.markers.json", how: "the only one in the folder" });
  assert.equal(core.pickMarkersFile(["a.mp4"], "a.mp4"), null);
  assert.equal(core.pickMarkersFile([], "a.mp4"), null);
  // name that starts like the video's (e.g. the file has a suffix)
  assert.equal(core.pickMarkersFile(["v.final.markers.json", "z.markers.json"], "v.mp4").name, "v.final.markers.json");
});

const item = (start, duration, kind = "clip", name = "c") => ({ kind, name, start, duration });

test("cut plan: only clips, overlapping stretches merge, padding applies, no-length clips are counted", () => {
  const items = [item(100, 20, "clip", "a"), item(110, 30, "clip", "b"), item(300, 10), item(500, 0), item(0, 50, "game")];
  const p = core.planCuts(items);
  assert.deepEqual(p.ranges.map((r) => [r.start, r.end]), [[100, 140], [300, 310]]);
  assert.deepEqual(p.ranges[0].names, ["a", "b"]);
  assert.equal(p.merged, 1);
  assert.equal(p.noLength, 1);
  const padded = core.planCuts(items, { padBefore: 5, padAfter: 10, min: 0, max: 315 });
  assert.deepEqual(padded.ranges.map((r) => [r.start, r.end]), [[95, 150], [295, 315]]);
  const withGames = core.planCuts(items, { kinds: ["game", "clip"] });
  assert.equal(withGames.ranges[0].start, 0);
  assert.deepEqual(core.planCuts(items, { mergeGap: 200 }).ranges.map((r) => [r.start, r.end]), [[100, 310]]);
});

test("cuts on a clip: source time maps to timeline time and is trimmed to what the clip plays", () => {
  const clip = { start: 10, end: 110, inPoint: 50, outPoint: 150, speed: 1 };
  const cuts = core.cutsForClip([{ start: 40, end: 60, names: ["a"] }, { start: 120, end: 200, names: ["b"] }, { start: 0, end: 30, names: ["gone"] }], clip);
  assert.deepEqual(cuts.map((c) => [c.srcStart, c.srcEnd, c.tlStart, c.tlEnd]), [[50, 60, 10, 20], [120, 150, 80, 110]]);
  assert.deepEqual(core.cutPoints(cuts, clip), [20, 80]); // the clip's own ends (10 and 110) are not cuts
  const fast = core.cutsForClip([{ start: 60, end: 80, names: [] }], { start: 0, end: 50, inPoint: 50, outPoint: 150, speed: 2 });
  assert.deepEqual([fast[0].tlStart, fast[0].tlEnd], [5, 15]);
});

test("the sample clip becomes one stretch to cut", () => {
  const { items } = core.planMarkers(file(), {});
  const p = core.planCuts(items);
  assert.deepEqual(p.ranges.map((r) => [r.start, r.end]), [[7, 30]]);
});

// ---- 0.5.0: cut set, timeline mapping, coverage, new settings ----------------------------------------------------
test("new settings have safe defaults and are validated", () => {
  const d = core.normalizeSettings(null);
  assert.equal(d.padBefore, 0);
  assert.equal(d.padAfter, 0);
  assert.equal(d.mergeGap, 0);
  assert.equal(d.backup, true);
  const s = core.normalizeSettings({ padBefore: "1.5", padAfter: "-3", mergeGap: "abc", backup: false });
  assert.equal(s.padBefore, 1.5);
  assert.equal(s.padAfter, 0, "a negative pad falls back to the default");
  assert.equal(s.mergeGap, 0);
  assert.equal(s.backup, false);
  assert.match(core.summarizeSettings({ padBefore: 1, padAfter: 2, mergeGap: 3 }), /pad 1s\/2s · merge < 3s/);
});

test("cut set: clips give padded merged ranges, chapters give boundaries that are never merged", () => {
  const items = [
    item(100, 20, "clip", "a"), item(120, 10, "clip", "b"), // touch: one range, no cut between them
    item(200, 10, "clip", "c"),
    item(0, 150, "game", "Chatting"), item(150, 150, "game", "Game 2"),
  ];
  const clipsOnly = core.planCutSet(items);
  assert.deepEqual(clipsOnly.ranges.map((r) => [r.start, r.end]), [[100, 130], [200, 210]]);
  assert.deepEqual(clipsOnly.points, [100, 130, 200, 210]);
  assert.deepEqual(clipsOnly.chapters, []);
  const chaptersOnly = core.planCutSet(items, { clips: false, chapters: true });
  assert.deepEqual(chaptersOnly.chapters.map((c) => [c.start, c.end]), [[0, 150], [150, 300]]);
  assert.deepEqual(chaptersOnly.points, [0, 150, 300], "the shared boundary is one point");
  const both = core.planCutSet(items, { chapters: true });
  assert.deepEqual(both.points, [0, 100, 130, 150, 200, 210, 300]);
});

test("cut set: padding never puts a cut between clips that end up touching", () => {
  const items = [item(100, 20), item(124, 10), item(300, 10)];
  const p = core.planCutSet(items, { padBefore: 3, padAfter: 3 });
  assert.deepEqual(p.ranges.map((r) => [r.start, r.end]), [[97, 137], [297, 313]], "100-120 and 124-134 grow into each other and merge");
  assert.equal(p.merged, 1);
});

test("timeline points: a clip that starts later in the source ignores earlier points", () => {
  // the first hour of the source was deleted: the clip plays source 1800-2400 from timeline 0
  const clips = [{ start: 0, end: 600, inPoint: 1800, outPoint: 2400, speed: 1 }];
  const pts = core.timelinePoints([1700, 1850, 2000, 2100, 2500], clips);
  assert.deepEqual(pts.map((p) => p.tl), [50, 200, 300]);
  assert.deepEqual(pts.map((p) => p.src), [1850, 2000, 2100]);
});

test("timeline points: several pieces of the same media, speed, and edges that are not cuts", () => {
  const clips = [
    { start: 0, end: 100, inPoint: 0, outPoint: 100, speed: 1 },
    { start: 100, end: 150, inPoint: 200, outPoint: 300, speed: 2 }, // plays source 200-300 at double speed
  ];
  const pts = core.timelinePoints([0, 50, 100, 200, 250, 300], clips);
  assert.deepEqual(pts.map((p) => [p.tl, p.src]), [[50, 50], [125, 250]], "0/100/200/300 sit on clip edges");
});

test("coverage: merged source windows and how many keep-ranges fall inside them", () => {
  const clips = [
    { inPoint: 1800, outPoint: 2000 }, { inPoint: 2000, outPoint: 2400 }, // touching pieces form one window
    { inPoint: 3000, outPoint: 3100 },
  ];
  const c = core.coverage([{ start: 1700, end: 1850 }, { start: 2100, end: 2200 }, { start: 2500, end: 2600 }, { start: 3050, end: 3060 }], clips);
  assert.deepEqual(c.windows, [{ start: 1800, end: 2400 }, { start: 3000, end: 3100 }]);
  assert.equal(c.inside, 3, "the first range overlaps the window by being clamped");
  assert.equal(c.outside, 1);
});

test("markers file name belongs to a video", () => {
  const m = core.markersNameMatchesMedia;
  assert.ok(m("IlloJuan - part1.markers.json", "E:\\a\\IlloJuan - part1.mp4"));
  assert.ok(m("v.final.markers.json", "/x/v.mp4"));
  assert.ok(m("video.markers.json", "/x/video.final.mp4"));
  assert.ok(!m("v.markers.json", "/x/v.final.mp4"), "a very short name is too loose to trust");
  assert.ok(!m("other.markers.json", "/x/v.mp4"));
  assert.ok(!m("(pasted text)", "/x/v.mp4"));
  assert.ok(!m("v.markers.xml", "/x/v.mp4"));
});
