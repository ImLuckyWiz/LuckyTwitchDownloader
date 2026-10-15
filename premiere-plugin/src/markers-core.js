"use strict";
/*
 * Pure logic of the plugin: read a .markers.json, check it, and turn it into the list of markers to create
 * (name, comment, time, duration, color). It knows nothing about Premiere, so it is tested with plain Node
 * (npm test) against tests/fixtures/markers_sample.json, which the Python app's tests keep in sync.
 */

const FORMAT = "luckytwitch-markers";
const SUPPORTED_VERSION = 1; // the file version this plugin understands (MARKERS_JSON_VERSION in the app)

// Premiere's marker color presets, in the order of its "Marker color" menu.
// The index is what the API takes. Use Diagnostics > "Add test markers" to confirm the order on your build.
const COLORS = [
  { index: 0, name: "Green" },
  { index: 1, name: "Red" },
  { index: 2, name: "Purple" },
  { index: 3, name: "Orange" },
  { index: 4, name: "Yellow" },
  { index: 5, name: "White" },
  { index: 6, name: "Blue" },
  { index: 7, name: "Cyan" },
];
const GREEN = 0, RED = 1, ORANGE = 3, YELLOW = 4, BLUE = 6;

const DEFAULT_SETTINGS = {
  importGames: true,
  importClips: true,
  gameColor: BLUE,
  colorByViews: true, // clips take the color of their view tier; off = all clips use clipColor
  clipColor: YELLOW,
  lowColor: YELLOW, // fewer views than midViews
  midColor: ORANGE, // midViews or more
  highColor: RED, // highViews or more
  midViews: 10,
  highViews: 50,
  minViews: 0, // clips with fewer views are skipped
  gamePrefix: false, // name game markers "GAME: <game>" like the XML does
  offsetMode: "start", // "start" = the part begins at the start of the sequence, "playhead" = at the playhead
  placement: "clip", // "clip" = markers on the clip's source (they follow your cuts), "sequence" = fixed times on the timeline
  padBefore: 0, // seconds kept before each clip when cutting (clips that touch or overlap after padding are merged)
  padAfter: 0, // seconds kept after each clip when cutting
  mergeGap: 0, // clips closer together than this many seconds are treated as one when cutting
  backup: true, // duplicate the sequence before cutting
};

class MarkersFileError extends Error {
  constructor(message) {
    super(message);
    this.name = "MarkersFileError";
  }
}

const isNum = (n) => typeof n === "number" && Number.isFinite(n);

/** Text of a .markers.json -> checked file object. Throws MarkersFileError with a message fit for the panel. */
function parseMarkersFile(text) {
  let data;
  try {
    data = JSON.parse(String(text).replace(/^\uFEFF/, ""));
  } catch (e) {
    throw new MarkersFileError("That file is not valid JSON. Pick the .markers.json that LuckyTwitch wrote next to the video.");
  }
  if (!data || typeof data !== "object" || data.format !== FORMAT) {
    throw new MarkersFileError("That is not a LuckyTwitch markers file. Pick the .markers.json written next to the video (not the .markers.xml or .clips.json).");
  }
  if (!isNum(data.version) || data.version < 1) {
    throw new MarkersFileError("The markers file has no valid version number.");
  }
  if (data.version > SUPPORTED_VERSION) {
    throw new MarkersFileError(
      `This markers file is version ${data.version}, newer than this plugin understands (version ${SUPPORTED_VERSION}). Update the plugin to the one that comes with your LuckyTwitch Downloader.`
    );
  }
  if (!Array.isArray(data.markers)) {
    throw new MarkersFileError("The markers file has no \"markers\" list.");
  }
  const markers = [];
  let skipped = 0;
  for (const m of data.markers) {
    const ok = m && (m.kind === "game" || m.kind === "clip") && isNum(m.start) && isNum(m.end) && m.start >= 0;
    if (!ok) {
      skipped++;
      continue;
    }
    markers.push({
      kind: m.kind,
      name: String(m.name ?? ""),
      start: m.start,
      end: m.end,
      comment: typeof m.comment === "string" ? m.comment : "",
      views: isNum(m.views) ? m.views : 0,
      game: typeof m.game === "string" ? m.game : null,
      clips: Array.isArray(m.clips) ? m.clips : [],
    });
  }
  return {
    version: data.version,
    name: typeof data.name === "string" ? data.name : "",
    fps: isNum(data.fps) ? data.fps : null,
    duration: isNum(data.duration) ? data.duration : null,
    part: data.part && isNum(data.part.start) ? data.part : null,
    source: data.source && typeof data.source === "object" ? data.source : null,
    markers,
    skipped,
  };
}

const colorIndex = (v, fallback) => (Number.isInteger(v) && v >= 0 && v < COLORS.length ? v : fallback);
const count = (v, fallback) => (isNum(Number(v)) && Number(v) >= 0 && v !== "" && v !== null ? Number(v) : fallback);

/** Whatever was stored / typed -> a complete, valid settings object. */
function normalizeSettings(raw) {
  const r = raw && typeof raw === "object" ? raw : {};
  const d = DEFAULT_SETTINGS;
  return {
    importGames: r.importGames === undefined ? d.importGames : !!r.importGames,
    importClips: r.importClips === undefined ? d.importClips : !!r.importClips,
    gameColor: colorIndex(r.gameColor, d.gameColor),
    colorByViews: r.colorByViews === undefined ? d.colorByViews : !!r.colorByViews,
    clipColor: colorIndex(r.clipColor, d.clipColor),
    lowColor: colorIndex(r.lowColor, d.lowColor),
    midColor: colorIndex(r.midColor, d.midColor),
    highColor: colorIndex(r.highColor, d.highColor),
    midViews: count(r.midViews, d.midViews),
    highViews: count(r.highViews, d.highViews),
    minViews: count(r.minViews, d.minViews),
    gamePrefix: r.gamePrefix === undefined ? d.gamePrefix : !!r.gamePrefix,
    offsetMode: r.offsetMode === "playhead" ? "playhead" : "start",
    placement: r.placement === "sequence" ? "sequence" : "clip",
    padBefore: count(r.padBefore, d.padBefore),
    padAfter: count(r.padAfter, d.padAfter),
    mergeGap: count(r.mergeGap, d.mergeGap),
    backup: r.backup === undefined ? d.backup : !!r.backup,
  };
}

function colorForClip(views, s) {
  if (!s.colorByViews) return s.clipColor;
  if (views >= s.highViews) return s.highColor;
  if (views >= s.midViews) return s.midColor;
  return s.lowColor;
}

/**
 * File + settings -> what to create. `baseSeconds` is where the start of the part lands in the sequence
 * (0, or the playhead). Times are seconds; a marker with no length (end <= start) gets duration 0.
 */
function planMarkers(file, rawSettings, baseSeconds = 0) {
  const s = normalizeSettings(rawSettings);
  const items = [];
  const counts = { games: 0, clips: 0, hidden: 0 };
  for (const m of file.markers) {
    if (m.kind === "game") {
      if (!s.importGames) {
        counts.hidden++;
        continue;
      }
      counts.games++;
      items.push({
        kind: "game",
        name: s.gamePrefix ? `GAME: ${m.name}` : m.name,
        comment: m.comment,
        start: baseSeconds + m.start,
        duration: Math.max(0, m.end - m.start),
        color: s.gameColor,
      });
    } else {
      if (!s.importClips || m.views < s.minViews) {
        counts.hidden++;
        continue;
      }
      counts.clips++;
      items.push({
        kind: "clip",
        name: m.name,
        comment: m.comment,
        start: baseSeconds + m.start,
        duration: Math.max(0, m.end - m.start),
        color: colorForClip(m.views, s),
      });
    }
  }
  items.sort((a, b) => a.start - b.start || (a.kind === b.kind ? 0 : a.kind === "game" ? -1 : 1));
  return { items, counts };
}

function formatTime(seconds) {
  const t = Math.max(0, Math.round(seconds));
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const sec = t % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

function colorName(index) {
  const c = COLORS.find((x) => x.index === index);
  return c ? c.name : `#${index}`;
}

/** One line that tells what the (collapsed) settings are, so nobody has to open them to know. */
function summarizeSettings(raw) {
  const s = normalizeSettings(raw);
  const parts = [];
  parts.push(s.importGames ? `Games ${colorName(s.gameColor)}` : "No games");
  if (!s.importClips) parts.push("no clips");
  else {
    parts.push(s.colorByViews ? `Clips by views (${colorName(s.lowColor)}/${colorName(s.midColor)}/${colorName(s.highColor)})` : `Clips ${colorName(s.clipColor)}`);
    if (s.minViews > 0) parts.push(`min ${s.minViews} views`);
  }
  parts.push(s.placement === "clip" ? "on the clip" : "on the sequence");
  if (s.padBefore > 0 || s.padAfter > 0) parts.push(`pad ${s.padBefore}s/${s.padAfter}s`);
  if (s.mergeGap > 0) parts.push(`merge < ${s.mergeGap}s`);
  return parts.join(" · ");
}

// ---- finding the markers file by itself -------------------------------------------------------------------
const MARKERS_SUFFIX = ".markers.json";

/** "E:\\a\\b\\video.mp4" or "/a/b/video.mp4" -> "video.mp4" */
function baseName(path) {
  const s = String(path || "");
  return s.slice(Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\")) + 1);
}

/** "E:\\a\\b\\video.mp4" -> "E:\\a\\b" (no trailing slash; "" when there is no folder part) */
function dirName(path) {
  const s = String(path || "");
  const i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
  return i < 0 ? "" : s.slice(0, i);
}

function stripExtension(name) {
  const i = String(name).lastIndexOf(".");
  return i > 0 ? String(name).slice(0, i) : String(name);
}

/** The ways a folder path can be written for UXP's getEntryWithUrl, most likely first (file:/ + percent-encoding handles "Ú", spaces...). */
function fileUrlForms(path) {
  const s = String(path || "");
  if (!s) return [];
  const forward = s.replace(/\\/g, "/");
  const encoded = forward
    .split("/")
    .map((seg, i) => (i === 0 && /^[A-Za-z]:$/.test(seg) ? seg : encodeURIComponent(seg)))
    .join("/");
  const rooted = encoded.startsWith("/") ? encoded : "/" + encoded; // "/E:/..." or "/Users/..."
  return Array.from(new Set(["file:" + rooted, "file://" + rooted, s]));
}

/**
 * Which of a folder's file names is the markers file for this video?
 * Returns {name, how} or null. With a video name it prefers "<video>.markers.json", then a name that starts like it;
 * a lone .markers.json in the folder is accepted last (the panel shows which file it took, so a wrong guess is visible).
 */
function pickMarkersFile(names, mediaFileName) {
  const lower = (x) => String(x).toLowerCase();
  const cands = (names || []).filter((n) => lower(n).endsWith(MARKERS_SUFFIX));
  if (!cands.length) return null;
  if (mediaFileName) {
    const stem = lower(stripExtension(baseName(mediaFileName)));
    const exact = cands.find((n) => lower(n) === stem + MARKERS_SUFFIX);
    if (exact) return { name: exact, how: "same name as the video" };
    const starts = cands.filter((n) => lower(n).startsWith(stem)).sort((a, b) => a.length - b.length);
    if (starts.length) return { name: starts[0], how: "name starts like the video's" };
    const inside = cands.filter((n) => {
      const st = lower(n.slice(0, -MARKERS_SUFFIX.length));
      return st.length > 3 && stem.startsWith(st);
    });
    if (inside.length === 1) return { name: inside[0], how: "the video's name starts like the file's" };
  }
  if (cands.length === 1) return { name: cands[0], how: "the only one in the folder" };
  return null;
}

// ---- cut planning (used by the dry-run probe now, and by the cutting feature later) -----------------------
/**
 * Marker items -> the stretches of SOURCE time to keep/cut around, as [{start, end, names}] (seconds).
 * Overlapping (or `mergeGap`-close) stretches are merged so no point is cut twice. Items with no length are
 * counted in `noLength` and left out (there is no "out" to cut at).
 * opts: kinds (default ["clip"]), padBefore, padAfter, mergeGap, min, max (clamp to the media).
 */
function planCuts(items, opts) {
  const o = Object.assign({ kinds: ["clip"], padBefore: 0, padAfter: 0, mergeGap: 0, min: 0, max: Infinity }, opts || {});
  const wanted = (items || []).filter((i) => o.kinds.includes(i.kind));
  const noLength = wanted.filter((i) => !(i.duration > 0)).length;
  const raw = wanted
    .filter((i) => i.duration > 0)
    .map((i) => ({ start: Math.max(o.min, i.start - o.padBefore), end: Math.min(o.max, i.start + i.duration + o.padAfter), names: [i.name] }))
    .filter((r) => r.end > r.start)
    .sort((a, b) => a.start - b.start);
  const ranges = [];
  for (const r of raw) {
    const last = ranges[ranges.length - 1];
    if (last && r.start <= last.end + o.mergeGap + 0.001) {
      last.end = Math.max(last.end, r.end);
      last.names.push(...r.names);
    } else ranges.push({ start: r.start, end: r.end, names: r.names.slice() });
  }
  return { ranges, merged: raw.length - ranges.length, noLength };
}

/**
 * Source-time stretches -> where they fall on the timeline for one clip
 * clip = {start, end (timeline s), inPoint, outPoint (source s), speed}. Stretches are trimmed to what the clip plays.
 */
function cutsForClip(ranges, clip) {
  const speed = clip.speed > 0 ? clip.speed : 1;
  const out = [];
  for (const r of ranges) {
    const s = Math.max(r.start, clip.inPoint);
    const e = Math.min(r.end, clip.outPoint);
    if (!(e > s)) continue;
    out.push({
      srcStart: s,
      srcEnd: e,
      tlStart: clip.start + (s - clip.inPoint) / speed,
      tlEnd: clip.start + (e - clip.inPoint) / speed,
      names: r.names,
    });
  }
  return out;
}

/** The distinct timeline times where a razor would have to cut (the clip's own two ends are not cuts). */
function cutPoints(cuts, clip) {
  const eps = 0.0005;
  const pts = [];
  for (const c of cuts) for (const t of [c.tlStart, c.tlEnd]) if (t > clip.start + eps && t < clip.end - eps) pts.push(t);
  return Array.from(new Set(pts.map((t) => Math.round(t * 1000) / 1000))).sort((a, b) => a - b);
}


// ---- the cut set: clips and/or chapters -> source-time cut points -> timeline times, for any number of timeline clips ----
/**
 * Marker items -> everything a cut run needs, in SOURCE seconds (seconds into the video file, which is what the markers file uses).
 * opts: clips (default true), chapters (default false), padBefore, padAfter, mergeGap, min, max.
 * - ranges: the stretches to keep from the clip markers (padded; touching / overlapping / mergeGap-close ones merged, so two clips next
 *   to each other get no padding between them and no cut between them).
 * - chapters: the game / category markers that have a length. They are NOT merged, because their boundaries are what we cut at.
 * - points: every distinct source time a razor would cut at (ranges' ends + chapter boundaries), sorted.
 */
function planCutSet(items, opts) {
  const o = Object.assign({ clips: true, chapters: false, padBefore: 0, padAfter: 0, mergeGap: 0, min: 0, max: Infinity }, opts || {});
  const clipPlan = o.clips
    ? planCuts(items, { kinds: ["clip"], padBefore: o.padBefore, padAfter: o.padAfter, mergeGap: o.mergeGap, min: o.min, max: o.max })
    : { ranges: [], merged: 0, noLength: 0 };
  const chapters = [];
  if (o.chapters) {
    for (const i of items || []) {
      if (i.kind !== "game" || !(i.duration > 0)) continue;
      const start = Math.max(o.min, i.start);
      const end = Math.min(o.max, i.start + i.duration);
      if (end > start) chapters.push({ start, end, name: i.name });
    }
    chapters.sort((a, b) => a.start - b.start);
  }
  const raw = [];
  for (const r of clipPlan.ranges) raw.push(r.start, r.end);
  for (const c of chapters) raw.push(c.start, c.end);
  const points = Array.from(new Set(raw.map((t) => Math.round(t * 1000) / 1000))).sort((a, b) => a - b);
  return { ranges: clipPlan.ranges, chapters, points, merged: clipPlan.merged, noLength: clipPlan.noLength };
}

/**
 * Source-time points -> timeline cut points over several timeline clips (all playing the same media).
 * clips = [{start, end (timeline s), inPoint, outPoint (source s), speed}]. Each clip only gets the points inside what it plays
 * (so a clip that starts later in the source, e.g. after you deleted the first hour, simply ignores the earlier points).
 * Returns [{tl, src}] sorted by timeline time; points on a clip's own edges are not cuts.
 */
function timelinePoints(points, clips) {
  const eps = 0.0005;
  const out = [];
  for (const c of clips || []) {
    const speed = c.speed > 0 ? c.speed : 1;
    for (const p of points || []) {
      if (!(p > c.inPoint + eps && p < c.outPoint - eps)) continue;
      const tl = c.start + (p - c.inPoint) / speed;
      if (tl > c.start + eps && tl < c.end - eps) out.push({ tl: Math.round(tl * 1000) / 1000, src: p });
    }
  }
  const seen = new Set();
  return out
    .filter((x) => (seen.has(x.tl) ? false : seen.add(x.tl)))
    .sort((a, b) => a.tl - b.tl);
}

/**
 * How the keep-ranges relate to what the timeline plays: the merged source windows of the clips, and how many ranges touch one of
 * them (inside) or none (outside, which a cut ignores). Used for the pre-flight line and the button counts.
 */
function coverage(ranges, clips) {
  const wins = (clips || []).map((c) => ({ start: c.inPoint, end: c.outPoint })).filter((w) => w.end > w.start).sort((a, b) => a.start - b.start);
  const windows = [];
  for (const w of wins) {
    const last = windows[windows.length - 1];
    if (last && w.start <= last.end + 0.001) last.end = Math.max(last.end, w.end);
    else windows.push({ start: w.start, end: w.end });
  }
  let inside = 0;
  for (const r of ranges || []) if (windows.some((w) => Math.min(w.end, r.end) - Math.max(w.start, r.start) > 0.001)) inside++;
  return { windows, inside, outside: (ranges || []).length - inside };
}

/** Does this markers file belong to this video? ("<video>.markers.json", or a name that starts like the video's, or the other way round.) */
function markersNameMatchesMedia(markersName, mediaPath) {
  const lower = (x) => String(x || "").toLowerCase();
  const n = lower(markersName);
  if (!n.endsWith(MARKERS_SUFFIX)) return false;
  const stem = lower(stripExtension(baseName(mediaPath)));
  const mstem = n.slice(0, -MARKERS_SUFFIX.length);
  if (!stem || !mstem) return false;
  return mstem === stem || mstem.startsWith(stem) || (mstem.length > 3 && stem.startsWith(mstem));
}

const LT_CORE_API = {
  FORMAT,
  SUPPORTED_VERSION,
  COLORS,
  DEFAULT_SETTINGS,
  MarkersFileError,
  parseMarkersFile,
  normalizeSettings,
  colorForClip,
  planMarkers,
  formatTime,
  colorName,
  summarizeSettings,
  MARKERS_SUFFIX,
  baseName,
  dirName,
  stripExtension,
  fileUrlForms,
  pickMarkersFile,
  planCuts,
  cutsForClip,
  cutPoints,
  planCutSet,
  timelinePoints,
  coverage,
  markersNameMatchesMedia,
};
if (typeof module !== "undefined" && module.exports) module.exports = LT_CORE_API;
if (typeof window !== "undefined") window.LTCore = LT_CORE_API;
