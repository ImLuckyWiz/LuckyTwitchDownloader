"use strict";
try {
/* The panel: file picker, settings, and the Import button. Logic is in markers-core.js, Premiere calls in premiere-adapter.js. */

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
  require("uxp").entrypoints.setup({ panels: { luckytwitchMarkers: { show() {} } } });
} catch (e) {
  /* older hosts do not need / have this */
}

let loaded = null; // the checked file: {file, label}

function setStatus(text, kind) {
  const el = $("status");
  if (!el) return;
  el.textContent = text;
  el.className = kind || "muted";
}

function openTroubleshooting(open) {
  $("troubleBody").style.display = open ? "block" : "none";
  $("toggleTrouble").textContent = (open ? "▾ " : "▸ ") + "Troubleshooting";
}

/** Writes to the log (Troubleshooting) and shows the latest message in the status line under the Import button. */
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
const NUMBER_FIELDS = ["minViews", "midViews", "highViews"];
const CHECK_FIELDS = ["importGames", "gamePrefix", "importClips", "colorByViews"];

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
  $("offsetMode").value = s.offsetMode;
  updateDots();
  refreshVisibility();
}

function readSettings() {
  const raw = { offsetMode: $("offsetMode").value };
  for (const id of COLOR_FIELDS) raw[id] = Number($(id).value);
  for (const id of NUMBER_FIELDS) raw[id] = $(id).value.trim();
  for (const id of CHECK_FIELDS) raw[id] = $(id).checked;
  return core.normalizeSettings(raw);
}

function saveSettings() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(readSettings()));
  } catch (e) {
    /* storage can be unavailable; the settings just won't be remembered */
  }
  updateDots();
  refreshVisibility();
  updateSummary();
}

// ---- file and summary -----------------------------------------------------------------------------------
function updateSummary() {
  if (!loaded) return;
  const settings = readSettings();
  const { items, counts } = core.planMarkers(loaded.file, settings);
  const f = loaded.file;
  $("fileEmpty").style.display = "none";
  $("fileDetails").style.display = "block";
  $("fileName").textContent = loaded.label;
  $("fileTitle").textContent = f.source && f.source.streamer ? `${f.source.streamer} · ${f.source.title || ""}`.trim() : "";
  $("filePart").textContent = f.part ? `Part ${core.formatTime(f.part.start)} – ${core.formatTime(f.part.end)} of the VOD` : "";
  $("pillGames").textContent = `${counts.games} game ${counts.games === 1 ? "change" : "changes"}`;
  $("pillClips").textContent = `${counts.clips} ${counts.clips === 1 ? "clip" : "clips"}`;
  $("pillGameDot").style.backgroundColor = colorHex(settings.gameColor);
  $("pillClipDot").style.backgroundColor = colorHex(settings.colorByViews ? settings.midColor : settings.clipColor);
  const notes = [];
  if (counts.hidden) notes.push(`${counts.hidden} left out by your choices.`);
  if (f.skipped) notes.push(`${f.skipped} entries in the file were not understood and are skipped.`);
  $("fileNote").textContent = notes.join(" ");
  $("import").disabled = items.length === 0;
  $("importClip").disabled = items.length === 0;
  $("import").textContent = items.length ? `${items.length} to sequence` : "To sequence";
  $("importClip").textContent = items.length ? `${items.length} to clip` : "To clip";
  setStatus(items.length ? "Ready." : "Nothing to import with these choices.", items.length ? "muted" : "err");
}

function useFileText(text, label) {
  const file = core.parseMarkersFile(text);
  loaded = { file, label };
  $("pick").textContent = "Choose another file…";
  updateSummary();
}

function failLoad(e) {
  loaded = null;
  $("import").disabled = true;
  $("importClip").disabled = true;
  $("import").textContent = "To sequence";
  $("importClip").textContent = "To clip";
  $("fileEmpty").style.display = "block";
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
    useFileText(await entry.read(), entry.name);
  } catch (e) {
    failLoad(e);
    log("If the picker will not open on your Premiere, open the .markers.json in Notepad, copy everything, paste it in the box below and press «Use pasted text».", true);
  }
}

function usePasted() {
  const text = $("pasted").value.trim();
  if (!text) return log("Paste the contents of the .markers.json first.", true);
  try {
    useFileText(text, "(pasted text)");
  } catch (e) {
    failLoad(e);
  }
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
}

async function doImport() {
  if (!loaded) return;
  const settings = readSettings();
  const { items } = core.planMarkers(loaded.file, settings);
  if (!items.length) return log("Nothing to import with these choices.", true);
  const n = await getAdapter().importMarkers(items, settings.offsetMode, log);
  log(`Done: ${n} markers added to the active sequence.`);
}

async function doImportToClip() {
  if (!loaded) return;
  const settings = readSettings();
  const { items } = core.planMarkers(loaded.file, settings);
  if (!items.length) return log("Nothing to import with these choices.", true);
  const r = await getAdapter().importMarkersToClip(items, log);
  log(`Done: ${r.count} markers added to the clip "${r.clipName}" (they follow it through your cuts).`);
}

function init() {
  // Buttons first: whatever fails after this, they still react.
  const on = (id, fn) => $(id) && $(id).addEventListener("click", () => guarded(fn));
  on("pick", pickFile);
  on("usePasted", usePasted);
  on("import", doImport);
  on("importClip", doImportToClip);
  on("copyLog", copyLog);
  $("toggleTrouble") && $("toggleTrouble").addEventListener("click", () => openTroubleshooting($("troubleBody").style.display === "none"));
  $("clearLog") && $("clearLog").addEventListener("click", () => { $("log").value = ""; $("copyState").textContent = ""; });
  on("probe", () => getAdapter().probe(log));
  on("testMarkers", () => getAdapter().addTestMarkers(core.COLORS, log));
  // Experiment (clip markers): its messages go to the log only, not to the status line under the Import button.
  const dlog = (text, isError) => log(text, !!isError, !isError);
  on("probeClips", () => getAdapter().probeClips(dlog));
  on("testClipMarkers", () => getAdapter().addClipTestMarkers(core.COLORS, dlog));
  try {
    fillColorMenus();
    showSettings(loadSettings());
    for (const id of [...COLOR_FIELDS, ...NUMBER_FIELDS, ...CHECK_FIELDS, "offsetMode"]) {
      $(id).addEventListener("change", saveSettings);
    }
  } catch (e) {
    log(`Could not set up the settings: ${e && e.message ? e.message : e}`, true);
  }
  log(`Panel ready (settings, file picker and buttons are set up). Core: ${core ? "ok" : "missing"}, Premiere adapter: ${window.LTAdapter ? "ok" : "not loaded"}.`, false, true);
}

window.addEventListener("error", (ev) => log(`Error: ${ev.message || ev}`, true));
window.addEventListener("unhandledrejection", (ev) => log(`Error: ${ev.reason && ev.reason.message ? ev.reason.message : ev.reason}`, true));

if (document.readyState === "loading") window.addEventListener("DOMContentLoaded", init);
else init();
} catch (e) {
  if (window.__ltLog) window.__ltLog("main.js failed to start: " + (e && e.stack ? e.stack : e), true);
}
