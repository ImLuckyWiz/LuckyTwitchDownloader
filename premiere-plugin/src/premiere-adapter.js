"use strict";
/*
 * Everything that talks to Premiere Pro lives in this file, so when Adobe changes the UXP API (or a call turns out
 * to behave differently from what the docs say) this is the only place to fix.
 *
 * STATUS: written from the Premiere UXP API as documented, NOT yet verified against a running Premiere 2026.
 * The Diagnostics section of the panel ("Probe the API", "Add test markers") exists to check each assumption:
 *   1. the project / sequence / markers calls exist
 *   2. markers are created at the right time with the right length
 *   3. color index N gives the color named in COLORS (markers-core.js)
 */

let pproModule = null;
/** The premierepro module, loaded when first needed (so this file can load even where it is missing). */
function P() {
  if (!pproModule) pproModule = require("premierepro");
  return pproModule;
}

const TICKS_PER_SECOND = 254016000000; // Premiere's time unit

class PremiereError extends Error {
  constructor(message) {
    super(message);
    this.name = "PremiereError";
  }
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

/** Reads a value that may be a property, a method, or a getXxx() method (the UXP API mixes the styles). */
async function read(obj, name) {
  if (obj == null) return undefined;
  const v = obj[name];
  if (typeof v === "function") return await v.call(obj);
  if (v !== undefined) return v;
  const getter = obj["get" + cap(name)];
  return typeof getter === "function" ? await getter.call(obj) : undefined;
}

function toSeconds(t) {
  if (typeof t === "number") return t;
  if (t && typeof t.seconds === "number") return t.seconds;
  if (t && t.ticks !== undefined) return Number(t.ticks) / TICKS_PER_SECOND;
  return NaN;
}

function need(obj, method, where) {
  if (!obj || typeof obj[method] !== "function") {
    throw new PremiereError(
      `This Premiere version does not offer ${where}.${method}(). Open Diagnostics, press "Probe the API" and send the result.`
    );
  }
  return obj[method].bind(obj);
}

const tick = (seconds) => P().TickTime.createWithSeconds(Math.max(0, seconds));

async function activeContext() {
  const project = await P().Project.getActiveProject();
  if (!project) throw new PremiereError("No project is open.");
  const sequence = await project.getActiveSequence();
  if (!sequence) throw new PremiereError("There is no active sequence. Open one in the Timeline and try again.");
  return { project, sequence };
}

/** Runs `build(compoundAction)` as one undoable step ("Edit > Undo" removes everything that was added). */
async function transaction(project, label, build) {
  let ok = true;
  const run = () => {
    ok = project.executeTransaction((compound) => build(compound), label);
  };
  if (typeof project.lockedAccess === "function") await project.lockedAccess(run);
  else run();
  if (ok === false) throw new PremiereError("Premiere refused the change (the transaction failed).");
}

/** Where the part starts in the sequence, in seconds. */
async function baseSeconds(sequence, mode) {
  if (mode !== "playhead") return 0;
  const pos = await need(sequence, "getPlayerPosition", "Sequence")();
  const s = toSeconds(pos);
  if (!Number.isFinite(s)) throw new PremiereError("Could not read the playhead position.");
  return s;
}

/** Existing markers of the sequence as [{marker, start, name}] (best effort: shape differs between builds). */
async function listMarkers(markersOwner) {
  const raw = (await read(markersOwner, "markers")) ?? (await read(markersOwner, "getMarkers"));
  const arr = Array.isArray(raw) ? raw : raw && typeof raw.length === "number" ? Array.from(raw) : [];
  const out = [];
  for (const marker of arr) {
    out.push({ marker, start: toSeconds(await read(marker, "start")), name: await read(marker, "name") });
  }
  return out;
}

const markerType = () => (P().Marker && P().Marker.MARKER_TYPE_COMMENT) || "Comment";

/**
 * Creates the planned markers on the active sequence (from planMarkers in markers-core.js).
 * Step 1 adds them all in one undoable transaction, step 2 colors them. If only step 2 fails the markers
 * stay (with Premiere's default color) and the error says so.
 */
async function importMarkers(items, offsetMode, log) {
  const { project, sequence } = await activeContext();
  const base = await baseSeconds(sequence, offsetMode);
  const markers = await need(P().Markers, "getMarkers", "Markers")(sequence);
  const createAdd = need(markers, "createAddMarkerAction", "the markers list");

  const shifted = items.map((it) => ({ ...it, start: it.start + base }));
  await transaction(project, "LuckyTwitch: add markers", (compound) => {
    for (const it of shifted) {
      compound.addAction(createAdd(it.name, markerType(), tick(it.start), tick(it.duration), it.comment || ""));
    }
  });
  log(`Added ${shifted.length} markers.`);

  try {
    await colorMarkers(project, markers, shifted, log);
  } catch (e) {
    throw new PremiereError(`The ${shifted.length} markers were added, but coloring them failed: ${e.message}`);
  }
  return shifted.length;
}

async function colorMarkers(project, markersOwner, items, log) {
  const existing = await listMarkers(markersOwner);
  if (!existing.length) throw new PremiereError("could not read the markers back from the sequence");
  const wanted = [];
  for (const it of items) {
    const hit = existing.find(
      (m) => m.name === it.name && Math.abs(m.start - it.start) < 0.01 && !wanted.some((w) => w.marker === m.marker)
    );
    if (hit) wanted.push({ marker: hit.marker, color: it.color });
  }
  if (wanted.length < items.length) log(`Colored ${wanted.length} of ${items.length} (the rest could not be matched).`);
  await transaction(project, "LuckyTwitch: color markers", (compound) => {
    for (const w of wanted) {
      compound.addAction(need(w.marker, "createSetColorByIndexAction", "a marker")(w.color));
    }
  });
  log(`Colored ${wanted.length} markers.`);
}

/** Diagnostics: eight markers, one per color index, named with the color the plugin believes that index is. */
async function addTestMarkers(colors, log) {
  const { project, sequence } = await activeContext();
  const markers = await need(P().Markers, "getMarkers", "Markers")(sequence);
  const items = colors.map((c, i) => ({ name: `LT test ${c.name} (index ${c.index})`, start: i * 5, duration: 3, color: c.index }));
  const createAdd = need(markers, "createAddMarkerAction", "the markers list");
  await transaction(project, "LuckyTwitch: test markers", (compound) => {
    for (const it of items) compound.addAction(createAdd(it.name, markerType(), tick(it.start), tick(it.duration), "test"));
  });
  log(`Added ${items.length} test markers at 0 s, 5 s, 10 s... Check that each is the color in its name.`);
  await colorMarkers(project, markers, items, log);
}

/** Names of everything an object offers, walking up its prototype chain. */
function members(obj) {
  const names = new Map();
  let o = obj;
  while (o && o !== Object.prototype && o !== Function.prototype) {
    for (const k of Object.getOwnPropertyNames(o)) {
      if (k === "constructor" || names.has(k)) continue;
      let label = k;
      try {
        label = typeof obj[k] === "function" ? `${k}()` : k;
      } catch (e) {
        label = `${k}(throws)`;
      }
      names.set(k, label);
    }
    o = Object.getPrototypeOf(o);
  }
  return Array.from(names.values()).sort();
}

/** Diagnostics: what the Premiere API actually offers on this build. The text is meant to be pasted back. */
async function probe(log) {
  const line = (title, obj) => log(`${title}: ${obj == null ? "(none)" : members(obj).join(", ")}`);
  try {
    log(`premierepro module: ${Object.keys(P()).sort().join(", ")}`);
    line("Markers (static)", P().Markers);
    line("Marker (static)", P().Marker);
    line("TickTime (static)", P().TickTime);
    const project = await P().Project.getActiveProject();
    line("Project", project);
    const sequence = project ? await project.getActiveSequence() : null;
    line("Sequence", sequence);
    if (sequence && P().Markers && typeof P().Markers.getMarkers === "function") {
      const markers = await P().Markers.getMarkers(sequence);
      line("markers list", markers);
      const first = (await listMarkers(markers))[0];
      line("a marker", first && first.marker);
    }
  } catch (e) {
    log(`Probe stopped: ${e && e.message ? e.message : e}`);
  }
}

const LT_ADAPTER_API = { importMarkers, addTestMarkers, probe, PremiereError };
if (typeof module !== "undefined" && module.exports) module.exports = LT_ADAPTER_API;
if (typeof window !== "undefined") window.LTAdapter = LT_ADAPTER_API;
