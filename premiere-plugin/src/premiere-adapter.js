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

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Runs `build(compoundAction)` as one undoable step ("Edit > Undo" removes everything that was added). */
async function transaction(project, label, build) {
  let result = true;
  const run = () => {
    result = project.executeTransaction((compound) => build(compound), label);
  };
  if (typeof project.lockedAccess === "function") await project.lockedAccess(run);
  else run();
  const ok = await result; // some builds return a promise, others a plain boolean
  if (ok === false) throw new PremiereError("Premiere refused the change (the transaction failed).");
  await sleep(100); // let Premiere commit before anything reads the markers back
}

/** Where the part starts in the sequence, in seconds. */
async function baseSeconds(sequence, mode) {
  if (mode !== "playhead") return 0;
  const pos = await need(sequence, "getPlayerPosition", "Sequence")();
  const s = toSeconds(pos);
  if (!Number.isFinite(s)) throw new PremiereError("Could not read the playhead position.");
  return s;
}

/** Turns whatever a build returns for "the markers" (array, array-like, iterable) into a plain array, or null. */
function asArray(raw) {
  if (Array.isArray(raw)) return raw;
  if (raw && typeof raw.length === "number") return Array.from(raw);
  if (raw && typeof raw[Symbol.iterator] === "function") return Array.from(raw);
  return null;
}

/**
 * Existing markers of a sequence / clip project item as [{marker, start, name}], read FRESH from Premiere
 * (a Markers object fetched earlier can be a stale snapshot that never shows markers added after it).
 * Retries a few times because the change may take a moment to show up. Returns [] when nothing could be read;
 * `why` (optional array) collects what was tried, for the log.
 */
async function listMarkers(owner, why) {
  for (let attempt = 0; attempt < 5; attempt++) {
    if (attempt) await sleep(150);
    let list;
    try {
      list = await need(P().Markers, "getMarkers", "Markers")(owner);
    } catch (e) {
      if (why) why.push(`Markers.getMarkers(owner) threw: ${e && e.message ? e.message : e}`);
      continue;
    }
    // `list` is either the array itself or an object that holds it.
    let arr = asArray(list);
    let via = "the returned value itself";
    if (!arr && list) {
      for (const name of ["getMarkers", "markers", "getMarkerList", "getAll", "getItems"]) {
        const v = list[name];
        try {
          arr = asArray(typeof v === "function" ? await v.call(list) : v);
        } catch (e) {
          arr = null;
        }
        if (arr) {
          via = name;
          break;
        }
      }
    }
    if (why && attempt === 0) {
      why.push(`Markers.getMarkers(owner) returned ${list == null ? "nothing" : Array.isArray(list) ? "an array" : "an object offering: " + members(list).join(", ")}; read through ${arr ? via : "(nothing worked)"}`);
    }
    if (arr && arr.length) {
      const out = [];
      for (const marker of arr) {
        out.push({ marker, start: toSeconds(await read(marker, "start")), name: await read(marker, "name") });
      }
      return out;
    }
  }
  return [];
}

const markerType = () => (P().Marker && P().Marker.MARKER_TYPE_COMMENT) || "Comment";

/** Adds the items as markers on `owner` (a sequence, or a clip's project item) in one undo step, then colors them. */
async function addAndColor(project, owner, items, label, log) {
  const markers = await need(P().Markers, "getMarkers", "Markers")(owner);
  const createAdd = need(markers, "createAddMarkerAction", "the markers list");
  await transaction(project, label, (compound) => {
    for (const it of items) {
      compound.addAction(createAdd(it.name, markerType(), tick(it.start), tick(it.duration), it.comment || ""));
    }
  });
  log(`Added ${items.length} markers.`);
  try {
    await colorMarkers(project, owner, items, log);
  } catch (e) {
    throw new PremiereError(`The ${items.length} markers were added, but coloring them failed: ${e.message}`);
  }
}

/** Creates the planned markers (from planMarkers in markers-core.js) on the active SEQUENCE. */
async function importMarkers(items, offsetMode, log) {
  const { project, sequence } = await activeContext();
  const base = await baseSeconds(sequence, offsetMode);
  const shifted = items.map((it) => ({ ...it, start: it.start + base }));
  await addAndColor(project, sequence, shifted, "LuckyTwitch: add markers", log);
  return shifted.length;
}

/**
 * Creates the planned markers on the SOURCE of a clip, so they follow the clip through every cut.
 * The target is the selected clip (else the first video clip). The part's own time 0 is the start of the media,
 * so a marker at part-time t goes to source-time t (no offset, no playhead).
 */
async function importMarkersToClip(items, log) {
  const { project, sequence } = await activeContext();
  const target = await pickTargetClip(sequence, log);
  const d = await describeClip(target.item);
  log(`Target clip (${target.where}): "${d.name}", media "${d.mediaName}".`);
  const owner = await clipProjectItem(target.item);
  if (!owner) throw new PremiereError("Could not get the clip's project item (the source media).");
  await addAndColor(project, owner, items, "LuckyTwitch: add markers to clip", log);
  return { count: items.length, clipName: d.name };
}

/** The selected clip, else the first video clip on the timeline. */
async function pickTargetClip(sequence, log) {
  const selected = (await selectedClips(sequence))[0];
  if (selected) return { item: selected, where: "the selected clip" };
  const first = (await videoClips(sequence, log))[0];
  if (first) return { item: first.item, where: "the first video clip, because none is selected" };
  throw new PremiereError("There is no clip on the timeline. Put the video on the timeline (and select it) first.");
}

/** Colors the markers that were just added. Reads them back fresh from `owner`; never relies on an old list. */
async function colorMarkers(project, owner, items, log) {
  const why = [];
  const existing = await listMarkers(owner, why);
  if (!existing.length) {
    why.forEach((w) => log(`(read-back detail) ${w}`, false));
    throw new PremiereError("could not read the markers back from Premiere (details are in the log above; please send them)");
  }
  const pending = items.slice();
  const wanted = [];
  for (const m of existing) {
    const i = pending.findIndex((it) => it.name === m.name && Math.abs(it.start - m.start) < 0.01);
    if (i < 0) continue;
    wanted.push({ marker: m.marker, color: pending[i].color });
    pending.splice(i, 1);
  }
  if (pending.length) log(`Colored ${wanted.length} of ${items.length} (${pending.length} could not be matched by name and time).`);
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
  const items = colors.map((c, i) => ({ name: `LT test ${c.name} (index ${c.index})`, start: i * 5, duration: 3, color: c.index, comment: "test" }));
  await addAndColor(project, sequence, items, "LuckyTwitch: test markers", log);
  log(`Added ${items.length} test markers at 0 s, 5 s, 10 s... Check that each is the color in its name.`);
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
      const found = await listMarkers(sequence, []);
      log(`markers currently on the sequence: ${found.length}`);
      line("a marker", found[0] && found[0].marker);
    }
  } catch (e) {
    log(`Probe stopped: ${e && e.message ? e.message : e}`);
  }
}

// ---------------------------------------------------------------------------------------------------------------
// EXPERIMENT (not used by the import): can markers live on the source clip instead of the sequence, so they follow
// every cut? And can the plugin read where each clip sits on the timeline and which part of the source it plays?
// Both buttons are in Troubleshooting; they only report what this Premiere offers.
// ---------------------------------------------------------------------------------------------------------------
const safe = async (fn) => {
  try {
    return await fn();
  } catch (e) {
    return undefined;
  }
};

/** Runs fn; on failure logs the reason (so one missing call does not hide the others) and returns undefined. */
async function attempt(log, label, fn) {
  try {
    return await fn();
  } catch (e) {
    log(`${label}: failed (${e && e.message ? e.message : e})`, true);
    return undefined;
  }
}

const fmtSec = (v) => {
  const s = toSeconds(v);
  return Number.isFinite(s) ? `${s.toFixed(3)} s` : "?";
};

/** Every clip on the video tracks as [{track, item}]. */
async function videoClips(sequence, log) {
  const out = [];
  const count = await attempt(log, "getVideoTrackCount", () => need(sequence, "getVideoTrackCount", "Sequence")());
  const typeEnum = P().Constants && P().Constants.TrackItemType;
  const type = typeEnum && typeEnum.CLIP !== undefined ? typeEnum.CLIP : 1;
  for (let i = 0; i < (count || 0); i++) {
    const track = await attempt(log, `getVideoTrack(${i})`, () => need(sequence, "getVideoTrack", "Sequence")(i));
    if (!track) continue;
    if (typeof track.getTrackItems !== "function") {
      log(`Video track ${i + 1} has no getTrackItems(). It offers: ${members(track).join(", ")}`, true);
      continue;
    }
    const items = await attempt(log, `track ${i + 1} getTrackItems`, () => track.getTrackItems(type, false));
    for (const item of items || []) out.push({ track: i + 1, item });
  }
  return out;
}

/** The clip's own project item (the source media), as ClipProjectItem when this build can cast it. */
async function clipProjectItem(item) {
  const pi = await safe(() => read(item, "projectItem"));
  if (!pi) return undefined;
  const CP = P().ClipProjectItem;
  const cast = CP && typeof CP.cast === "function" ? await safe(() => CP.cast(pi)) : undefined;
  return cast || pi;
}

async function describeClip(item) {
  const get = (name) => safe(() => read(item, name));
  const pi = await clipProjectItem(item);
  return {
    name: await get("name"),
    start: await get("startTime"),
    end: await get("endTime"),
    inPoint: await get("inPoint"),
    outPoint: await get("outPoint"),
    duration: await get("duration"),
    mediaName: pi ? await safe(() => read(pi, "name")) : undefined,
    mediaPath: pi ? await safe(() => read(pi, "mediaFilePath")) : undefined,
  };
}

async function selectedClips(sequence) {
  const sel = await safe(() => read(sequence, "selection"));
  const items = sel ? await safe(() => read(sel, "trackItems")) : undefined;
  return Array.isArray(items) ? items : [];
}

/** Read-only: lists the timeline clips with their timeline position and source in/out, and what the objects offer. */
async function probeClips(log) {
  const { sequence } = await activeContext();
  const typeEnum = P().Constants && P().Constants.TrackItemType;
  log(`Constants.TrackItemType: ${typeEnum ? JSON.stringify(typeEnum) : "(none)"}`);
  const clips = await videoClips(sequence, log);
  log(`Video clips on the timeline: ${clips.length}`);
  for (const { track, item } of clips.slice(0, 20)) {
    const d = await describeClip(item);
    log(
      `V${track} "${d.name}": timeline ${fmtSec(d.start)} -> ${fmtSec(d.end)}, plays source ${fmtSec(d.inPoint)} -> ${fmtSec(d.outPoint)}` +
        `, media "${d.mediaName}" ${d.mediaPath ? `(${d.mediaPath})` : "(no file path)"}`
    );
  }
  if (clips.length > 20) log(`... and ${clips.length - 20} more.`);
  const sel = await selectedClips(sequence);
  log(`Selected clips: ${sel.length}`);
  if (clips[0]) {
    line_("a timeline clip", clips[0].item, log);
    const pi = await clipProjectItem(clips[0].item);
    line_("its project item", pi, log);
  }
}

function line_(title, obj, log) {
  log(`${title}: ${obj == null ? "(none)" : members(obj).join(", ")}`);
}

/**
 * Adds 3 markers to the SOURCE of one clip (the selected clip, else the first video clip), at 2, 4 and 6 s into the
 * part of the source that clip plays, then reads them back. If clip markers follow cuts, they will show up on the clip
 * wherever it sits, and keep their place after you razor or ripple-delete around them.
 */
async function addClipTestMarkers(colors, log) {
  const { project, sequence } = await activeContext();
  let target = (await selectedClips(sequence))[0];
  let where = "the selected clip";
  if (!target) {
    const first = (await videoClips(sequence, log))[0];
    target = first && first.item;
    where = "the first video clip";
  }
  if (!target) throw new PremiereError("There is no clip on the timeline to test with.");
  const d = await describeClip(target);
  log(`Using ${where}: "${d.name}" (media "${d.mediaName}"), plays source ${fmtSec(d.inPoint)} -> ${fmtSec(d.outPoint)}.`);

  const owner = await clipProjectItem(target);
  if (!owner) throw new PremiereError("Could not get the clip's project item (the source media).");
  const base = Number.isFinite(toSeconds(d.inPoint)) ? toSeconds(d.inPoint) : 0;
  const items = [
    { name: "LT clip test 1 (green)", start: base + 2, duration: 1, color: 0 },
    { name: "LT clip test 2 (red)", start: base + 4, duration: 1, color: 1 },
    { name: "LT clip test 3 (blue)", start: base + 6, duration: 1, color: 6 },
  ];
  await addAndColor(project, owner, items.map((it) => ({ ...it, comment: "clip test" })), "LuckyTwitch: clip test markers", log);
  log(`Added ${items.length} markers on the source clip at source ${items.map((m) => m.start.toFixed(1)).join(", ")} s.`);

  const back = await listMarkers(owner, []);
  log(`Read back from the clip: ${back.length} marker(s): ${back.map((m) => `"${m.name}" at ${toSeconds(m.start).toFixed(1)} s`).join(", ")}`);
  log(
    "Now look at that clip: double-click it in the Project panel (Source Monitor) and check the Markers panel; " +
      "also look for the markers on the clip in your timeline. Then cut a piece out before them and see if they stay on the same moment. " +
      "Ctrl+Z removes the test markers."
  );
}

const LT_ADAPTER_API = { importMarkers, importMarkersToClip, addTestMarkers, probe, probeClips, addClipTestMarkers, PremiereError, _setPremiere: (m) => { pproModule = m; } };
if (typeof module !== "undefined" && module.exports) module.exports = LT_ADAPTER_API;
if (typeof window !== "undefined") window.LTAdapter = LT_ADAPTER_API;
