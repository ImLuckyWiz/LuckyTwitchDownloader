"use strict";
/*
 * Everything that talks to Premiere Pro lives in this file, so when Adobe changes the UXP API (or a call turns out
 * to behave differently from what the docs say) this is the only place to fix.
 *
 * STATUS (0.5.0): markers on the sequence / on the clip, and their coloring, are verified on Premiere Pro 2026. The cut engine (clone +
 * trim in halving rounds) ran on a real Premiere in 0.4.1; what is NEW in 0.5.0 is that it works on every clip of the markers file's
 * video (collectTarget / cutAtClipEdges), which so far is only covered by the fake-timeline tests (test/cut.test.js).
 * Finding the markers file next to the video and everything under "Probes" / "Experiments" are NEW and unverified:
 * the Troubleshooting section of the panel exists to check each assumption and report what this Premiere offers.
 */

const C = () => (typeof window !== "undefined" && window.LTCore) || require("./markers-core.js");

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
async function transaction(project, label, build, settle = 100) {
  let result = true;
  const run = () => {
    result = project.executeTransaction((compound) => build(compound), label);
  };
  if (typeof project.lockedAccess === "function") await project.lockedAccess(run);
  else run();
  const ok = await result; // some builds return a promise, others a plain boolean
  if (ok === false) throw new PremiereError("Premiere refused the change (the transaction failed).");
  if (settle > 0) await sleep(settle); // let Premiere commit before anything reads the markers back
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
async function listMarkers(owner, why, attempts = 5) {
  for (let attempt = 0; attempt < attempts; attempt++) {
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

const sameMarker = (m, it) => m.name === it.name && Math.abs(m.start - it.start) < 0.01;

/**
 * Adds the items as markers on `owner` (a sequence, or a clip's project item) in one undo step, then colors them.
 * Markers that are already there (same name and time) are not added again, only recolored. Returns {added, skipped}.
 */
async function addAndColor(project, owner, items, label, log) {
  const taken = (await listMarkers(owner, undefined, 1)).slice();
  const fresh = [];
  for (const it of items) {
    const i = taken.findIndex((m) => sameMarker(m, it));
    if (i >= 0) taken.splice(i, 1);
    else fresh.push(it);
  }
  const skipped = items.length - fresh.length;
  if (fresh.length) {
    const markers = await need(P().Markers, "getMarkers", "Markers")(owner);
    const createAdd = need(markers, "createAddMarkerAction", "the markers list");
    await transaction(project, label, (compound) => {
      for (const it of fresh) {
        compound.addAction(createAdd(it.name, markerType(), tick(it.start), tick(it.duration), it.comment || ""));
      }
    });
    log(`Added ${fresh.length} markers.${skipped ? ` ${skipped} were already there.` : ""}`);
  } else {
    log(`All ${items.length} markers were already there.`);
  }
  try {
    await colorMarkers(project, owner, items, log);
  } catch (e) {
    throw new PremiereError(`The ${fresh.length} markers were added, but coloring them failed: ${e.message}`);
  }
  return { added: fresh.length, skipped };
}

/** Where markers go: the active sequence, or the source of the selected clip (else the first video clip). */
async function resolveOwner(placement, log) {
  const { project, sequence } = await activeContext();
  if (placement === "sequence") return { project, sequence, owner: sequence, what: "the active sequence" };
  const target = await pickTargetClip(sequence, log);
  const d = await describeClip(target.item);
  log(`Target clip (${target.where}): "${d.name}", media "${d.mediaName}".`);
  const owner = await clipProjectItem(target.item);
  if (!owner) throw new PremiereError("Could not get the clip's project item (the source media).");
  return { project, sequence, owner, what: `the clip "${d.name}"`, clipName: d.name };
}

/**
 * The one entry point of the panel. opts = {placement: "clip" | "sequence", offsetMode: "start" | "playhead"}.
 * On a clip the part's own time 0 is the start of the media, so a marker at part-time t goes to source-time t
 * (no offset, no playhead). Returns {added, skipped, what}.
 */
async function addMarkers(items, opts, log) {
  const o = opts || {};
  const t = await resolveOwner(o.placement, log);
  let list = items;
  if (o.placement === "sequence") {
    const base = await baseSeconds(t.sequence, o.offsetMode);
    list = items.map((it) => ({ ...it, start: it.start + base }));
  }
  const label = o.placement === "sequence" ? "LuckyTwitch: add markers" : "LuckyTwitch: add markers to clip";
  const r = await addAndColor(t.project, t.owner, list, label, log);
  return { ...r, what: t.what };
}

/** Removes the markers (same name and time as `items`) that a previous import put on the target. One undo step. Returns the number removed. */
async function removeMarkers(items, opts, log) {
  const o = opts || {};
  const t = await resolveOwner(o.placement, log);
  let list = items;
  if (o.placement === "sequence") {
    const base = await baseSeconds(t.sequence, o.offsetMode);
    list = items.map((it) => ({ ...it, start: it.start + base }));
  }
  const existing = await listMarkers(t.owner, undefined, 2);
  const pending = list.slice();
  const doomed = [];
  for (const m of existing) {
    const i = pending.findIndex((it) => sameMarker(m, it));
    if (i < 0) continue;
    doomed.push(m.marker);
    pending.splice(i, 1);
  }
  if (!doomed.length) return { removed: 0, what: t.what };
  const markers = await need(P().Markers, "getMarkers", "Markers")(t.owner);
  const createRemove = need(markers, "createRemoveMarkerAction", "the markers list");
  await transaction(t.project, "LuckyTwitch: remove markers", (compound) => {
    for (const mk of doomed) compound.addAction(createRemove(mk));
  });
  log(`Removed ${doomed.length} markers.`);
  return { removed: doomed.length, what: t.what };
}

/** Creates the planned markers on the active SEQUENCE (kept for the tests and older callers). */
async function importMarkers(items, offsetMode, log) {
  return addMarkers(items, { placement: "sequence", offsetMode }, log);
}

/** Creates the planned markers on the SOURCE of a clip, so they follow the clip through every cut. */
async function importMarkersToClip(items, log) {
  return addMarkers(items, { placement: "clip" }, log);
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

// ---------------------------------------------------------------------------------------------------------------
// FINDING THE MARKERS FILE BY ITSELF (0.4.0, new): the .markers.json is written next to each downloaded part, so the
// folder of the target clip's media is the best place to look; the folder of the Premiere project is the second.
// Reading a folder by path needs the manifest permission localFileSystem: "fullAccess".
// ---------------------------------------------------------------------------------------------------------------
const msg = (e) => (e && e.message ? e.message : String(e));

/** Where to look, in order: [{where, folder, mediaName}]. `why` collects what was found, for the log. */
async function detectionTargets(why) {
  const { project, sequence } = await activeContext();
  const out = [];
  let mediaName;
  let mediaPathOfTarget;
  try {
    const target = await pickTargetClip(sequence, () => {});
    const pi = await clipProjectItem(target.item);
    const mediaPath = pi ? await safe(() => read(pi, "mediaFilePath")) : undefined;
    why.push(`target clip: ${target.where}; its media path: ${mediaPath || "(none)"}`);
    if (mediaPath) {
      mediaPathOfTarget = mediaPath;
      mediaName = C().baseName(mediaPath);
      out.push({ where: "next to the video", folder: C().dirName(mediaPath), mediaName, mediaPath });
    }
  } catch (e) {
    why.push(`no target clip: ${msg(e)}`);
  }
  const projectPath = await safe(() => read(project, "path"));
  why.push(`project path: ${projectPath || "(not saved yet)"}`);
  if (projectPath && C().dirName(projectPath)) out.push({ where: "next to the Premiere project", folder: C().dirName(projectPath), mediaName, mediaPath: mediaPathOfTarget });
  return out;
}

/** A folder entry from a native path, trying the URL forms UXP may want. Returns null (and says why in `why`). */
async function openFolder(path, why) {
  let fs;
  try {
    fs = require("uxp").storage.localFileSystem;
  } catch (e) {
    why.push(`no file system access: ${msg(e)}`);
    return null;
  }
  for (const url of C().fileUrlForms(path)) {
    try {
      const entry = await fs.getEntryWithUrl(url);
      if (entry && entry.isFolder !== false) {
        why.push(`opened the folder with getEntryWithUrl("${url}")`);
        return entry;
      }
      why.push(`getEntryWithUrl("${url}") gave something that is not a folder`);
    } catch (e) {
      why.push(`getEntryWithUrl("${url}") failed: ${msg(e)}`);
    }
  }
  return null;
}

/**
 * Looks for the markers file of the target clip. Returns {text, name, path, where, how} or null.
 * Never throws for "not found" (that is a normal answer); `why` (array) collects the steps for the log.
 */
async function findMarkersFile(why = []) {
  const targets = await detectionTargets(why);
  if (!targets.length) {
    why.push("nothing to look next to: no clip with a media file and no saved project");
    return null;
  }
  for (const t of targets) {
    const folder = await openFolder(t.folder, why);
    if (!folder) continue;
    let entries;
    try {
      entries = await folder.getEntries();
    } catch (e) {
      why.push(`could not list "${t.folder}": ${msg(e)}`);
      continue;
    }
    const files = (entries || []).filter((e) => e.isFile);
    const names = files.map((e) => e.name);
    const markerNames = names.filter((n) => n.toLowerCase().endsWith(C().MARKERS_SUFFIX));
    why.push(`${t.where}: "${t.folder}" has ${files.length} files, ${markerNames.length} of them .markers.json${markerNames.length ? ": " + markerNames.join(" | ") : ""}`);
    const pick = C().pickMarkersFile(names, t.mediaName);
    if (!pick) {
      if (markerNames.length) why.push(`${markerNames.length} markers files there but none can be told to be this video's`);
      continue;
    }
    const entry = files.find((e) => e.name === pick.name);
    let text;
    try {
      text = await entry.read();
    } catch (e) {
      why.push(`could not read "${pick.name}": ${msg(e)}`);
      continue;
    }
    return { text, name: pick.name, path: entry.nativePath || `${t.folder}/${pick.name}`, where: t.where, how: pick.how, mediaPath: t.mediaPath };
  }
  return null;
}

/** Probe: runs the search and prints every step. */
async function probeDetection(log) {
  const why = [];
  let found = null;
  try {
    found = await findMarkersFile(why);
  } catch (e) {
    why.push(`stopped: ${msg(e)}`);
  }
  why.forEach((w) => log(`(detect) ${w}`));
  log(found ? `Detection result: "${found.name}" (${found.where}; ${found.how}), ${found.text.length} characters.` : "Detection result: nothing found.");
}

// ---------------------------------------------------------------------------------------------------------------
// PROBES (read-only) and EXPERIMENTS (they change the project; Ctrl+Z undoes them). All in Troubleshooting.
// They exist so that the next version (cutting the clips at each marker) is written against what this Premiere
// really offers instead of against guesses. Paste the log back.
// ---------------------------------------------------------------------------------------------------------------
const secOf = (v) => toSeconds(v);

/** Every clip on the audio tracks as [{track, item}]. */
async function audioClips(sequence, log) {
  const out = [];
  const count = await attempt(log, "getAudioTrackCount", () => need(sequence, "getAudioTrackCount", "Sequence")());
  const typeEnum = P().Constants && P().Constants.TrackItemType;
  const type = typeEnum && typeEnum.CLIP !== undefined ? typeEnum.CLIP : 1;
  for (let i = 0; i < (count || 0); i++) {
    const track = await attempt(log, `getAudioTrack(${i})`, () => need(sequence, "getAudioTrack", "Sequence")(i));
    if (!track || typeof track.getTrackItems !== "function") continue;
    const items = await attempt(log, `audio track ${i + 1} getTrackItems`, () => track.getTrackItems(type, false));
    for (const item of items || []) out.push({ track: i + 1, item });
  }
  return out;
}

/** Probe: the audio side of the timeline (a razor has to cut the audio too), and which audio clip looks linked to which video clip. */
async function probeAudio(log) {
  const { sequence } = await activeContext();
  const aCount = await safe(() => need(sequence, "getAudioTrackCount", "Sequence")());
  log(`Audio tracks: ${aCount}`);
  const track = await safe(() => sequence.getAudioTrack(0));
  line_("an audio track", track, log);
  const clips = await audioClips(sequence, log);
  log(`Audio clips on the timeline: ${clips.length}`);
  for (const { track: n, item } of clips.slice(0, 20)) {
    const d = await describeClip(item);
    log(`A${n} "${d.name}": timeline ${fmtSec(d.start)} -> ${fmtSec(d.end)}, plays source ${fmtSec(d.inPoint)} -> ${fmtSec(d.outPoint)}, media "${d.mediaName}"`);
  }
  if (clips[0]) line_("an audio clip", clips[0].item, log);
  const videos = await videoClips(sequence, log);
  for (const v of videos.slice(0, 10)) {
    const vd = await describeClip(v.item);
    const linked = [];
    for (const a of clips) {
      const ad = await describeClip(a.item);
      if (Math.abs(secOf(ad.start) - secOf(vd.start)) < 0.01 && Math.abs(secOf(ad.end) - secOf(vd.end)) < 0.01) linked.push(`A${a.track}`);
    }
    log(`V${v.track} "${vd.name}" has audio with the same start and end on: ${linked.join(", ") || "(none)"}`);
  }
}

/** Probe: what the sequence editor offers (is there anything like a razor?), plus the track and selection objects. */
async function probeEditor(log) {
  const { sequence } = await activeContext();
  const SE = P().SequenceEditor;
  line_("SequenceEditor (static)", SE, log);
  line_("SequenceEditor.prototype", SE && SE.prototype, log);
  let editor;
  for (const how of ["getEditor", "getInstance", "create"]) {
    if (SE && typeof SE[how] === "function") {
      editor = await safe(() => SE[how](sequence));
      if (editor) {
        log(`editor obtained with SequenceEditor.${how}(sequence)`);
        break;
      }
    }
  }
  if (!editor && typeof SE === "function") editor = await safe(() => new SE(sequence));
  line_("the editor", editor, log);
  if (editor) {
    const cutting = members(editor).filter((n) => /razor|split|cut|slice|trim|ripple|extract|lift|remove|delete|overwrite|insert|add/i.test(n));
    log(`editor members that look like cutting / removing: ${cutting.join(", ") || "(none)"}`);
  }
  line_("the selection", await safe(() => sequence.getSelection()), log);
  line_("a video track", await safe(() => sequence.getVideoTrack(0)), log);
  const vt = await safe(() => sequence.getVideoTrack(0));
  if (vt) {
    for (const name of ["getTrackItems", "getTrackItemsAtTime", "getName", "isMuted", "isLocked", "getIndex", "getId"]) {
      if (typeof vt[name] === "function") log(`video track offers ${name}()`);
    }
  }
}

/** Probe: members of many classes (static side and prototype) and the values of the Constants enums. */
async function probeClasses(log) {
  const names = [
    "SequenceEditor", "TrackItemSelection", "Action", "CompoundAction", "ClipProjectItem", "ProjectItem", "FolderItem",
    "SequenceUtils", "ProjectUtils", "WorkAreaUtils", "Utils", "EventManager", "VideoTrack", "AudioTrack",
    "VideoClipTrackItem", "AudioClipTrackItem", "SourceMonitor", "Media", "Properties", "Metadata", "Exporter",
    "Transcript", "TransitionFactory", "SequenceSettings", "Keyframe",
  ];
  for (const n of names) {
    const cls = P()[n];
    if (!cls) {
      log(`${n}: (not in this Premiere)`);
      continue;
    }
    line_(`${n} (static)`, cls, log);
    if (cls.prototype) line_(`${n}.prototype`, cls.prototype, log);
  }
  const K = P().Constants;
  if (K) {
    for (const key of Object.keys(K)) {
      let v;
      try {
        v = JSON.stringify(K[key]);
      } catch (e) {
        v = String(K[key]);
      }
      log(`Constants.${key}: ${v}`);
    }
  } else log("Constants: (none)");
}

/**
 * Probe (dry run): what cutting around the planned clip markers WOULD do to the timeline. Changes nothing.
 * `items` is the plan from the loaded file (planMarkers); `opts` goes to planCutSet (clips, chapters, padding, merge gap...);
 * `hint` = {mediaPath, fileName} tells which video the markers belong to.
 */
async function probeCutPlan(items, log, opts, hint) {
  const { sequence } = await activeContext();
  const t = await collectTarget(sequence, hint);
  log(`Cut plan for ${t.used.length} clip(s) of "${t.mediaName}" on V${t.trackIndex + 1} (${t.how}).`);
  if (t.elsewhere) log(`${t.elsewhere} more clip(s) of this video sit on higher video tracks and are ignored.`);
  if (t.reversed) log(`${t.reversed} reversed-speed clip(s) are ignored.`);
  const cov = C().coverage(C().planCutSet(items, { ...opts, clips: true }).ranges, t.descs);
  log(`The timeline plays source ${cov.windows.map((w) => `${C().formatTime(w.start)}-${C().formatTime(w.end)}`).join(", ") || "(nothing)"}.`);
  const set = C().planCutSet(items, Object.assign({ clips: true, chapters: true }, opts));
  const points = C().timelinePoints(set.points, t.descs);
  log(`${set.ranges.length} ${set.ranges.length === 1 ? "stretch" : "stretches"} to keep (${set.merged} merged because they touch or overlap; ${cov.inside} touch the timeline, ${cov.outside} fall outside it), ${set.chapters.length} chapters, ${set.noLength} clip markers have no length and are left out.`);
  const cuts = [];
  for (const d of t.descs) cuts.push(...C().cutsForClip(set.ranges, d));
  cuts.sort((a, b) => a.tlStart - b.tlStart);
  const kept = cuts.reduce((a, c) => a + (c.tlEnd - c.tlStart), 0);
  const total = t.descs.reduce((a, d) => a + (d.end - d.start), 0);
  log(`A razor would cut at ${points.length} timeline times. Keeping only the clips would leave ${kept.toFixed(1)} s of ${total.toFixed(1)} s.`);
  cuts.slice(0, 25).forEach((c, i) => log(`  #${i + 1} timeline ${c.tlStart.toFixed(3)} -> ${c.tlEnd.toFixed(3)} (${(c.tlEnd - c.tlStart).toFixed(1)} s) = source ${c.srcStart.toFixed(3)} -> ${c.srcEnd.toFixed(3)}  ${c.names[0] || ""}`));
  if (cuts.length > 25) log(`  ... and ${cuts.length - 25} more.`);
  log(`Audio clips with the same start and end as those video clips: ${t.linked.length ? Array.from(new Set(t.linked.map((a) => "A" + (a.track + 1)))).join(", ") : "(none found)"}`);
}

/** Runs every read-only probe in one go, one log to paste. `getItems()` returns the planned items (or null). */
async function probeAll(log, getItems, getHint) {
  const step = async (title, fn) => {
    log(`===== ${title} =====`);
    try {
      await fn();
    } catch (e) {
      log(`${title} stopped: ${msg(e)}`, true);
    }
  };
  await step("API", () => probe(log));
  await step("Clips", () => probeClips(log));
  await step("Audio", () => probeAudio(log));
  await step("Editor", () => probeEditor(log));
  await step("File detection", () => probeDetection(log));
  await step("Cut plan (dry run)", async () => {
    const items = getItems();
    if (!items || !items.length) return log("(no markers file loaded or nothing to plan, skipped)");
    await probeCutPlan(items, log, undefined, getHint ? getHint() : undefined);
  });
  await step("Classes", () => probeClasses(log));
  log("===== end of probes =====");
}

/**
 * EXPERIMENT (changes the project, Ctrl+Z undoes it, up to 3 steps): tries to split the video clip under the playhead
 * in two by overwriting its second half with the same source range, which is how a razor can be emulated when the API
 * has none. It reports what it did at each step and the clips on the track afterwards.
 * If something fails half way, the source in/out marks of the clip in the Project panel may be left set: Ctrl+Z.
 */
async function testCutAtPlayhead(log) {
  const { project, sequence } = await activeContext();
  const t = secOf(await need(sequence, "getPlayerPosition", "Sequence")());
  const vids = await videoClips(sequence, log);
  let hit;
  for (const v of vids) {
    const d = await describeClip(v.item);
    if (t > secOf(d.start) + 0.05 && t < secOf(d.end) - 0.05) {
      hit = { ...v, d };
      break;
    }
  }
  if (!hit) throw new PremiereError("The playhead is not inside a video clip (put it in the middle of one, at least a few frames from its ends).");
  const S = secOf(hit.d.start), E = secOf(hit.d.end), I = secOf(hit.d.inPoint), O = secOf(hit.d.outPoint);
  const speed = (await safe(() => read(hit.item, "speed"))) || 1;
  const srcAt = I + (t - S) * speed;
  log(`Cut test at ${t.toFixed(3)} s in V${hit.track} "${hit.d.name}" (timeline ${S.toFixed(3)} -> ${E.toFixed(3)}, source ${I.toFixed(3)} -> ${O.toFixed(3)}, speed ${speed}). The second half should play source ${srcAt.toFixed(3)} -> ${O.toFixed(3)}.`);

  const pi = await clipProjectItem(hit.item);
  if (!pi) throw new PremiereError("Could not get the clip's project item.");
  const SE = P().SequenceEditor;
  const editor = SE && typeof SE.getEditor === "function" ? await SE.getEditor(sequence) : undefined;
  if (!editor) throw new PremiereError("SequenceEditor.getEditor(sequence) is not available here: run \"Probe editor\" and send the log.");
  const overwrite = need(editor, "createOverwriteItemAction", "the sequence editor");
  const setInOut = need(pi, "createSetInOutPointsAction", "the project item");

  const audio = await audioClips(sequence, () => {});
  let aIndex = 0;
  for (const a of audio) {
    const ad = await describeClip(a.item);
    if (Math.abs(secOf(ad.start) - S) < 0.01 && Math.abs(secOf(ad.end) - E) < 0.01) {
      aIndex = a.track - 1;
      break;
    }
  }
  const oldIn = await safe(() => pi.getInPoint());
  const oldOut = await safe(() => pi.getOutPoint());
  log(`Project item in/out before: ${fmtSec(oldIn)} -> ${fmtSec(oldOut)}. Overwriting on V${hit.track}, audio track A${aIndex + 1}.`);

  await transaction(project, "LuckyTwitch cut test: source range", (compound) => {
    log(`(compound action offers: ${members(compound).join(", ")})`);
    compound.addAction(setInOut(tick(srcAt), tick(O)));
  });
  log("Step 1 ok: source in/out set to the second half.");
  let failed = null;
  try {
    await transaction(project, "LuckyTwitch cut test: overwrite", (compound) => {
      compound.addAction(overwrite(pi, tick(t), hit.track - 1, aIndex));
    });
    log("Step 2 ok: overwritten at the playhead.");
  } catch (e) {
    failed = e;
    log(`Step 2 failed: ${msg(e)}`, true);
  }
  try {
    await transaction(project, "LuckyTwitch cut test: restore source range", (compound) => {
      const oi = secOf(oldIn);
      if (Number.isFinite(oi) && oi > 0.001 && oldOut) compound.addAction(setInOut(oldIn, oldOut));
      else compound.addAction(need(pi, "createClearInOutPointsAction", "the project item")());
    });
    log("Step 3 ok: the source in/out of the project item is back.");
  } catch (e) {
    log(`Step 3 failed (the project item may keep in/out marks; clear them with Alt+I / Alt+O in the Source Monitor, or Ctrl+Z): ${msg(e)}`, true);
  }
  const after = await videoClips(sequence, log);
  log(`Video clips now: ${after.length}`);
  for (const { track, item } of after.slice(0, 12)) {
    const d = await describeClip(item);
    log(`  V${track} "${d.name}": timeline ${fmtSec(d.start)} -> ${fmtSec(d.end)}, source ${fmtSec(d.inPoint)} -> ${fmtSec(d.outPoint)}`);
  }
  const afterAudio = await audioClips(sequence, () => {});
  log(`Audio clips now: ${afterAudio.length}`);
  for (const { track, item } of afterAudio.slice(0, 12)) {
    const d = await describeClip(item);
    log(`  A${track} "${d.name}": timeline ${fmtSec(d.start)} -> ${fmtSec(d.end)}, source ${fmtSec(d.inPoint)} -> ${fmtSec(d.outPoint)}`);
  }
  log(failed ? "Result: the overwrite did not work (see above)." : "Result: look at the timeline: is there a cut at the playhead, with video and audio both split and playing on? If so, cutting at every clip is feasible. Ctrl+Z to undo (up to 3 steps).");
}

// ---------------------------------------------------------------------------------------------------------------
// SPLIT BY CLONE + TRIM. The Premiere UXP API has NO razor / "Add Edit" call (checked in the uxp-premiere-pro reference
// and confirmed by Adobe in the community forum: SequenceEditor only has clone / insert / overwrite / remove, and track
// items only have createSetStart/End/InPoint/OutPoint/Move actions). So a cut at time t is built from those pieces:
//   1. clone the clip onto a FREE track above (same time)        -> temp copy keeps every effect, speed, scale...
//   2. original: set end = t.   temp copy: set start = t (and the in point, if setStart did not move it)
//   3. clone the temp copy back down onto the original track     -> it lands in the gap [t, end]
//   4. remove the temp copy
// Premiere's UI refresh makes every timeline edit slow, so splitMany() does these 4 edits for SEVERAL clips at once
// (video + its audio, and, in cutAtClipEdges, every piece that still holds a cut point: halving rounds).
// Every step reads the result back and the run stops at the first mismatch.
// ---------------------------------------------------------------------------------------------------------------
const KIND = { video: { count: "getVideoTrackCount", list: videoClips }, audio: { count: "getAudioTrackCount", list: audioClips } };

/** Every clip of one kind with its span: [{track (0-based), item, S, E, I, O}]. */
async function spans(sequence, kind, log) {
  const out = [];
  for (const { track, item } of await KIND[kind].list(sequence, log)) {
    const d = await describeClip(item);
    out.push({ kind, track: track - 1, item, S: secOf(d.start), E: secOf(d.end), I: secOf(d.inPoint), O: secOf(d.outPoint), name: d.name, mediaName: d.mediaName, mediaPath: d.mediaPath });
  }
  return out;
}

/** Timeline start/end and source in/out of one track item, in seconds (only the four reads a cut needs). */
async function itemSpan(item) {
  return { S: secOf(await read(item, "startTime")), E: secOf(await read(item, "endTime")), I: secOf(await read(item, "inPoint")), O: secOf(await read(item, "outPoint")) };
}

/** Waits until fn() returns something ok() accepts (Premiere can need a moment to show a change). Returns the last value. */
async function waitFor(fn, ok, tries = 8, ms = 40) {
  let v;
  for (let i = 0; i < tries; i++) {
    if (i) await sleep(ms);
    v = await fn();
    if (ok(v)) return v;
  }
  return v;
}

/** The clips of ONE track (0-based index), reading only what a cut needs. Much faster than spans() inside a loop. */
async function trackSpans(sequence, kind, trackIndex) {
  const track = await need(sequence, kind === "video" ? "getVideoTrack" : "getAudioTrack", "Sequence")(trackIndex);
  const typeEnum = P().Constants && P().Constants.TrackItemType;
  const type = typeEnum && typeEnum.CLIP !== undefined ? typeEnum.CLIP : 1;
  const items = (await track.getTrackItems(type, false)) || [];
  const out = [];
  for (const item of items) {
    out.push({ kind, track: trackIndex, item, ...(await itemSpan(item)) });
  }
  return out;
}

/** The clip on `track` that has this start and end (used to find the temp copy and the second half after cloning). */
async function findSpan(sequence, kind, track, S, E, tol = 0.01) {
  return (await trackSpans(sequence, kind, track)).find((c) => Math.abs(c.S - S) < tol && Math.abs(c.E - E) < tol);
}

/** Lowest track above `c.track` with nothing in [S, E]; -1 when there is none. */
async function freeTrackAbove(sequence, c, all, log) {
  const count = await need(sequence, KIND[c.kind].count, "Sequence")();
  for (let j = c.track + 1; j < count; j++) {
    if (!all.some((o) => o.track === j && o.S < c.E - 0.001 && o.E > c.S + 0.001)) return j;
  }
  return -1;
}

const SETTLE = 30; // ms to let Premiere commit a timeline edit (reads are retried anyway)

/**
 * Splits several clips at once, each at its own time: jobs = [{c, t, free}] where `c` is a span (from spans() /
 * trackSpans()), `t` the cut time and `free` the index of an empty track of the same kind above it. Clips of one call
 * must not overlap in time on the same track (their temp copies share the workspace track). It makes 4 timeline edits
 * for the whole batch (5 if a source in point has to be set), whatever its size, and checks every result: the first
 * half must end at t, the second half must start at t and play the source from the matching position.
 */
async function splitMany(project, sequence, editor, jobs, log, tol = 0.02) {
  if (!jobs.length) return [];
  const clone = need(editor, "createCloneTrackItemAction", "the sequence editor");
  const zero = tick(0);
  const tag = (j) => `${j.c.kind[0].toUpperCase()}${j.c.track + 1} @${j.t.toFixed(3)}`;
  const cloneTo = (j, item, dir) => clone(item, zero, j.c.kind === "video" ? dir * j.up : 0, j.c.kind === "audio" ? dir * j.up : 0, false, false);
  for (const j of jobs) {
    j.speed = (await safe(() => read(j.c.item, "speed"))) || 1;
    j.srcAt = j.c.I + (j.t - j.c.S) * j.speed;
    j.up = j.free - j.c.track;
    log(`[${tag(j)}] clip ${j.c.S.toFixed(3)} -> ${j.c.E.toFixed(3)}, source ${j.c.I.toFixed(3)} -> ${j.c.O.toFixed(3)}, speed ${j.speed}; second half must play source from ${j.srcAt.toFixed(3)}; workspace track ${j.c.kind[0].toUpperCase()}${j.free + 1}.`);
  }

  // 1. temp copies on the free tracks
  await transaction(project, "LuckyTwitch split: temp copies", (comp) => {
    for (const j of jobs) comp.addAction(cloneTo(j, j.c.item, 1));
  }, SETTLE);
  for (const j of jobs) {
    j.temp = await waitFor(() => findSpan(sequence, j.c.kind, j.free, j.c.S, j.c.E), Boolean);
    if (!j.temp) throw new PremiereError(`[${tag(j)}] step 1: the temp copy did not show up on track ${j.free + 1}.`);
  }
  log(`step 1 ok: ${jobs.length} temp cop${jobs.length === 1 ? "y" : "ies"} made.`);

  // 2. original ends at t; the temp copy starts at t
  await transaction(project, "LuckyTwitch split: trim", (comp) => {
    for (const j of jobs) {
      comp.addAction(need(j.c.item, "createSetEndAction", "a track item")(tick(j.t)));
      comp.addAction(need(j.temp.item, "createSetStartAction", "a track item")(tick(j.t)));
    }
  }, SETTLE);
  const fix = [];
  for (const j of jobs) {
    j.tempNow = await waitFor(() => itemSpan(j.temp.item), (x) => Math.abs(x.S - j.t) <= tol);
    if (Math.abs(j.tempNow.I - j.srcAt) > tol) fix.push(j);
  }
  log(`step 2 ok: trimmed${fix.length ? `; ${fix.length} source in point(s) still to set` : " (setStart moved the source in point too)"}.`);
  if (fix.length) {
    await transaction(project, "LuckyTwitch split: in point", (comp) => {
      for (const j of fix) comp.addAction(need(j.temp.item, "createSetInPointAction", "a track item")(tick(j.srcAt)));
    }, SETTLE);
    for (const j of fix) j.tempNow = await waitFor(() => itemSpan(j.temp.item), (x) => Math.abs(x.I - j.srcAt) <= tol);
  }

  // 3. temp copies back down onto the original tracks, into the gap
  await transaction(project, "LuckyTwitch split: copies back", (comp) => {
    for (const j of jobs) comp.addAction(cloneTo(j, j.temp.item, -1));
  }, SETTLE);
  const problems = [];
  for (const j of jobs) {
    j.second = await waitFor(() => findSpan(sequence, j.c.kind, j.c.track, j.t, j.c.E, Math.max(tol, 0.05)), Boolean);
    const first = await waitFor(() => itemSpan(j.c.item), (x) => Math.abs(x.E - j.t) <= tol, 5);
    const bad = [];
    if (Math.abs(first.E - j.t) > tol) bad.push(`the first half ends at ${first.E.toFixed(3)} (wanted ${j.t.toFixed(3)})`);
    if (!j.second) bad.push("the second half did not appear on the original track");
    else {
      if (Math.abs(j.second.S - j.t) > tol) bad.push(`the second half starts at ${j.second.S.toFixed(3)} (wanted ${j.t.toFixed(3)})`);
      if (Math.abs(j.second.I - j.srcAt) > tol) bad.push(`the second half plays source from ${j.second.I.toFixed(3)} (wanted ${j.srcAt.toFixed(3)})`);
    }
    if (bad.length) problems.push(`[${tag(j)}] ${bad.join("; ")}`);
  }
  if (problems.length) throw new PremiereError(`check failed: ${problems.join(" | ")}. Stopped. Temp copies are still on the workspace tracks; undo (Ctrl+Z) or use the backup sequence.`);
  log("step 3 ok: second halves are in place and checked.");

  // 4. remove the temp copies (one edit for all)
  await transaction(project, "LuckyTwitch split: remove temp copies", (comp) => {
    P().TrackItemSelection.createEmptySelection((sel) => {
      for (const j of jobs) sel.addItem(j.temp.item, false);
      const mt = P().Constants && P().Constants.MediaType;
      comp.addAction(need(editor, "createRemoveItemsAction", "the sequence editor")(sel, false, mt ? mt.ANY : 0, false));
    });
  }, SETTLE);
  log("step 4 ok: temp copies removed.");
  return jobs.map((j) => j.second);
}

/** The sequence's frame grid: cuts can only be made on frames. snap(t) rounds seconds to the nearest frame. */
async function frameGrid(sequence) {
  const tb = Number(await safe(() => sequence.getTimebase()));
  const frame = Number.isFinite(tb) && tb > 0 ? tb / TICKS_PER_SECOND : 0;
  const ok = frame > 1 / 240 && frame < 1 / 10; // anything else is not a believable frame length
  return { frame: ok ? frame : 0, snap: (t) => (ok ? Math.round(t / frame) * frame : t) };
}

/**
 * Which timeline clips does a markers file apply to? Every video clip that plays the media the file belongs to (not just one clip),
 * so it also works on a timeline that was already cut or trimmed: each clip knows which part of the source it plays.
 * hint = {mediaPath, fileName}: the video the file was found next to, else the video named like the file, else the selected
 * (or first) clip's video. Only the lowest video track holding that media is used (higher tracks are the workspace).
 * Returns {vids, auds, used, linked, descs, trackIndex, elsewhere, reversed, mediaName, how}.
 */
async function collectTarget(sequence, hint, log) {
  const vids = await spans(sequence, "video", () => {});
  const auds = await spans(sequence, "audio", () => {});
  const h = hint || {};
  const key = (c) => String(c.mediaPath || c.mediaName || "").replace(/\\/g, "/").toLowerCase();
  const tryKey = (k, how) => {
    if (!k) return null;
    const matches = vids.filter((c) => key(c) === k);
    return matches.length ? { matches, how } : null;
  };
  const norm = (p) => String(p || "").replace(/\\/g, "/").toLowerCase();
  let found = h.mediaPath ? tryKey(norm(h.mediaPath), "the video the markers file was found next to") : null;
  if (!found && h.fileName) {
    const m = vids.find((c) => C().markersNameMatchesMedia(h.fileName, c.mediaPath || c.mediaName));
    if (m) found = tryKey(key(m), `the video named like "${h.fileName}"`);
  }
  if (!found) {
    const target = await pickTargetClip(sequence, () => {});
    const d = await describeClip(target.item);
    found = tryKey(norm(d.mediaPath || d.mediaName), `${target.where}'s video`);
  }
  if (!found) throw new PremiereError("There is no video clip on the timeline that plays this markers file's video. Put the video on the timeline (and select it) first.");
  const matches = found.matches;
  for (const c of matches) {
    c.speed = (await safe(() => read(c.item, "speed"))) || 1;
    c.reversed = !!(await safe(() => read(c.item, "isSpeedReversed")));
  }
  const usable = matches.filter((c) => !c.reversed);
  if (!usable.length) throw new PremiereError("Every clip of this video on the timeline is reversed; cutting reversed clips is not supported.");
  const trackIndex = Math.min(...usable.map((c) => c.track));
  const used = usable.filter((c) => c.track === trackIndex).sort((a, b) => a.S - b.S);
  const linked = auds.filter((a) => used.some((c) => Math.abs(a.S - c.S) < 0.01 && Math.abs(a.E - c.E) < 0.01));
  const descs = used.map((c) => ({ start: c.S, end: c.E, inPoint: c.I, outPoint: c.O, speed: c.speed }));
  return { vids, auds, used, linked, descs, trackIndex, elsewhere: usable.length - used.length, reversed: matches.length - usable.length, mediaName: used[0].mediaName || used[0].name, how: found.how };
}

/** For the panel: what the timeline plays of the markers file's video (read-only). Returns {descs, mediaName, trackIndex, elsewhere, reversed, how}. */
async function inspectTimeline(hint) {
  const { sequence } = await activeContext();
  const t = await collectTarget(sequence, hint);
  return { descs: t.descs, mediaName: t.mediaName, trackIndex: t.trackIndex, elsewhere: t.elsewhere, reversed: t.reversed, how: t.how };
}

/**
 * Cuts every timeline clip of the markers file's video (and the audio clips with the same start and end) at the planned points:
 * the start and end of every clip (opts.clips, default true) and/or the boundaries of every chapter (opts.chapters).
 * `items` are the planned markers; opts = {backup, clips, chapters, plan (padding, merge gap), hint}. Nothing is deleted, only split.
 * Points are source times mapped through each clip's own in point / speed, so it works after you deleted or trimmed parts first, and
 * a point that already has a cut is skipped (running it twice is harmless).
 *
 * Speed: instead of one cut after the other, the cut points are handled in HALVING ROUNDS. Round 1 cuts each piece at its middle
 * cut point, round 2 cuts both halves at their middle points at the same time; and so on, so 38 cut points need 6 rounds of 4
 * timeline edits instead of 38 cuts of 8. Every round is verified; the first failure stops the run.
 * Returns {cuts, skipped, points, rounds, clips}.
 */
async function cutAtClipEdges(items, opts, log) {
  const o = opts || {};
  const { project, sequence } = await activeContext();
  const t = await collectTarget(sequence, o.hint);
  const { vids, auds, used } = t;
  const grid = await frameGrid(sequence);
  const set = C().planCutSet(items, Object.assign({}, o.plan, { clips: o.clips !== false, chapters: !!o.chapters }));
  const edge = Math.max(0.01, grid.frame / 2);
  const tol = grid.frame ? Math.max(0.02, grid.frame) : 0.06;
  let pending = Array.from(new Set(C().timelinePoints(set.points, t.descs).map((p) => Math.round(grid.snap(p.tl) * 1e6) / 1e6)))
    .filter((x) => used.some((c) => x > c.S + edge && x < c.E - edge))
    .sort((a, b) => a - b);
  const total = pending.length;
  const rounds = Math.ceil(Math.log2(total + 1));
  const win = C().coverage(set.ranges, t.descs).windows.map((w) => `${C().formatTime(w.start)}-${C().formatTime(w.end)}`).join(", ");
  const what = [o.clips !== false ? `${set.ranges.length} clips` : "", o.chapters ? `${set.chapters.length} chapters` : ""].filter(Boolean).join(" + ");
  log(`Cutting ${used.length} clip${used.length === 1 ? "" : "s"} of "${t.mediaName}" on V${t.trackIndex + 1} (${t.how}); they play source ${win || "(nothing)"}. ${what} give ${total} cut points${grid.frame ? ` (snapped to frames of ${(grid.frame * 1000).toFixed(2)} ms)` : " (frame length unknown: cuts are not snapped)"}.`);
  if (t.elsewhere) log(`(${t.elsewhere} more clip(s) of this video sit on higher video tracks: ignored.)`);
  if (t.reversed) log(`(${t.reversed} reversed-speed clip(s): ignored.)`);
  if (!total) return { cuts: 0, skipped: 0, points: 0, rounds: 0, clips: used.length };

  // The video clips and the audio clips with the same start and end are cut together, each on its own empty workspace track above.
  const spanOf = (list) => ({ S: Math.min(...list.map((c) => c.S)), E: Math.max(...list.map((c) => c.E)) });
  const free = new Map(); // "video:0" -> index of an empty track above
  const vSpan = { kind: "video", track: t.trackIndex, ...spanOf(used) };
  const vFree = await freeTrackAbove(sequence, vSpan, vids, () => {});
  if (vFree < 0) throw new PremiereError(`There is no empty video track above V${t.trackIndex + 1}. Add one (right-click the track header > Add Track), keep it empty, and try again.`);
  free.set(`video:${t.trackIndex}`, vFree);
  const aTracks = Array.from(new Set(t.linked.map((a) => a.track))).sort((a, b) => a - b);
  for (const at of aTracks) {
    const aSpan = { kind: "audio", track: at, ...spanOf(t.linked.filter((a) => a.track === at)) };
    const f = await freeTrackAbove(sequence, aSpan, auds, () => {});
    if (f < 0) throw new PremiereError(`There is no empty audio track above A${at + 1}. Add one (right-click the track header > Add Track), keep it empty, and try again.`);
    free.set(`audio:${at}`, f);
  }
  const SE = P().SequenceEditor;
  const editor = SE && typeof SE.getEditor === "function" ? await SE.getEditor(sequence) : undefined;
  if (!editor) throw new PremiereError("SequenceEditor.getEditor(sequence) is not available here.");
  log(`Video V${t.trackIndex + 1} and ${aTracks.length} audio track(s) (${aTracks.map((a) => "A" + (a + 1)).join(", ") || "none"}) will be cut in about ${rounds} rounds, using empty tracks above as workspace.`);

  if (o.backup) {
    try {
      await transaction(project, "LuckyTwitch: backup copy of the sequence", (comp) => comp.addAction(need(sequence, "createCloneAction", "Sequence")()));
      log("Made a backup copy of the sequence (it is in the Project panel).");
    } catch (e) {
      throw new PremiereError(`Could not make the backup copy (${msg(e)}). Untick the backup box to cut without one, or duplicate the sequence yourself first.`);
    }
  }

  let done = 0, skipped = 0, round = 0;
  const quiet = (text, isError) => { if (isError) log(text, true); };
  while (pending.length) {
    round++;
    const vNow = await trackSpans(sequence, "video", t.trackIndex);
    const aNow = new Map();
    for (const at of aTracks) aNow.set(at, await trackSpans(sequence, "audio", at));
    // Group the pending points by the video piece that holds them; each piece is cut at its middle point this round.
    const groups = new Map();
    const rest = [];
    for (const x of pending) {
      const piece = vNow.find((c) => x > c.S + edge && x < c.E - edge);
      if (!piece) { skipped++; continue; } // there is already a cut here
      if (!groups.has(piece)) groups.set(piece, []);
      groups.get(piece).push(x);
    }
    const jobs = [];
    let cutsThisRound = 0;
    for (const [piece, ts] of groups) {
      const mid = Math.floor(ts.length / 2);
      const x = ts[mid];
      rest.push(...ts.filter((_, i) => i !== mid));
      cutsThisRound++;
      jobs.push({ c: piece, t: x, free: free.get(`video:${t.trackIndex}`) });
      for (const at of aTracks) {
        const ap = aNow.get(at).find((c) => Math.abs(c.S - piece.S) < 0.05 && Math.abs(c.E - piece.E) < 0.05);
        if (ap) jobs.push({ c: ap, t: x, free: free.get(`audio:${at}`) });
        else log(`(A${at + 1} has no clip matching the video piece ${piece.S.toFixed(3)} -> ${piece.E.toFixed(3)}: left uncut there)`);
      }
    }
    if (!jobs.length) break;
    log(`Round ${round} of about ${rounds}: cutting ${cutsThisRound} piece${cutsThisRound === 1 ? "" : "s"}...`);
    try {
      await splitMany(project, sequence, editor, jobs, round === 1 ? log : quiet, tol);
    } catch (e) {
      throw new PremiereError(`Stopped after ${done} of ${total} cuts (round ${round}): ${msg(e)}`);
    }
    done += cutsThisRound;
    log(`Round ${round} done: ${done} of ${total} cuts.`);
    pending = rest.sort((a, b) => a - b);
  }
  return { cuts: done, skipped, points: total, rounds: round, clips: used.length };
}

/**
 * EXPERIMENT: splits the video clip under the playhead (and the audio clips with the same start and end) by cloning
 * and trimming. Every step is logged with what Premiere reports afterwards.
 */
async function testSplitAtPlayhead(log) {
  const { project, sequence } = await activeContext();
  const t = secOf(await need(sequence, "getPlayerPosition", "Sequence")());
  const vids = await spans(sequence, "video", log);
  const hit = vids.find((c) => t > c.S + 0.05 && t < c.E - 0.05);
  if (!hit) throw new PremiereError("The playhead is not inside a video clip (put it a few frames inside one).");
  const allA = await spans(sequence, "audio", () => {});
  const auds = allA.filter((a) => Math.abs(a.S - hit.S) < 0.01 && Math.abs(a.E - hit.E) < 0.01);
  const SE = P().SequenceEditor;
  const editor = SE && typeof SE.getEditor === "function" ? await SE.getEditor(sequence) : undefined;
  if (!editor) throw new PremiereError("SequenceEditor.getEditor(sequence) is not available here.");
  log(`Tracks in the sequence: ${await safe(() => sequence.getVideoTrackCount())} video, ${await safe(() => sequence.getAudioTrackCount())} audio.`);
  log(`Split test at ${t.toFixed(3)} s: video V${hit.track + 1} \"${hit.name}\" and ${auds.length} audio clip(s) with the same start/end (${auds.map((a) => "A" + (a.track + 1)).join(", ") || "none"}).`);
  const jobs = [];
  for (const c of [hit, ...auds]) {
    const free = await freeTrackAbove(sequence, c, c.kind === "video" ? vids : allA, () => {});
    if (free < 0) log(`[${c.kind[0].toUpperCase()}${c.track + 1}] skipped: there is no empty track above it to use as a workspace (add an empty ${c.kind} track and try again).`, true);
    else jobs.push({ c, t, free });
  }
  try {
    await splitMany(project, sequence, editor, jobs, log);
  } catch (e) {
    log(`Split stopped: ${msg(e)}`, true);
  }
  const after = await spans(sequence, "video", () => {});
  log(`Video clips now: ${after.length}`);
  after.slice(0, 12).forEach((c) => log(`  V${c.track + 1} \"${c.name}\": ${c.S.toFixed(3)} -> ${c.E.toFixed(3)}, source ${c.I.toFixed(3)} -> ${c.O.toFixed(3)}`));
  const afterA = await spans(sequence, "audio", () => {});
  log(`Audio clips now: ${afterA.length}`);
  afterA.slice(0, 12).forEach((c) => log(`  A${c.track + 1} \"${c.name}\": ${c.S.toFixed(3)} -> ${c.E.toFixed(3)}, source ${c.I.toFixed(3)} -> ${c.O.toFixed(3)}`));
  log("Result: is there a cut at the playhead with video and audio both split, the second half playing on seamlessly, and no leftover clip on the track above? Ctrl+Z undoes it (several steps).");
}

const LT_ADAPTER_API = {
  importMarkers, importMarkersToClip, addMarkers, removeMarkers, findMarkersFile, inspectTimeline,
  addTestMarkers, probe, probeClips, probeAudio, probeEditor, probeClasses, probeDetection, probeCutPlan, probeAll,
  addClipTestMarkers, testCutAtPlayhead, testSplitAtPlayhead, cutAtClipEdges, PremiereError, _setPremiere: (m) => { pproModule = m; },
};
if (typeof module !== "undefined" && module.exports) module.exports = LT_ADAPTER_API;
if (typeof window !== "undefined") window.LTAdapter = LT_ADAPTER_API;
