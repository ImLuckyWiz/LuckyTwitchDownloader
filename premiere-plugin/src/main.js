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
let limitIdx = null; // "Only in chapter": index into core.chapterList(file), null = the whole file (not saved: it belongs to the file)
let lastPre = null; // the latest pre-flight result (core.evaluatePreflight), or null when unknown
let running = false; // a cut / Do it all is in progress (buttons are locked, Stop is shown)
let stopRequested = false;
let stopNoun = "round"; // what Stop finishes: a cutting round or a delete batch
let lastFacts = null; // the facts of the latest pre-flight (buildFacts), for the Do it all label and its delete preview
let armed = null; // 0.7.0: {kind: "gaps" | "doAll", key, until}: the first click of a delete shows the preview, the second one (same preview) runs it
const ARM_MS = 30000;
let autoRanKey = ""; // the file the opt-in auto-run already handled (once per detected file)
let autoWhyKey = ""; // the last "auto-run skipped" reason that was logged, so it is not repeated

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
const NUMBER_FIELDS = ["minViews", "midViews", "highViews", "padBefore", "padAfter", "mergeGap", "minClips", "maxDeletePct", "minKeepPieces"];
const CHECK_FIELDS = ["importGames", "gamePrefix", "importClips", "colorByViews", "backup", "recipeMarkers", "recipeCutClips", "recipeCutChapters", "recipeDeleteGaps", "autoRun"];
const SELECT_FIELDS = ["placement"];

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
  $("placeHint").textContent =
    $("placement").value === "sequence"
      ? "Markers go on the active sequence, each where the clip that plays it has it (the video must be on the timeline)."
      : "Markers go on the video's clip (selected in the Project panel, else on the timeline) and follow your cuts.";
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
  disarm(); // any change of a setting cancels a pending delete confirmation
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
/** "Only in chapter": {min, max, name} or null. */
const scope = () => (loaded ? core.chapterScope(loaded.file, limitIdx) : null);
/** Padding / merge gap, and the chapter range when one is chosen (planCutSet clamps to min / max). */
const planOpts = (s) => {
  const sc = scope();
  return { padBefore: s.padBefore, padAfter: s.padAfter, mergeGap: s.mergeGap, ...(sc ? { min: sc.min, max: sc.max } : {}) };
};
const isArmed = (kind, key) => !!armed && armed.kind === kind && armed.key === key && Date.now() < armed.until;
const arm = (kind, key) => { armed = { kind, key, until: Date.now() + ARM_MS }; };
function disarm() { armed = null; }

/** The delete plan for these pieces with the current settings (the keep ranges are the clips, padded and merged like the cut did). */
function gapPlan(pieces, frame, audioUnmatched) {
  const st = readSettings();
  const set = core.planCutSet(cutItems(), { ...planOpts(st), clips: true, chapters: false });
  return core.planGapDelete(pieces, set.ranges, { frame, scope: scope(), maxDeletePct: st.maxDeletePct, minKeep: st.minKeepPieces, audioUnmatched: audioUnmatched || 0 });
}
/** What the adapter's deleteGaps / probeGapPlan need besides the items. */
const gapArgs = (st) => ({ plan: planOpts(st), scope: scope(), hint: hint(), maxDeletePct: st.maxDeletePct, minKeep: st.minKeepPieces });

/** Every clip and game of the file, whatever the marker settings hide: what a cut works from. */
const cutItems = () => (loaded ? core.planMarkers(loaded.file, { ...readSettings(), importGames: true, importClips: true }).items : null);
/** The markers Add / Do it all would put on: the marker settings, limited to the chosen chapter. */
const markerItems = () => (loaded ? core.restrictItems(core.planMarkers(loaded.file, readSettings()).items, scope()) : []);
const markerOpts = (s) => ({ placement: s.placement, hint: hint() });

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

/** The "Only in chapter" menu: whole file + the file's chapters. Hidden when the file has none. */
function fillChapterMenu() {
  const list = loaded ? core.chapterList(loaded.file) : [];
  const opts = ['<option value="">Whole file</option>'].concat(
    list.map((c) => `<option value="${c.index}">${c.index + 1}. ${String(c.name).replace(/[<>&"]/g, "")} (${core.formatTime(c.start)}–${core.formatTime(c.end)})</option>`)
  );
  $("limitChapter").innerHTML = opts.join("");
  $("limitChapter").value = limitIdx === null ? "" : String(limitIdx);
  $("limitRow").style.display = list.length ? "block" : "none";
}

/**
 * The facts the pre-flight needs, from what is loaded, the settings and what Premiere reported (tl = inspectTimeline result or null,
 * mk = checkMarkers result or null). Pure bookkeeping: nothing here talks to Premiere.
 */
function buildFacts(tl, tlError, mk, mkError) {
  const st = readSettings();
  const all = cutItems();
  const plan = planOpts(st);
  const r = { markers: st.recipeMarkers, clips: st.recipeCutClips, chapters: st.recipeCutChapters, deleteGaps: st.recipeDeleteGaps };
  const clipSet = core.planCutSet(all, { ...plan, clips: true });
  const chapSet = core.planCutSet(all, { ...(plan.min === undefined ? {} : { min: plan.min, max: plan.max }), clips: false, chapters: true });
  const both = core.planCutSet(all, { ...plan, clips: r.clips, chapters: r.chapters });
  const pendingPoints = tl ? core.pendingCutPoints(both.points, tl.descs, tl.frame) : [];
  // 0.7.0: what the delete step would do. When the recipe cuts first, the pieces do not exist yet: work on the pieces the cut WILL make.
  let gaps = null;
  if (r.deleteGaps && tl) gaps = gapPlan(r.clips || r.chapters ? core.simulatePieces(tl.descs, pendingPoints) : tl.descs, tl.frame, tl.audioUnmatched || 0);
  return {
    gaps,
    loaded: !!loaded, recipe: r, minClips: st.minClips, markerCount: markerItems().length, markers: mk, markersError: mkError || "",
    timeline: tl, timelineError: tlError || "", workspace: tl ? tl.workspace : null,
    clipsInside: tl ? core.coverage(clipSet.ranges, tl.descs).inside : 0, clipsTotal: clipSet.ranges.length,
    chaptersInside: tl ? core.coverage(chapSet.chapters, tl.descs).inside : 0, chaptersTotal: chapSet.chapters.length,
    pending: pendingPoints.length, rounds: tl ? core.roundsFor(pendingPoints, tl.descs, tl.frame) : 0, backup: st.backup,
  };
}

/** Reads Premiere (read-only) and evaluates the pre-flight. `tl` may be passed when the timeline was just inspected. */
async function runPreflight(tl, tlError) {
  const st = readSettings();
  let mk = null, mkError = "";
  if (st.recipeMarkers && markerItems().length) {
    try {
      mk = await getAdapter().checkMarkers(markerItems(), markerOpts(st));
    } catch (e) {
      mkError = e && e.message ? e.message : String(e);
    }
  }
  lastFacts = buildFacts(tl, tlError, mk, mkError);
  return core.evaluatePreflight(lastFacts);
}

function showPreflight(pre) {
  const line = $("preSummary");
  if (!pre) {
    line.textContent = "";
    $("preLinks").style.display = "none";
    $("preChecks").style.display = "none";
    return;
  }
  line.textContent = pre.ok ? (pre.alreadyDone ? "Everything in the recipe is already done." : pre.summary ? `Will ${pre.summary}` : "") : `Not ready: ${pre.problems[0]}`;
  line.className = "hint pre-line" + (pre.ok ? "" : " bad");
  $("preChecks").textContent = pre.checks.map((c) => `${c.ok ? "✓" : "✗"} ${c.text}`).join("\n");
  $("preLinks").style.display = pre.checks.length ? "flex" : "none";
}

/** Buttons, counts and the timeline line. Does not touch the status line (so a "Done" message stays). */
function renderCounts() {
  if (!loaded) return;
  const settings = readSettings();
  const items = markerItems();
  const counts = core.planMarkers(loaded.file, settings).counts;
  const f = loaded.file;
  const all = cutItems();
  const sc = scope();
  const clipSet = core.planCutSet(all, { ...planOpts(settings), clips: true });
  const chapSet = core.planCutSet(all, { min: sc ? sc.min : 0, max: sc ? sc.max : Infinity, clips: false, chapters: true });
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

  $("add").disabled = items.length === 0 || running;
  $("add").textContent = items.length ? `Add ${items.length} markers` : "Add markers";
  $("remove").disabled = running;
  const steps = core.recipeSteps(settings);
  $("doAll").disabled = !steps.length || running;
  const rg = lastFacts && lastFacts.gaps && lastFacts.gaps.ok ? lastFacts.gaps : null;
  if (armed && armed.kind === "doAll" && !(rg && core.gapKey(rg) === armed.key && Date.now() < armed.until)) disarm();
  const label = core.recipeLabel(settings, { markers: items.length, clips: nClips, chapters: nChaps, gaps: rg ? rg.deleteCount : undefined });
  $("doAll").textContent = armed && armed.kind === "doAll" ? `Click again to confirm: ${label}` : label;

  // the red button: classification of the pieces on the timeline right now (pure: it only needs what the last look at the timeline read)
  const gp = timeline ? gapPlan(timeline.descs, timeline.frame, timeline.audioUnmatched || 0) : null;
  if (armed && armed.kind === "gaps" && !(gp && gp.ok && core.gapKey(gp) === armed.key && Date.now() < armed.until)) disarm();
  const dg = $("deleteGaps");
  if (!gp) {
    dg.disabled = true;
    dg.textContent = "Delete the gaps";
    $("gapPreview").textContent = "";
  } else if (!gp.ok) {
    dg.disabled = true;
    dg.textContent = "Delete the gaps";
    $("gapPreview").textContent = gp.problems[0];
  } else if (gp.nothing) {
    dg.disabled = true;
    dg.textContent = "Delete the gaps (none left)";
    $("gapPreview").textContent = "No gap piece is left: every piece of the timeline is a clip.";
  } else {
    dg.disabled = running;
    dg.textContent = armed && armed.kind === "gaps" ? `Click again to delete ${plural(gp.deleteCount, "piece", "pieces")}` : `Delete the gaps: ${plural(gp.deleteCount, "piece", "pieces")}`;
    $("gapPreview").textContent = `Will delete ${gp.text}${settings.backup ? ", after one backup." : ". NO backup: the box is off in Settings."}`;
  }
  $("cutClips").disabled = nClips === 0 || running;
  $("cutClips").textContent = clipCov && clipCov.outside ? `Cut at ${nClips} of ${clipSet.ranges.length} clips` : nClips ? `Cut at ${plural(nClips, "clip", "clips")}` : "Cut at clips";
  $("cutChapters").disabled = nChaps === 0 || running;
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
  const n = markerItems().length;
  setStatus(n ? "Ready." : "Nothing to add with these settings.", n ? "muted" : "err");
}

let refreshing = false;
/**
 * Looks at the timeline (read-only) so the buttons can say how many clips / chapters fall inside what it plays, and re-runs the pre-flight
 * for the Do it all line. Never shows an error. At the end it offers the opt-in auto-run its chance.
 */
async function refreshTimeline() {
  if (!loaded || busy || refreshing) return;
  refreshing = true;
  let tlError = "";
  try {
    timeline = await getAdapter().inspectTimeline(hint());
    timelineNote = "";
  } catch (e) {
    timeline = null;
    timelineNote = e && e.message ? e.message : String(e);
    tlError = timelineNote;
  }
  try {
    lastPre = await runPreflight(timeline, tlError);
  } catch (e) {
    lastPre = null;
  } finally {
    refreshing = false;
  }
  renderCounts();
  showPreflight(lastPre);
  await maybeAutoRun();
}

function useFileText(text, label, meta) {
  const file = core.parseMarkersFile(text);
  disarm();
  lastFacts = null;
  loaded = { file, label, text, path: meta && meta.path, auto: !!(meta && meta.auto), found: meta && meta.found, mediaPath: meta && meta.mediaPath };
  timeline = null;
  timelineNote = "";
  lastPre = null;
  limitIdx = null;
  fillChapterMenu();
  showPreflight(null);
  updateSummary();
}

function failLoad(e) {
  loaded = null;
  timeline = null;
  $("add").disabled = true;
  $("remove").disabled = true;
  $("cutClips").disabled = true;
  $("cutChapters").disabled = true;
  $("doAll").disabled = true;
  $("doAll").textContent = "Do it all";
  $("deleteGaps").disabled = true;
  $("deleteGaps").textContent = "Delete the gaps";
  $("gapPreview").textContent = "";
  $("limitRow").style.display = "none";
  lastPre = null;
  showPreflight(null);
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
let lastDetectLog = ""; // the last "(detect) stopped" text: the 4-second poll must not repeat it

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
      lastDetectLog = "";
      detecting = false; // refreshTimeline may start the auto-run, which must not be blocked by this flag
      await refreshTimeline();
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
    const m = e && e.message ? e.message : String(e);
    if (/No project is open/i.test(m)) {
      // not an error: there is just nothing to look at yet. Say it in the panel, never in the log (the poll would repeat it every 4 s).
      if (!loaded) $("fileEmpty").textContent = "Open or create a project: the panel then looks for the .markers.json by itself.";
      if (manual) log("No project is open.", true);
    } else if (manual) log(`Search failed: ${m}`, true);
    else if (m !== lastDetectLog) {
      lastDetectLog = m;
      window.__ltLog(`(detect) stopped: ${m}`);
    }
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
  const items = markerItems();
  if (!items.length) return log("Nothing to add with these settings.", true);
  const r = await getAdapter().addMarkers(items, markerOpts(settings), log);
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
  const r = await getAdapter().removeMarkers(all, markerOpts(settings), log);
  if (r.removed) log(`Done: ${r.removed} markers removed from ${r.what}.`);
  else log(`Nothing to remove: none of this file's markers are on ${r.what}.`);
}

// ---- progress and Stop ----------------------------------------------------------------------------------
function setStopNoun(noun) {
  stopNoun = noun;
  if (!stopRequested) $("stop").textContent = `Stop after this ${noun}`;
}

function setRunning(on, noun) {
  running = on;
  stopRequested = false;
  stopNoun = noun || "round";
  $("runBox").style.display = on ? "block" : "none";
  $("stop").disabled = false;
  $("stop").textContent = `Stop after this ${stopNoun}`;
  $("progressText").textContent = "";
  $("progressFill").style.width = "0%";
  $("limitChapter").disabled = on;
  renderCounts();
}

/** p = {step, steps, label, round, rounds, done, total} */
function showProgress(p) {
  $("progressText").textContent = core.progressText(p);
  $("progressFill").style.width = p.total ? `${Math.min(100, Math.round((100 * p.done) / p.total))}%` : "0%";
}

function onStop() {
  if (!running || stopRequested) return;
  stopRequested = true;
  $("stop").disabled = true;
  $("stop").textContent = `Stopping after this ${stopNoun}…`;
  window.__ltLog(`Stop requested: the current ${stopNoun} will be finished.`);
}

/** What a cut run needs from the panel: progress display and the Stop check. */
const cutHooks = (extra) => ({ onProgress: (e) => showProgress({ ...extra, ...e }), shouldStop: () => stopRequested });
/** The same for the delete: its rounds are batches of gap pieces. */
const deleteHooks = (extra) => ({ onProgress: (e) => showProgress({ ...extra, unit: "gap pieces", roundLabel: "batch", ...e }), shouldStop: () => stopRequested });

/** kind: "clips" = the start and end of every clip; "chapters" = every game / category boundary. */
async function doCut(kind) {
  if (!loaded) return;
  const settings = readSettings();
  const clips = kind === "clips";
  setRunning(true);
  let r;
  try {
    r = await getAdapter().cutAtClipEdges(
      cutItems(),
      { backup: settings.backup, clips, chapters: !clips, plan: planOpts(settings), hint: hint(), ...cutHooks({ label: "cutting" }) },
      log
    );
  } finally {
    setRunning(false);
  }
  if (r.stopped) return log(`Stopped on request after round ${r.rounds}: ${r.cuts} of ${r.points} cuts are made. Run it again to finish; points that already have a cut are skipped.`);
  if (!r.cuts && !r.points) return log(`Nothing to cut: every ${clips ? "clip" : "chapter"} edge is already a cut, or falls outside what the timeline plays.`, true);
  log(`Done: ${r.cuts} cuts made in ${plural(r.clips, "clip", "clips")}${r.skipped ? ` (${r.skipped} points already had a cut)` : ""}. Look at the timeline.`);
}

// ---- Delete the gaps (the red button) ---------------------------------------------------------------------
/**
 * First click: reads the timeline fresh, shows what would be deleted, and arms the button (nothing is changed). Second click, with the same
 * preview: runs. The run re-checks everything and refuses if the timeline no longer matches the preview.
 */
async function doDeleteGaps() {
  if (!loaded) return;
  const settings = readSettings();
  let tl;
  try {
    tl = await getAdapter().inspectTimeline(hint());
  } catch (e) {
    return log(`Nothing was changed. ${e && e.message ? e.message : e}`, true);
  }
  timeline = tl;
  timelineNote = "";
  const plan = gapPlan(tl.descs, tl.frame, tl.audioUnmatched || 0);
  renderCounts();
  if (!plan.ok) return log(`Nothing was changed. ${plan.problems.join(" ")}`, true);
  if (plan.nothing) return log("Done: no gap piece is left, every piece of the timeline is a clip.");
  const key = core.gapKey(plan);
  if (!isArmed("gaps", key)) {
    arm("gaps", key);
    renderCounts();
    return log(`Will delete ${plan.text}. Click the red button again to confirm${settings.backup ? " (one backup of the sequence first)" : " (NO backup: the box is off in Settings)"}.`);
  }
  disarm();
  setRunning(true, "batch");
  let r;
  try {
    r = await getAdapter().deleteGaps(cutItems(), { ...gapArgs(settings), backup: settings.backup, expect: { deleteCount: plan.deleteCount, keepCount: plan.keepCount }, ...deleteHooks({ label: "deleting gaps" }) }, log);
  } finally {
    setRunning(false);
  }
  if (r.stopped) return log(`Stopped on request after batch ${r.rounds}: ${r.deleted} of ${r.total} gap pieces are deleted. Press the red button again to finish: it shows what is left and asks you to confirm again.`);
  const holeNote = r.holes ? ` Premiere's ripple left ${plural(r.holes, "hole", "holes")} of up to one frame (${(r.holeSeconds * 1000).toFixed(0)} ms in all); each was closed by lengthening the clip in front of it, so a clip can end up to one frame longer at its end.` : "";
  log(`Done: ${plural(r.deleted, "gap piece", "gap pieces")} deleted (${core.fmtSeconds(r.deletedSeconds)}). ${plural(r.keepPieces, "clip", "clips")} left back to back (${core.fmtSeconds(r.keepSeconds)}).${holeNote} Look at the timeline.`);
}

// ---- Do it all ------------------------------------------------------------------------------------------
/**
 * The saved recipe, in one go: pre-flight (fresh reads, nothing touched until it passes), one backup, then the ticked steps in order,
 * stopping at the first failure or when Stop is pressed, and saying what is done and what is left.
 */
async function doItAll() {
  if (!loaded) return;
  const settings = readSettings();
  const steps = core.recipeSteps(settings);
  setStatus("Checking before touching anything…", "muted");
  let tl = null, tlError = "";
  try {
    tl = await getAdapter().inspectTimeline(hint());
  } catch (e) {
    tlError = e && e.message ? e.message : String(e);
  }
  timeline = tl;
  timelineNote = tlError;
  const pre = await runPreflight(tl, tlError);
  lastPre = pre;
  renderCounts();
  showPreflight(pre);
  if (!pre.ok) return log(`Nothing was changed. ${pre.problems.join(" ")}`, true);
  if (pre.alreadyDone) return log("Done: everything in the recipe is already done, nothing to do.");

  // A recipe that deletes asks for confirmation BEFORE the run starts (so a run never stops to ask): the first press shows the preview, the second one runs.
  const g = lastFacts && lastFacts.gaps;
  if (settings.recipeDeleteGaps && g && g.ok && !g.nothing) {
    const key = core.gapKey(g);
    if (!isArmed("doAll", key)) {
      arm("doAll", key);
      renderCounts();
      return log(`This run will delete the gaps at the end: ${g.text}. Press Do it all again to confirm${settings.backup ? " (one backup of the sequence first)" : " (NO backup: the box is off in Settings)"}.`);
    }
  }
  disarm();
  const expect = settings.recipeDeleteGaps && g && g.ok ? { deleteCount: g.deleteCount, keepCount: g.keepCount } : undefined;

  const items = markerItems();
  const quiet = (text, isError) => log(text, isError, !isError); // the status line shows the progress, the details go to the log
  setRunning(true);
  let out;
  try {
    out = await core.runRecipe(steps, {
      backup: settings.backup ? () => getAdapter().backupSequence(quiet) : null,
      markers: () => getAdapter().addMarkers(items, markerOpts(settings), quiet),
      cut: () =>
        getAdapter().cutAtClipEdges(
          cutItems(),
          { backup: false, clips: settings.recipeCutClips, chapters: settings.recipeCutChapters, plan: planOpts(settings), hint: hint(), ...cutHooks(stepInfo) },
          quiet
        ),
      delete: () => getAdapter().deleteGaps(cutItems(), { ...gapArgs(settings), backup: false, expect, ...deleteHooks(stepInfo) }, quiet),
      shouldStop: () => stopRequested,
      onStep: (n, total, step) => {
        stepInfo = { step: n, steps: total, label: step.id === "markers" ? "adding markers" : step.id === "delete" ? "deleting gaps" : "cutting" };
        setStopNoun(step.id === "delete" ? "batch" : "round");
        showProgress(stepInfo);
      },
    });
  } finally {
    setRunning(false);
  }
  const text = core.outcomeText(out, steps);
  log(text, !!(out.failed || out.backupFailed));
}
let stepInfo = {};

// ---- the opt-in auto-run --------------------------------------------------------------------------------
/** Runs the recipe by itself, once per detected file, when the setting is on, the pre-flight passes and something is left to do. */
async function maybeAutoRun() {
  const s = readSettings();
  if (!s.autoRun || !loaded || !loaded.auto || busy || running) return;
  const key = `${loaded.path || loaded.label}|${loaded.text.length}`;
  const v = core.autoRunVerdict({ enabled: true, autoLoaded: true, key, ranKey: autoRanKey, pre: lastPre, deletes: s.recipeDeleteGaps });
  if (!v.run) {
    if (v.why && `${key}|${v.why}` !== autoWhyKey) {
      autoWhyKey = `${key}|${v.why}`;
      log(v.why);
    }
    return;
  }
  autoRanKey = key;
  log("Auto-run: running the recipe once for this file…", false, true);
  await guarded(doItAll);
}

const plannedItems = () => cutItems();

function init() {
  // Buttons first: whatever fails after this, they still react.
  const on = (id, fn) => $(id) && $(id).addEventListener("click", () => guarded(fn));
  on("pick", pickFile);
  on("pick2", pickFile);
  on("detect", () => autoDetect(true));
  on("usePasted", usePasted);
  on("doAll", doItAll);
  on("add", doAdd);
  on("cutClips", () => doCut("clips"));
  on("cutChapters", () => doCut("chapters"));
  on("deleteGaps", doDeleteGaps);
  on("remove", doRemove);
  on("copyLog", copyLog);
  $("stop") && $("stop").addEventListener("click", onStop); // not through guarded: a run is busy, Stop must still work
  $("limitChapter") && $("limitChapter").addEventListener("change", () => {
    limitIdx = $("limitChapter").value === "" ? null : Number($("limitChapter").value);
    updateSummary();
    refreshTimeline();
  });
  $("togglePre") && $("togglePre").addEventListener("click", () => toggleSection("preChecks", "togglePre", "pre-flight checks"));
  $("toggleTrouble") && $("toggleTrouble").addEventListener("click", () => openTroubleshooting());
  $("toggleFile") && $("toggleFile").addEventListener("click", () => toggleSection("fileDetails", "toggleFile", "details"));
  $("toggleSettings") && $("toggleSettings").addEventListener("click", () => toggleSection("settingsBody", "toggleSettings", "Settings"));
  $("clearLog") && $("clearLog").addEventListener("click", () => { $("log").value = ""; $("copyState").textContent = ""; });
  // Probes and experiments: their messages go to the log only, not to the status line under the Add button.
  const dlog = (text, isError) => log(text, !!isError, !isError);
  on("probe", () => getAdapter().probe(dlog));
  on("probeClips", () => getAdapter().probeClips(dlog));
  on("probeAudio", () => getAdapter().probeAudio(dlog));
  on("probeMarkerOwners", () => getAdapter().probeMarkerOwners(dlog));
  on("probeEditor", () => getAdapter().probeEditor(dlog));
  on("probeClasses", () => getAdapter().probeClasses(dlog));
  on("probeDetect", () => getAdapter().probeDetection(dlog));
  on("probeSelection", () => getAdapter().probeSelection(dlog));
  on("probeCutPlan", async () => {
    const items = plannedItems();
    if (!items || !items.length) return dlog("Cut plan needs a loaded markers file with clips (nothing to plan yet).", true);
    const st = readSettings();
    await getAdapter().probeCutPlan(items, dlog, planOpts(st), hint());
  });
  on("probeGapPlan", async () => {
    const items = plannedItems();
    if (!items || !items.length) return dlog("Gap plan needs a loaded markers file with clips (nothing to plan yet).", true);
    await getAdapter().probeGapPlan(items, dlog, gapArgs(readSettings()), hint());
  });
  on("probeAll", () => getAdapter().probeAll(dlog, plannedItems, hint, () => gapArgs(readSettings())));
  // The ripple experiment changes the project: the first click only arms it.
  let rippleArmed = false;
  on("testRipple", async () => {
    if (!rippleArmed) {
      rippleArmed = true;
      $("testRipple").textContent = "Click again: changes THIS project";
      setTimeout(() => { rippleArmed = false; $("testRipple").textContent = "Test ripple delete"; }, 10000);
      return log("Test ripple delete removes pieces from the timeline (many undo steps): run it on a COPY of the project, on a timeline that is already cut. Click the button again to run it.");
    }
    rippleArmed = false;
    $("testRipple").textContent = "Test ripple delete";
    await getAdapter().testRippleDelete(dlog, hint());
  });
  on("testMarkers", () => getAdapter().addTestMarkers(core.COLORS, dlog));
  on("testClipMarkers", () => getAdapter().addClipTestMarkers(core.COLORS, dlog));
  on("testCut", () => getAdapter().testCutAtPlayhead(dlog));
  on("testSplit", () => getAdapter().testSplitAtPlayhead(dlog));
  on("testAlign", () => getAdapter().testAlignToVideo(dlog));
  try {
    fillColorMenus();
    showSettings(loadSettings());
    for (const id of [...COLOR_FIELDS, ...NUMBER_FIELDS, ...CHECK_FIELDS, ...SELECT_FIELDS]) {
      $(id).addEventListener("change", saveSettings);
    }
    for (const id of ["recipeMarkers", "recipeCutClips", "recipeCutChapters", "recipeDeleteGaps", "minClips", "placement", "autoRun", "maxDeletePct", "minKeepPieces", "padBefore", "padAfter", "mergeGap"]) {
      $(id).addEventListener("change", () => refreshTimeline()); // the pre-flight depends on these
    }
  } catch (e) {
    log(`Could not set up the settings: ${e && e.message ? e.message : e}`, true);
  }
  log(`Panel ready (0.7.3). Core: ${core ? "ok" : "missing"}.`, false, true);
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
