"use strict";
/* The panel: file picker, settings, and the Import button. Logic is in markers-core.js, Premiere calls in premiere-adapter.js. */

const core = require("./markers-core.js");
const adapter = require("./premiere-adapter.js");

const $ = (id) => document.getElementById(id);
const STORE_KEY = "luckytwitch-markers-settings-v1";

try {
  require("uxp").entrypoints.setup({ panels: { luckytwitchMarkers: { show() {} } } });
} catch (e) {
  /* older hosts do not need / have this */
}

let loaded = null; // the checked file: {file, label}

function log(text, isError = false) {
  const div = document.createElement("div");
  div.textContent = text;
  if (isError) div.className = "err";
  $("log").appendChild(div);
  $("log").scrollTop = $("log").scrollHeight;
}

// ---- settings -------------------------------------------------------------------------------------------
const COLOR_FIELDS = ["gameColor", "lowColor", "midColor", "highColor", "clipColor"];
const NUMBER_FIELDS = ["minViews", "midViews", "highViews"];
const CHECK_FIELDS = ["importGames", "gamePrefix", "importClips", "colorByViews"];

function fillColorMenus() {
  for (const id of COLOR_FIELDS) {
    for (const c of core.COLORS) {
      const o = document.createElement("option");
      o.value = String(c.index);
      o.textContent = c.name;
      $(id).appendChild(o);
    }
  }
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
  updateSummary();
}

// ---- file and summary -----------------------------------------------------------------------------------
function updateSummary() {
  if (!loaded) return;
  const { items, counts } = core.planMarkers(loaded.file, readSettings());
  const f = loaded.file;
  const lines = [loaded.label];
  if (f.source && f.source.streamer) lines.push(`${f.source.streamer} · ${f.source.title || ""}`.trim());
  if (f.part) lines.push(`Part: ${core.formatTime(f.part.start)} – ${core.formatTime(f.part.end)} of the VOD`);
  lines.push(`Will create ${items.length} markers (${counts.games} game, ${counts.clips} clip)` + (counts.hidden ? `, ${counts.hidden} left out by your choices` : ""));
  if (f.skipped) lines.push(`${f.skipped} entries in the file were not understood and are skipped.`);
  $("fileInfo").textContent = lines.join("\n");
  $("import").disabled = items.length === 0;
}

async function pickFile() {
  try {
    const fs = require("uxp").storage.localFileSystem;
    const entry = await fs.getFileForOpening({ types: ["json"] });
    if (!entry) return; // cancelled
    const file = core.parseMarkersFile(await entry.read());
    loaded = { file, label: entry.name };
    updateSummary();
  } catch (e) {
    loaded = null;
    $("import").disabled = true;
    $("fileInfo").textContent = "No file chosen.";
    log(e.message || String(e), true);
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
  const n = await adapter.importMarkers(items, settings.offsetMode, log);
  log(`Done: ${n} markers on the active sequence.`);
}

window.addEventListener("load", () => {
  fillColorMenus();
  showSettings(loadSettings());
  for (const id of [...COLOR_FIELDS, ...NUMBER_FIELDS, ...CHECK_FIELDS, "offsetMode"]) {
    $(id).addEventListener("change", saveSettings);
  }
  $("pick").addEventListener("click", () => guarded(pickFile));
  $("import").addEventListener("click", () => guarded(doImport));
  $("probe").addEventListener("click", () => guarded(() => adapter.probe(log)));
  $("testMarkers").addEventListener("click", () => guarded(() => adapter.addTestMarkers(core.COLORS, log)));
});
