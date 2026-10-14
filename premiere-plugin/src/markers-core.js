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
};
if (typeof module !== "undefined" && module.exports) module.exports = LT_CORE_API;
if (typeof window !== "undefined") window.LTCore = LT_CORE_API;
