"use strict";
try {
/* The panel: finds/loads the marker file, keeps the settings, and the Add button. Logic is in markers-core.js, Premiere calls in premiere-adapter.js. */

const core = window.LTCore || require("./markers-core.js");
// The Premiere adapter is loaded only when needed, so a problem there can never stop the panel (and the file picker) from starting.
let adapterModule = null;
function getAdapter() {
  if (!adapterModule) adapterModule = window.LTAdapter || require("./premiere-adapter.js");
  return adapterModule;
}

const $ = (id) => document.getElementById(id);
const STORE_KEY = "luckytwitch-markers-settings-v1";

try {
  require("uxp").entrypoints.setup({ panels: { luckytwitchMarkers: { show() { onPanelShow(); } } } });
} catch (e) {
  /* older hosts do not need / have this */
}

let loaded = null; // the checked file: {file, label, text, path, auto, mediaPath}
let timeline = null; // what the timeline plays of the file's video: {descs, mediaName, ...}, or null when unknown
let timelineNote = ""; // why it is unknown

function setStatus(text, kind) {
  const el = $("status");
  if (!el) return;
  el.textContent = text;
  el.className = kind || "muted";
}

function toggleSection(bodyId, buttonId, label, open) {
  const show = open === undefined ? $(bodyId).style.display === "none" : open;
  $(bodyId).style.display = show ? "block" : "none";
  $(buttonId).textContent = (show ? "▾ " : "▸ ") + label;
}
const openTroubleshooting = (open) => toggleSection("troubleBody", "toggleTrouble", "Troubleshooting", open);

/** Writes to the log (Troubleshooting) and shows the latest message in the status line under the Add button. */
function log(text, isError = false, quiet = false) {
  window.__ltLog(text, isError);
  if (quiet) return;
  if (isError) {
    setStatus(text, "err");
    openTroubleshooting(true);
  } else {
    setStatus(text, /^Done/.test(text) ? "ok" : "muted");
  }
}

async function copyLog() {
  const text = $("log").value;
  const say = (m) => ($("copyState").textContent = m);
  if (!text) return say("The log is empty.");
  try {
    await navigator.clipboard.writeText(text);
    return say("Copied.");
  } catch (e) {
    /* clipboard not available: fall back to selecting the text */
  }
  try {
    $("log").focus();
    $("log").select();
    say("Could not copy by itself. The log is selected: press Ctrl+C.");
  } catch (e) {
    say("Could not copy. Click in the log, press Ctrl+A, then Ctrl+C.");
  }
}

// ---- settings -------------------------------------------------------------------------------------------
const COLOR_FIELDS = ["gameColor", "lowColor", "midColor", "highColor", "clipColor"];
const NUMBER_FIELDS = ["minViews", "midViews", "highViews", "padBefore", "padAfter", "mergeGap"];
const CHECK_FIELDS = ["importGames", "gamePrefix", "importClips", "colorByViews", "backup"];
const SELECT_FIELDS = ["offsetMode", "placement"];

function fillColorMenus() {
  const html = core.COLORS.map((c) => `<option value="${c.index}">${c.name}</option>`).join("");
  for (const id of COLOR_FIELDS) $(id).innerHTML = html;
}

// Approximate looks of Premiere's eight marker colors, for the little dots next to the menus.
const COLOR_HEX = ["#3fbf5f", "#e5484d", "#9b5de5", "#f5922f", "#f2d03b", "#f5f5f5", "#3b82f6", "#22c5d8"];

function colorHex(index) {
  return COLOR_HEX[Number(index)] || "#888888";
}

function updateDots() {
  for (const id of COLOR_FIELDS) $(id + "Dot").style.backgroundColor = colorHex($(id).value);
}

/** Shows only the controls that matter for the current choices. */
function refreshVisibility() {
  const games = $("importGames").checked;
  const clips = $("importClips").checked;
  const byViews = $("colorByViews").checked;
  const show = (id, on, display = "block") => ($(id).style.display = on ? display : "none");
  show("gameColorCtl", games, "flex");
  show("gamePrefixRow", games, "flex");
  show("clipOptions", clips);
  show("tierRows", clips && byViews);
  show("singleColorRow", clips && !byViews, "flex");
  show("offsetRow", $("placement").value === "sequence", "flex");
  $("placeHint").textContent =
    $("placement").value === "sequence"
      ? "Markers go on the active sequence, at fixed times."
      : "Markers go on the selected clip (else the first video clip) and follow your cuts.";
}

function loadSettings() {
  let raw = null;
  try {
    raw = JSON.parse(localStorage.getItem(STORE_KEY));
  } catch (e) {
    /* first run or unreadable: use the defaults */
  }
  return core.normalizeSettings(raw);
}

function showSettings(s) {
  for (const id of COLOR_FIELDS) $(id).value = String(s[id]);
  for (const id of NUMBER_FIELDS) $(id).value = String(s[id]);
  for (const id of CHECK_FIELDS) $(id).checked = !!s[id];
  for (const id of SELECT_FIELDS) $(id).value = s[id];
  updateDots();
  refreshVisibility();
  updateSettingsSummary();
}

function readSettings() {
  const raw = {};
  for (const id of SELECT_FIELDS) raw[id] = $(id).value;
  for (const id of COLOR_FIELDS) raw[id] = Number($(id).value);
  for (const id of NUMBER_FIELDS) raw[id] = $(id).value.trim();
  for (const id of CHECK_FIELDS) raw[id] = $(id).checked;
  return core.normalizeSettings(raw);
}

function updateSettingsSummary() {
  $("settingsSummary").textContent = core.summarizeSettings(readSettings());
}

function saveSettings() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(readSettings()));
  } catch (e) {
    /* storage can be unavailable; the settings just won't be remembered */
  }
  updateDots();
  refreshVisibility();
  updateSettingsSummary();
  updateSummary();
}

// ---- file and summary -----------------------------------------------------------------------------------
/** The video this file belongs to, so cutting finds every timeline clip of it (not just the selected / first one). */
const hint = () => (loaded ? { mediaPath: loaded.mediaPath, fileName: /\.markers\.json$/i.test(loaded.label) ? loaded.label : undefined } : undefined);
const planOpts = (s) => ({ padBefore: s.padBefore, padAfter: s.padAfter, mergeGap: s.mergeGap });
/** Every clip and game of the file, whatever the marker settings hide: what a cut works from. */
const cutItems = () => (loaded ? core.planMarkers(loaded.file, { ...readSettings(), importGames: true, importClips: true }).items : null);

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

/** Buttons, counts and the timeline line. Does not touch the status line (so a "Done" message stays). */
function renderCounts() {
  if (!loaded) return;
  const settings = readSettings();
  const { items, counts } = core.planMarkers(loaded.file, settings);
  const f = loaded.file;
  const all = cutItems();
  const clipSet = core.planCutSet(all, { ...planOpts(settings), clips: true });
  const chapSet = core.planCutSet(all, { clips: false, chapters: true });
  const clipCov = timeline ? core.coverage(clipSet.ranges, timeline.descs) : null;
  const chapCov = timeline ? core.coverage(chapSet.chapters, timeline.descs) : null;
  const nClips = clipCov ? clipCov.inside : clipSet.ranges.length;
  const nChaps = chapCov ? chapCov.inside : chapSet.chapters.length;

  $("fileEmpty").style.display = "none";
  $("fileLine").style.display = "flex";
  const nGames = f.markers.filter((m) => m.kind === "game").length;
  const nClipMarkers = f.markers.filter((m) => m.kind === "clip").length;
  $("fileSummary").textContent = `${loaded.label} · ${plural(nGames, "game", "games")} · ${plural(nClipMarkers, "clip", "clips")}`;
  $("fileName").textContent = loaded.label;
  $("fileFound").textContent = loaded.found || "";
  $("fileTitle").textContent = f.source && f.source.streamer ? `${f.source.streamer} · ${f.source.title || ""}`.trim() : "";
  $("filePart").textContent = f.part ? `Part ${core.formatTime(f.part.start)} – ${core.formatTime(f.part.end)} of the VOD` : "";
  const notes = [];
  if (counts.hidden) notes.push(`${counts.hidden} left out by your marker settings.`);
  if (f.skipped) notes.push(`${f.skipped} entries in the file were not understood and are skipped.`);
  $("fileNote").textContent = notes.join(" ");

  $("add").disabled = items.length === 0;
  $("add").textContent = items.length ? `Add ${items.length} markers` : "Add markers";
  $("remove").disabled = false;
  $("cutClips").disabled = nClips === 0;
  $("cutClips").textContent = clipCov && clipCov.outside ? `Cut at ${nClips} of ${clipSet.ranges.length} clips` : nClips ? `Cut at ${plural(nClips, "clip", "clips")}` : "Cut at clips";
  $("cutChapters").disabled = nChaps === 0;
  $("cutChapters").textContent = chapCov && chapCov.outside ? `Cut at ${nChaps} of ${chapSet.chapters.length} chapters` : nChaps ? `Cut at ${plural(nChaps, "chapter", "chapters")}` : "Cut at chapters";
  $("pickRow").style.display = "none";
  $("pick2").style.display = "inline-block";

  const info = $("timelineInfo");
  if (timeline) {
    const w = clipCov.windows.map((x) => `${core.formatTime(x.start)}–${core.formatTime(x.end)}`).join(", ");
    const lines = [`Timeline: ${plural(timeline.descs.length, "clip", "clips")} of ${timeline.mediaName || "the video"} on V${timeline.trackIndex + 1}, playing ${w || "nothing"}.`];
    if (clipCov.outside) lines.push(`${clipCov.outside === 1 ? "1 clip of the file falls" : `${clipCov.outside} clips of the file fall`} outside what the timeline plays and ${clipCov.outside === 1 ? "is" : "are"} ignored.`);
    if (timeline.elsewhere) lines.push(`${plural(timeline.elsewhere, "more clip", "more clips")} of this video on higher tracks are ignored.`);
    if (timeline.reversed) lines.push(`${plural(timeline.reversed, "reversed clip", "reversed clips")} ignored.`);
    info.textContent = lines.join(" ");
    info.className = "hint tl-info" + (timeline.elsewhere || timeline.reversed ? " tl-warn" : "");
  } else {
    info.textContent = timelineNote || "";
    info.className = "hint tl-info";
  }
}

function updateSummary() {
  if (!loaded) return;
  renderCounts();
  const n = core.planMarkers(loaded.file, readSettings()).items.length;
  setStatus(n ? "Ready." : "Nothing to add with these settings.", n ? "muted" : "err");
}

let refreshing = false;
/** Looks at the timeline (read-only) so the buttons can say how many clips / chapters fall inside what it plays. Never shows an error. */
async function refreshTimeline() {
  if (!loaded || busy || refreshing) return;
  refreshing = true;
  try {
    timeline = await getAdapter().inspectTimeline(hint());
    timelineNote = "";
  } catch (e) {
    timeline = null;
    timelineNote = e && e.message ? e.message : String(e);
  } finally {
    refreshing = false;
  }
  renderCounts();
}

function useFileText(text, label, meta) {
  const file = core.parseMarkersFile(text);
  loaded = { file, label, text, path: meta && meta.path, auto: !!(meta && meta.auto), found: meta && meta.found, mediaPath: meta && meta.mediaPath };
  timeline = null;
  timelineNote = "";
  updateSummary();
}

function failLoad(e) {
  loaded = null;
  timeline = null;
  $("add").disabled = true;
  $("remove").disabled = true;
  $("cutClips").disabled = true;
  $("cutChapters").disabled = true;
  $("add").textContent = "Add markers";
  $("cutClips").textContent = "Cut at clips";
  $("cutChapters").textContent = "Cut at chapters";
  $("timelineInfo").textContent = "";
  $("pickRow").style.display = "flex";
  $("pick2").style.display = "none";
  $("fileEmpty").style.display = "block";
  $("fileLine").style.display = "none";
  $("fileDetails").style.display = "none";
  log(e && e.message ? e.message : String(e), true);
}

async function pickFile() {
  log("Opening the file picker…", false, true);
  try {
    const fs = require("uxp").storage.localFileSystem;
    let entry;
    try {
      entry = await fs.getFileForOpening({ types: ["json"] });
    } catch (e) {
      log(`The picker with a .json filter failed (${e && e.message ? e.message : e}); trying without a filter.`, false, true);
      entry = await fs.getFileForOpening();
    }
    if (!entry) return log("No file picked.", false, true); // cancelled
    useFileText(await entry.read(), entry.name, { auto: false, path: entry.nativePath, found: "Chosen by hand." });
  } catch (e) {
    failLoad(e);
    log("If the picker will not open on your Premiere, open the .markers.json in Notepad, copy everything, paste it in the box below and press «Use pasted text».", true);
  }
}

function usePasted() {
  const text = $("pasted").value.trim();
  if (!text) return log("Paste the contents of the .markers.json first.", true);
  try {
    useFileText(text, "(pasted text)", { auto: false, found: "Pasted by hand." });
  } catch (e) {
    failLoad(e);
  }
}

// ---- finding the file by itself --------------------------------------------------------------------------
let detecting = false;
let detectedOnce = false;

/**
 * Looks for the .markers.json next to the target clip's video (then next to the Premiere project).
 * manual = the user pressed "Search again": it may replace a file that was chosen by hand and it reports "not found".
 */
async function autoDetect(manual) {
  if (detecting || busy) return;
  if (loaded && !loaded.auto && !manual) return; // a file chosen by hand stays until the user says otherwise
  detecting = true;
  const why = [];
  try {
    const found = await getAdapter().findMarkersFile(why);
    if (found) {
      if (loaded && loaded.auto && loaded.path === found.path && loaded.text === found.text) return;
      useFileText(found.text, found.name, { auto: true, path: found.path, mediaPath: found.mediaPath, found: `Found ${found.where} (${found.how}).` });
      log(`Found the markers file ${found.where}: ${found.name} (${found.how}).`, false, true);
      refreshTimeline();
    } else if (manual || !detectedOnce) {
      why.forEach((w) => window.__ltLog(`(detect) ${w}`));
      if (!loaded) {
        $("fileEmpty").textContent = "No .markers.json found next to the video or the project. Put the video on the timeline (select it) and press Search again, or choose the file by hand.";
        setStatus("Choose a file to begin.", "muted");
      } else if (manual) {
        setStatus("Nothing found automatically; keeping the file you have.", "muted");
      }
    }
  } catch (e) {
    if (manual) log(`Search failed: ${e && e.message ? e.message : e}`, true);
    else window.__ltLog(`(detect) stopped: ${e && e.message ? e.message : e}`);
  } finally {
    detectedOnce = true;
    detecting = false;
  }
}

let lastShow = 0;
function onPanelShow() {
  const now = Date.now();
  if (now - lastShow < 2000) return;
  lastShow = now;
  autoDetect(false).then(() => refreshTimeline());
}

// ---- actions --------------------------------------------------------------------------------------------
let busy = false;
async function guarded(fn) {
  if (busy) return;
  busy = true;
  try {
    await fn();
  } catch (e) {
    log(e.message || String(e), true);
  } finally {
    busy = false;
  }
  refreshTimeline();
}

async function doAdd() {
  if (!loaded) return;
  const settings = readSettings();
  const { items } = core.planMarkers(loaded.file, settings);
  if (!items.length) return log("Nothing to add with these settings.", true);
  const r = await getAdapter().addMarkers(items, { placement: settings.placement, offsetMode: settings.offsetMode }, log);
  const follow = settings.placement === "clip" ? " They follow your cuts." : "";
  if (r.added === 0) log(`Done: nothing new, all ${r.skipped} markers were already on ${r.what} (colors refreshed).`);
  else log(`Done: ${r.added} markers added to ${r.what}${r.skipped ? ` (${r.skipped} were already there)` : ""}.${follow}`);
}

async function doRemove() {
  if (!loaded) return;
  const settings = readSettings();
  // Every marker this file could have produced, whatever the settings were when it was added (with and without the GAME: prefix).
  const all = [];
  for (const gamePrefix of [false, true]) {
    all.push(...core.planMarkers(loaded.file, { ...settings, importGames: true, importClips: true, minViews: 0, gamePrefix }).items);
  }
  const r = await getAdapter().removeMarkers(all, { placement: settings.placement, offsetMode: settings.offsetMode }, log);
  if (r.removed) log(`Done: ${r.removed} markers removed from ${r.what}.`);
  else log(`Nothing to remove: none of this file's markers are on ${r.what}.`);
}

/** kind: "clips" = the start and end of every clip; "chapters" = every game / category boundary. */
async function doCut(kind) {
  if (!loaded) return;
  const settings = readSettings();
  const clips = kind === "clips";
  const r = await getAdapter().cutAtClipEdges(
    cutItems(),
    { backup: settings.backup, clips, chapters: !clips, plan: planOpts(settings), hint: hint() },
    log
  );
  if (!r.cuts && !r.points) return log(`Nothing to cut: every ${clips ? "clip" : "chapter"} edge is already a cut, or falls outside what the timeline plays.`, true);
  log(`Done: ${r.cuts} cuts made in ${plural(r.clips, "clip", "clips")}${r.skipped ? ` (${r.skipped} points already had a cut)` : ""}. Look at the timeline.`);
}

const plannedItems = () => cutItems();

function init() {
  // Buttons first: whatever fails after this, they still react.
  const on = (id, fn) => $(id) && $(id).addEventListener("click", () => guarded(fn));
  on("pick", pickFile);
  on("pick2", pickFile);
  on("detect", () => autoDetect(true));
  on("usePasted", usePasted);
  on("add", doAdd);
  on("cutClips", () => doCut("clips"));
  on("cutChapters", () => doCut("chapters"));
  on("remove", doRemove);
  on("copyLog", copyLog);
  $("toggleTrouble") && $("toggleTrouble").addEventListener("click", () => openTroubleshooting());
  $("toggleFile") && $("toggleFile").addEventListener("click", () => toggleSection("fileDetails", "toggleFile", "details"));
  $("toggleSettings") && $("toggleSettings").addEventListener("click", () => toggleSection("settingsBody", "toggleSettings", "Settings"));
  $("clearLog") && $("clearLog").addEventListener("click", () => { $("log").value = ""; $("copyState").textContent = ""; });
  // Probes and experiments: their messages go to the log only, not to the status line under the Add button.
  const dlog = (text, isError) => log(text, !!isError, !isError);
  on("probe", () => getAdapter().probe(dlog));
  on("probeClips", () => getAdapter().probeClips(dlog));
  on("probeAudio", () => getAdapter().probeAudio(dlog));
  on("probeEditor", () => getAdapter().probeEditor(dlog));
  on("probeClasses", () => getAdapter().probeClasses(dlog));
  on("probeDetect", () => getAdapter().probeDetection(dlog));
  on("probeCutPlan", async () => {
    const items = plannedItems();
    if (!items || !items.length) return dlog("Cut plan needs a loaded markers file with clips (nothing to plan yet).", true);
    const st = readSettings();
    await getAdapter().probeCutPlan(items, dlog, planOpts(st), hint());
  });
  on("probeAll", () => getAdapter().probeAll(dlog, plannedItems, hint));
  on("testMarkers", () => getAdapter().addTestMarkers(core.COLORS, dlog));
  on("testClipMarkers", () => getAdapter().addClipTestMarkers(core.COLORS, dlog));
  on("testCut", () => getAdapter().testCutAtPlayhead(dlog));
  on("testSplit", () => getAdapter().testSplitAtPlayhead(dlog));
  try {
    fillColorMenus();
    showSettings(loadSettings());
    for (const id of [...COLOR_FIELDS, ...NUMBER_FIELDS, ...CHECK_FIELDS, ...SELECT_FIELDS]) {
      $(id).addEventListener("change", saveSettings);
    }
  } catch (e) {
    log(`Could not set up the settings: ${e && e.message ? e.message : e}`, true);
  }
  log(`Panel ready (0.5.0). Core: ${core ? "ok" : "missing"}.`, false, true);
  // Look for the marker file now, again when the panel is shown / focused, and every few seconds until one is loaded
  // (so it also works when the video is put on the timeline after the panel was opened).
  setTimeout(() => autoDetect(false), 400);
  window.addEventListener("focus", onPanelShow);
  setInterval(() => {
    if (!loaded && !busy) autoDetect(false);
  }, 4000);
}

window.addEventListener("error", (ev) => log(`Error: ${ev.message || ev}`, true));
window.addEventListener("unhandledrejection", (ev) => log(`Error: ${ev.reason && ev.reason.message ? ev.reason.message : ev.reason}`, true));

if (document.readyState === "loading") window.addEventListener("DOMContentLoaded", init);
else init();
} catch (e) {
  if (window.__ltLog) window.__ltLog("main.js failed to start: " + (e && e.stack ? e.stack : e), true);
}
