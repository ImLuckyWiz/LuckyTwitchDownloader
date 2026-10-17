"use strict";
/*
 * Everything that talks to Premiere Pro lives in this file, so when Adobe changes the UXP API (or a call turns out
 * to behave differently from what the docs say) this is the only place to fix.
 *
 * STATUS (0.7.0): NEW and only covered by the fake-timeline tests so far (test/cut.test.js): deleteGaps (ripple delete of the pieces between the
 * clips, chunked and verified after every chunk), probeGapPlan, and testRippleDelete, the experiment that measures what
 * createRemoveItemsAction(selection, ripple, mediaType, shiftOverLapping) really does on a real Premiere. The cut engine below is unchanged.
 *
 * STATUS (0.6.0): markers on the sequence / on the clip and their coloring, and the cut engine (clone + trim in halving rounds, on every
 * clip of the markers file's video, also on a trimmed timeline), were verified on a real Premiere in 0.5.0. NEW in 0.6.0 and only covered by
 * the fake-timeline tests so far (test/cut.test.js, test/adapter.test.js): the Project-panel selection (ProjectUtils.getSelection), markers
 * on the sequence mapped through the clip that plays them, the shared backup, the progress / stop hooks of the cut engine, and the
 * workspace-track check of the pre-flight. The Troubleshooting section of the panel has a probe for the selection.
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

async function activeProject() {
  const project = await P().Project.getActiveProject();
  if (!project) throw new PremiereError("No project is open.");
  return project;
}

async function activeContext() {
  const project = await activeProject();
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

const normPath = (p) => String(p || "").replace(/\\/g, "/").toLowerCase();

/** Does a clip (media path / name) belong to this markers file? hint = {mediaPath, fileName}. */
function clipMatchesHint(c, hint) {
  if (!hint) return false;
  if (hint.mediaPath && c.mediaPath && normPath(c.mediaPath) === normPath(hint.mediaPath)) return true;
  return !!(hint.fileName && C().markersNameMatchesMedia(hint.fileName, c.mediaPath || c.name));
}

/**
 * Every selection object this Premiere will give for the Project panel, as [{via, sel}]: ProjectUtils.getSelection(project), and, because
 * that one can come back empty (0.6.0 probe: "(none)"), the selection of each Project panel by its view id
 * (ProjectUtils.getProjectViewIds + getSelectionFromViewId). Never throws.
 */
async function selectionSources(project) {
  const PU = P().ProjectUtils;
  const out = [];
  if (!PU) return out;
  if (typeof PU.getSelection === "function") {
    const sel = await safe(() => PU.getSelection(project));
    if (sel) out.push({ via: "getSelection(project)", sel });
  }
  if (typeof PU.getProjectViewIds === "function" && typeof PU.getSelectionFromViewId === "function") {
    const ids = asArray(await safe(() => PU.getProjectViewIds())) || [];
    for (const id of ids) {
      const sel = await safe(() => PU.getSelectionFromViewId(id));
      if (sel) out.push({ via: `getSelectionFromViewId(${id})`, sel });
    }
  }
  return out;
}

/** The items inside a selection object (an array, or an object with items / getItems()). */
async function selectionItems(sel) {
  return asArray(sel) || asArray(await safe(() => read(sel, "items"))) || [];
}

/**
 * The clips selected in the Project panel, as [{pi, name, mediaPath}]. Bins, sequences and anything without a media file are left out.
 * The first selection source that holds clips wins. Never throws: the calls may be missing on a build, or nothing may be selected.
 */
async function projectSelectionClips(project) {
  for (const { sel } of await selectionSources(project)) {
    const out = [];
    for (const item of await selectionItems(sel)) {
      const CP = P().ClipProjectItem;
      const pi = (CP && typeof CP.cast === "function" ? await safe(() => CP.cast(item)) : undefined) || item;
      const mediaPath = await safe(() => read(pi, "mediaFilePath"));
      if (typeof mediaPath !== "string" || !mediaPath) continue;
      out.push({ pi, name: (await safe(() => read(pi, "name"))) || C().baseName(mediaPath), mediaPath });
    }
    if (out.length) return out;
  }
  return [];
}

/**
 * Where markers go. placement "sequence": the active sequence, which needs the file's video on the timeline (descs say which part of
 * the source each clip plays, so every marker can be mapped through the clip that plays it). placement "clip": the SOURCE of a clip
 * (the markers follow your cuts), looked for in this order: the clip selected in the Project panel that is this file's video, the file's
 * video on the timeline, any clip selected in the Project panel, the selected (else first) clip on the timeline. The Project-panel
 * routes need no sequence, so markers can be added before the video is on the timeline.
 */
async function resolveOwner(opts, log) {
  const o = opts || {};
  const project = await activeProject();
  const sequence = await safe(() => project.getActiveSequence());
  if (o.placement === "sequence") {
    if (!sequence) throw new PremiereError("There is no active sequence. Open one in the Timeline and try again.");
    let t;
    try {
      t = await collectTarget(sequence, o.hint);
    } catch (e) {
      throw new PremiereError(`Markers on the sequence need the file's video on the timeline, to know where each one goes (${msg(e)}). Put the video on the timeline, or set Markers go: on the clip.`);
    }
    log(`Mapping the markers through the clip(s) that play them (${t.how}).`);
    return { project, sequence, owner: sequence, what: "the active sequence", descs: t.descs };
  }
  const picked = await projectSelectionClips(project);
  let choice = picked.find((c) => clipMatchesHint(c, o.hint));
  let where = "the clip selected in the Project panel";
  if (!choice && sequence) {
    const t = await safe(() => collectTarget(sequence, o.hint));
    const pi = t && (await clipProjectItem(t.used[0].item));
    if (pi) {
      choice = { pi, name: t.mediaName };
      where = `the file's video on the timeline (${t.how})`;
    }
  }
  if (!choice && picked.length) {
    choice = picked[0];
    where = picked.length === 1 ? "the clip selected in the Project panel" : "the first of the clips selected in the Project panel";
  }
  if (!choice && sequence) {
    const target = await safe(() => pickTargetClip(sequence, () => {}));
    const pi = target && (await clipProjectItem(target.item));
    if (pi) {
      const d = await describeClip(target.item);
      choice = { pi, name: d.mediaName || d.name };
      where = target.where;
    }
  }
  if (!choice || !choice.pi) throw new PremiereError("There is no clip to put the markers on. Select the video in the Project panel, or put it on the timeline.");
  log(`Target clip (${where}): "${choice.name}".`);
  return { project, sequence, owner: choice.pi, what: `the clip "${choice.name}"`, clipName: choice.name };
}

/** The items as they go onto the owner: on a clip, source time as it is; on the sequence, mapped through the clips that play them. */
function itemsForOwner(items, t, log) {
  if (!t.descs) return { list: items, outside: 0 };
  const m = C().mapItemsToTimeline(items, t.descs);
  if (m.outside) log(`${m.outside === 1 ? "1 marker is" : `${m.outside} markers are`} outside what the timeline plays and left out.`);
  return { list: m.items, outside: m.outside };
}

/**
 * The one entry point for adding. opts = {placement: "clip" | "sequence", hint: {mediaPath, fileName}}. On a clip a marker at part-time t
 * goes to source-time t (no offset). On the sequence it goes where the clip that plays source-time t has it on the timeline.
 * Returns {added, skipped, what, outside}.
 */
async function addMarkers(items, opts, log) {
  const o = opts || {};
  const t = await resolveOwner(o, log);
  const { list, outside } = itemsForOwner(items, t, log);
  if (!list.length) throw new PremiereError("None of the markers falls inside what the timeline plays, so there is nothing to add.");
  const label = o.placement === "sequence" ? "LuckyTwitch: add markers" : "LuckyTwitch: add markers to clip";
  const r = await addAndColor(t.project, t.owner, list, label, log);
  return { ...r, what: t.what, outside };
}

/** Read-only: what addMarkers would do, as {what, total, present, outside}: how many of the markers are already on the target. */
async function checkMarkers(items, opts, log) {
  const t = await resolveOwner(opts, log || (() => {}));
  const { list, outside } = itemsForOwner(items, t, () => {});
  const taken = (await listMarkers(t.owner, undefined, 1)).slice();
  let present = 0;
  for (const it of list) {
    const i = taken.findIndex((m) => sameMarker(m, it));
    if (i >= 0) {
      taken.splice(i, 1);
      present++;
    }
  }
  return { what: t.what, total: list.length, present, outside };
}

/** Removes the markers (same name and time as `items`) that a previous import put on the target. One undo step. Returns the number removed. */
async function removeMarkers(items, opts, log) {
  const o = opts || {};
  const t = await resolveOwner(o, log);
  const { list } = itemsForOwner(items, t, log);
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

/**
 * Where to look, in order: [{where, folder, mediaName}]: next to the video of the target clip on the timeline, next to the clip selected in the
 * Project panel (this is what finds the file before the video is on the timeline; no sequence needed), next to the Premiere project.
 * `why` collects what was found, for the log.
 */
async function detectionTargets(why) {
  const project = await activeProject();
  const sequence = await safe(() => project.getActiveSequence());
  const out = [];
  let mediaName;
  let mediaPathOfTarget;
  if (sequence) {
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
  } else why.push("no active sequence (fine: the Project panel and the project folder are still searched)");
  const picked = (await projectSelectionClips(project))[0];
  if (picked && picked.mediaPath !== mediaPathOfTarget) {
    why.push(`clip selected in the Project panel: ${picked.mediaPath}`);
    out.push({ where: "next to the clip selected in the Project panel", folder: C().dirName(picked.mediaPath), mediaName: C().baseName(picked.mediaPath), mediaPath: picked.mediaPath });
    mediaName = mediaName || C().baseName(picked.mediaPath);
    mediaPathOfTarget = mediaPathOfTarget || picked.mediaPath;
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
  const grid = await frameGrid(sequence);
  const points = C().pendingCutPoints(set.points, t.descs, grid.frame); // what the cut would still have to do (already-cut points are not counted)
  log(`${set.ranges.length} ${set.ranges.length === 1 ? "stretch" : "stretches"} to keep (${set.merged} merged because they touch or overlap; ${cov.inside} touch the timeline, ${cov.outside} fall outside it), ${set.chapters.length} chapters, ${set.noLength} clip markers have no length and are left out.`);
  const cuts = [];
  for (const d of t.descs) cuts.push(...C().cutsForClip(set.ranges, d));
  cuts.sort((a, b) => a.tlStart - b.tlStart);
  // on an already cut timeline one stretch is split over several pieces: show it as one line
  for (let i = cuts.length - 1; i > 0; i--) {
    const a = cuts[i - 1], b = cuts[i];
    if (Math.abs(b.tlStart - a.tlEnd) < 0.001 && Math.abs(b.srcStart - a.srcEnd) < 0.001) {
      a.tlEnd = b.tlEnd;
      a.srcEnd = b.srcEnd;
      cuts.splice(i, 1);
    }
  }
  const kept = cuts.reduce((a, c) => a + (c.tlEnd - c.tlStart), 0);
  const total = t.descs.reduce((a, d) => a + (d.end - d.start), 0);
  log(`${points.length ? `The cut would still make ${points.length} cuts` : "No cut left to make (every point already has one, or falls outside the timeline)"}. Keeping only the clips would leave ${kept.toFixed(1)} s of ${total.toFixed(1)} s.`);
  cuts.slice(0, 25).forEach((c, i) => log(`  #${i + 1} timeline ${c.tlStart.toFixed(3)} -> ${c.tlEnd.toFixed(3)} (${(c.tlEnd - c.tlStart).toFixed(1)} s) = source ${c.srcStart.toFixed(3)} -> ${c.srcEnd.toFixed(3)}  ${c.names[0] || ""}`));
  if (cuts.length > 25) log(`  ... and ${cuts.length - 25} more.`);
  log(`Audio clips with the same start and end as those video clips: ${t.linked.length ? Array.from(new Set(t.linked.map((a) => "A" + (a.track + 1)))).join(", ") : "(none found)"}`);
}

/** Runs every read-only probe in one go, one log to paste. `getItems()` returns the planned items (or null). */
async function probeAll(log, getItems, getHint, getGapOpts) {
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
  await step("Project selection", () => probeSelection(log));
  await step("Cut plan (dry run)", async () => {
    const items = getItems();
    if (!items || !items.length) return log("(no markers file loaded or nothing to plan, skipped)");
    await probeCutPlan(items, log, undefined, getHint ? getHint() : undefined);
  });
  await step("Gap plan (dry run)", async () => {
    const items = getItems();
    if (!items || !items.length) return log("(no markers file loaded or nothing to plan, skipped)");
    await probeGapPlan(items, log, getGapOpts ? getGapOpts() : undefined, getHint ? getHint() : undefined);
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

const spanOf = (list) => ({ S: Math.min(...list.map((c) => c.S)), E: Math.max(...list.map((c) => c.E)) });

/**
 * Where the cut engine puts its temporary copies: for the video track being cut, and for each audio track holding the linked audio, the
 * lowest EMPTY track above (-1 = there is none). `t` is what collectTarget returned. Read-only; the pre-flight and the engine both use it.
 * Returns {videoTrack, video, audio: [{track, free}]} (all 0-based).
 */
async function workspaceFor(sequence, t) {
  const vSpan = { kind: "video", track: t.trackIndex, ...spanOf(t.used) };
  const video = await freeTrackAbove(sequence, vSpan, t.vids, () => {});
  const audio = [];
  for (const at of Array.from(new Set(t.linked.map((a) => a.track))).sort((a, b) => a - b)) {
    const aSpan = { kind: "audio", track: at, ...spanOf(t.linked.filter((a) => a.track === at)) };
    audio.push({ track: at, free: await freeTrackAbove(sequence, aSpan, t.auds, () => {}) });
  }
  return { videoTrack: t.trackIndex, video, audio };
}

// ---- the backup copy of the sequence: ONE per run -------------------------------------------------------------
// "Do it all" makes exactly one (forced) and tells the cut not to make its own. The individual cut buttons skip theirs when this panel
// already made one of the same sequence a short while ago in this session. The sequence is told apart by its guid (else its name); when
// neither can be read the buttons always make a backup, like in 0.5.0.
const BACKUP_FRESH_MS = 30 * 60 * 1000;
let lastBackup = null; // {key, at}

async function sequenceKey(sequence) {
  for (const name of ["guid", "sequenceID", "name"]) {
    const v = await safe(() => read(sequence, name));
    const text = v === undefined || v === null ? "" : String(v);
    if (text && text !== "[object Object]") return text;
  }
  return "";
}

/** Makes the backup copy unless a fresh one exists (force = always). Returns true when one was made. Throws when Premiere refuses. */
async function ensureBackup(project, sequence, log, force) {
  const key = await sequenceKey(sequence);
  if (!force && key && lastBackup && lastBackup.key === key && Date.now() - lastBackup.at < BACKUP_FRESH_MS) {
    log(`Skipped the backup: one was made ${Math.max(1, Math.round((Date.now() - lastBackup.at) / 60000))} min ago in this session (it is in the Project panel).`);
    return false;
  }
  try {
    await transaction(project, "LuckyTwitch: backup copy of the sequence", (comp) => comp.addAction(need(sequence, "createCloneAction", "Sequence")()));
  } catch (e) {
    throw new PremiereError(`Could not make the backup copy (${msg(e)}). Untick the backup box to cut without one, or duplicate the sequence yourself first.`);
  }
  lastBackup = { key, at: Date.now() };
  log("Made a backup copy of the sequence (it is in the Project panel).");
  return true;
}

/** The one backup of a "Do it all" run (always made). */
async function backupSequence(log) {
  const { project, sequence } = await activeContext();
  return ensureBackup(project, sequence, log || (() => {}), true);
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

/**
 * For the panel and the pre-flight: what the timeline plays of the markers file's video, the frame length, and the workspace tracks the
 * cut would use (read-only). Returns {descs, mediaName, trackIndex, elsewhere, reversed, how, frame, workspace, audioUnmatched}.
 * audioUnmatched (0.7.0): how many (video piece, linked audio track) pairs have no audio piece with the same start and end; the delete
 * refuses while it is above 0, because it would leave that audio behind.
 */
async function inspectTimeline(hint) {
  const { sequence } = await activeContext();
  const t = await collectTarget(sequence, hint);
  const grid = await frameGrid(sequence);
  const workspace = await workspaceFor(sequence, t);
  return { descs: t.descs, mediaName: t.mediaName, trackIndex: t.trackIndex, elsewhere: t.elsewhere, reversed: t.reversed, how: t.how, frame: grid.frame, workspace, audioUnmatched: pairPieces(t).unmatched };
}

/**
 * Cuts every timeline clip of the markers file's video (and the audio clips with the same start and end) at the planned points:
 * the start and end of every clip (opts.clips, default true) and/or the boundaries of every chapter (opts.chapters).
 * `items` are the planned markers; opts = {backup, clips, chapters, plan (padding, merge gap, min / max), hint, onProgress, shouldStop}.
 * Nothing is deleted, only split. Points are source times mapped through each clip's own in point / speed, so it works after you deleted
 * or trimmed parts first, and a point that already has a cut is skipped (running it twice is harmless).
 *
 * Speed: instead of one cut after the other, the cut points are handled in HALVING ROUNDS. Round 1 cuts each piece at its middle
 * cut point, round 2 cuts both halves at their middle points at the same time; and so on, so 38 cut points need 6 rounds of 4
 * timeline edits instead of 38 cuts of 8. Every round is verified; the first failure stops the run.
 *
 * onProgress({round, rounds, done, total}) is called when the plan is known and around every round. shouldStop() is asked before every
 * round: when it says true the run finishes the round it is in (a round is never cut short) and returns {stopped: true}.
 * opts.backup: make the backup copy first, unless a fresh one exists (see ensureBackup); "Do it all" makes its own and passes false.
 * Returns {cuts, skipped, points, rounds, clips, stopped}. A failure throws a PremiereError with .state = {done, total, round, leftover}.
 */
async function cutAtClipEdges(items, opts, log) {
  const o = opts || {};
  const { project, sequence } = await activeContext();
  const t = await collectTarget(sequence, o.hint);
  const { used } = t;
  const grid = await frameGrid(sequence);
  const set = C().planCutSet(items, Object.assign({}, o.plan, { clips: o.clips !== false, chapters: !!o.chapters }));
  const edge = Math.max(0.01, grid.frame / 2);
  const tol = grid.frame ? Math.max(0.02, grid.frame) : 0.06;
  let pending = C().pendingCutPoints(set.points, t.descs, grid.frame);
  const total = pending.length;
  const rounds = C().roundsFor(pending, t.descs, grid.frame);
  let done = 0, skipped = 0, round = 0;
  const progress = (extra) => {
    if (!o.onProgress) return;
    try {
      o.onProgress({ round, rounds, done, total, ...extra });
    } catch (e) {
      /* a broken progress display must never stop a cut */
    }
  };
  const stopAsked = () => !!(o.shouldStop && o.shouldStop());
  const win = C().coverage(set.ranges, t.descs).windows.map((w) => `${C().formatTime(w.start)}-${C().formatTime(w.end)}`).join(", ");
  const what = [o.clips !== false ? `${set.ranges.length} clips` : "", o.chapters ? `${set.chapters.length} chapters` : ""].filter(Boolean).join(" + ");
  log(`Cutting ${used.length} clip${used.length === 1 ? "" : "s"} of "${t.mediaName}" on V${t.trackIndex + 1} (${t.how}); they play source ${win || "(nothing)"}. ${what} give ${total} cut points${grid.frame ? ` (snapped to frames of ${(grid.frame * 1000).toFixed(2)} ms)` : " (frame length unknown: cuts are not snapped)"}.`);
  if (t.elsewhere) log(`(${t.elsewhere} more clip(s) of this video sit on higher video tracks: ignored.)`);
  if (t.reversed) log(`(${t.reversed} reversed-speed clip(s): ignored.)`);
  progress({ phase: "plan" });
  if (!total) return { cuts: 0, skipped: 0, points: 0, rounds: 0, clips: used.length, stopped: false };
  if (stopAsked()) return { cuts: 0, skipped: 0, points: total, rounds: 0, clips: used.length, stopped: true };

  // The video clips and the audio clips with the same start and end are cut together, each on its own empty workspace track above.
  const ws = await workspaceFor(sequence, t);
  if (ws.video < 0) throw new PremiereError(`There is no empty video track above V${t.trackIndex + 1}. Add one (right-click the track header > Add Track), keep it empty, and try again.`);
  const free = new Map(); // "video:0" -> index of an empty track above
  free.set(`video:${t.trackIndex}`, ws.video);
  for (const a of ws.audio) {
    if (a.free < 0) throw new PremiereError(`There is no empty audio track above A${a.track + 1}. Add one (right-click the track header > Add Track), keep it empty, and try again.`);
    free.set(`audio:${a.track}`, a.free);
  }
  const aTracks = ws.audio.map((a) => a.track);
  const SE = P().SequenceEditor;
  const editor = SE && typeof SE.getEditor === "function" ? await SE.getEditor(sequence) : undefined;
  if (!editor) throw new PremiereError("SequenceEditor.getEditor(sequence) is not available here.");
  log(`Video V${t.trackIndex + 1} and ${aTracks.length} audio track(s) (${aTracks.map((a) => "A" + (a + 1)).join(", ") || "none"}) will be cut in ${rounds} round${rounds === 1 ? "" : "s"} at most, using empty tracks above as workspace.`);

  if (o.backup) await ensureBackup(project, sequence, log, false);

  /** How many temporary copies are still on the workspace tracks (for the failure message). Never throws. */
  const leftoverCopies = async () => {
    const { S, E } = spanOf(used);
    let n = 0;
    const inSpan = (c) => c.S < E - 0.001 && c.E > S + 0.001;
    n += ((await safe(() => trackSpans(sequence, "video", ws.video))) || []).filter(inSpan).length;
    for (const a of ws.audio) n += ((await safe(() => trackSpans(sequence, "audio", a.free))) || []).filter(inSpan).length;
    return n;
  };

  const quiet = (text, isError) => { if (isError) log(text, true); };
  let stopped = false;
  while (pending.length) {
    if (stopAsked()) { stopped = true; break; }
    round++;
    progress({ phase: "round-start" });
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
    if (!jobs.length) { round--; break; }
    log(`Round ${round} of ${rounds} at most: cutting ${cutsThisRound} piece${cutsThisRound === 1 ? "" : "s"}...`);
    try {
      await splitMany(project, sequence, editor, jobs, round === 1 ? log : quiet, tol);
    } catch (e) {
      const err = new PremiereError(`Stopped after ${done} of ${total} cuts (round ${round}): ${msg(e)}`);
      err.state = { done, total, round, leftover: await leftoverCopies() };
      throw err;
    }
    done += cutsThisRound;
    log(`Round ${round} done: ${done} of ${total} cuts.`);
    pending = rest.sort((a, b) => a - b);
    progress({ phase: "round-done" });
  }
  if (stopped) log(`Stopped on request after round ${round}: ${done} of ${total} cuts are made. Run it again to finish; points that already have a cut are skipped.`);
  return { cuts: done, skipped, points: total, rounds: round, clips: used.length, stopped };
}

// ---- 0.7.0: ripple delete of the gaps ------------------------------------------------------------------------
const DELETE_CHUNK = 60; // gap pieces per ripple-delete action (and per verification read-back)

/**
 * The pieces the cut works on (video clips of the file's video on the lowest track holding it) paired with the linked audio piece on each
 * linked audio track (same start and end). `unmatched` counts the (video piece, audio track) pairs that have no audio piece: deleting
 * such a piece would leave its audio behind. Returns {pairs: [{v, a: Map(track -> span)}], aTracks, unmatched}.
 */
function pairPieces(t) {
  const aTracks = Array.from(new Set(t.linked.map((a) => a.track))).sort((a, b) => a - b);
  let unmatched = 0;
  const pairs = t.used.map((v) => {
    const a = new Map();
    for (const at of aTracks) {
      const m = t.linked.find((x) => x.track === at && Math.abs(x.S - v.S) < 0.05 && Math.abs(x.E - v.E) < 0.05);
      if (m) a.set(at, m);
      else unmatched++;
    }
    return { v, a };
  });
  return { pairs, aTracks, unmatched };
}

/**
 * Removes track items with the sequence editor, as ONE undoable step: createRemoveItemsAction(selection, ripple, mediaType, shiftOverLapping).
 * o = {ripple, media: "any" | "video" | "audio", shiftOverLapping, label, settle}. Returns the milliseconds the edit took.
 * Which argument is "ripple" is the 0.6.x guess; the Test ripple delete experiment checks it on a real Premiere.
 */
async function removeItems(project, editor, items, o) {
  const mtEnum = P().Constants && P().Constants.MediaType;
  const want = String(o.media || "any").toUpperCase();
  const mt = mtEnum ? mtEnum[want] : 0;
  if (mtEnum && mt === undefined) throw new PremiereError(`Constants.MediaType.${want} is not offered by this Premiere.`);
  const remove = need(editor, "createRemoveItemsAction", "the sequence editor");
  const t0 = Date.now();
  await transaction(project, o.label || "LuckyTwitch: delete", (comp) => {
    P().TrackItemSelection.createEmptySelection((sel) => {
      for (const it of items) sel.addItem(it, false);
      comp.addAction(remove(sel, !!o.ripple, mt, !!o.shiftOverLapping));
    });
  }, o.settle === undefined ? SETTLE : o.settle);
  return Date.now() - t0;
}

const bySpanStart = (a, b) => a.S - b.S;

/** The pieces of the target video track and of each linked audio track, sorted by start: {v: [span], a: Map(track -> [span])}. */
async function readPieceTracks(sequence, t, aTracks) {
  const v = (await trackSpans(sequence, "video", t.trackIndex)).sort(bySpanStart);
  const a = new Map();
  for (const at of aTracks) a.set(at, (await trackSpans(sequence, "audio", at)).sort(bySpanStart));
  return { v, a };
}

/** Identity of a piece across edits: the part of the source it plays (ripple moves pieces on the timeline but never changes this). */
const sourceKey = (c) => `${Math.round(c.I * 1000)}:${Math.round(c.O * 1000)}`;

const FILL_TOL = 0.003; // seconds: how close a lengthened piece must end to where it was asked to end (Premiere works in ticks; this is only read-back noise)

/**
 * 0.7.3: closes the holes a ripple delete left. The first real delete showed that Premiere closes each removed piece by its length minus
 * 0 to 1 frame, so a hole of up to a frame is left in front of the next piece. The hole is closed by LENGTHENING the piece in front of it
 * until it meets the next piece (createSetEndAction: at most the hole, about one frame, of extra source at the END of that clip), and
 * the hole in front of the first piece by pulling its start back (createSetStartAction, which also moves its source in point, as the cut
 * saw on a real Premiere). Nothing is moved, so nothing can overlap. All tracks go in ONE edit; afterwards EVERY piece of every track is
 * read back and must be where it should be: touched pieces at their new edge with the source in / out moved by exactly the added length,
 * untouched pieces exactly as before.
 * tracks = [{kind, track, label, next: [span] (the pieces after the delete, sorted), check: C().checkRippleHoles result for that track}].
 * Returns {filled, seconds, ms, problems}. Never throws for a mismatch: the caller stops the run with the problems.
 */
async function fillHoles(project, sequence, tracks, o) {
  const opts = o || {};
  const jobs = [];
  const wanted = new Map(); // `${label}:${i}` -> the piece as it must read after the edit
  const speedOf = (c) => {
    const d = c.E - c.S;
    const sp = d > 0 ? (c.O - c.I) / d : 1;
    return sp > 0 ? sp : 1;
  };
  for (const tr of tracks) {
    tr.next.forEach((c, i) => wanted.set(`${tr.label}:${i}`, { S: c.S, E: c.E, I: c.I, O: c.O }));
    for (const h of tr.check.fills) {
      const c = tr.next[h.i], nx = tr.next[h.i + 1];
      const hole = nx.S - c.E;
      const w = wanted.get(`${tr.label}:${h.i}`);
      w.E = nx.S;
      w.O = c.O + hole * speedOf(c);
      jobs.push({ tr, kind: "end", c, to: nx.S, hole });
    }
    if (tr.check.leadFill) {
      const c = tr.next[0];
      const hole = c.S - tr.check.leadFill.target;
      const w = wanted.get(`${tr.label}:0`);
      w.S = tr.check.leadFill.target;
      w.I = c.I - hole * speedOf(c);
      jobs.push({ tr, kind: "start", c, to: tr.check.leadFill.target, hole });
    }
  }
  if (!jobs.length) return { filled: 0, seconds: 0, ms: 0, problems: [] };
  const t0 = Date.now();
  await transaction(project, opts.label || "LuckyTwitch: close holes", (comp) => {
    for (const j of jobs) {
      if (j.kind === "end") comp.addAction(need(j.c.item, "createSetEndAction", "a track item")(tick(j.to)));
      else comp.addAction(need(j.c.item, "createSetStartAction", "a track item")(tick(j.to)));
    }
  }, opts.settle === undefined ? SETTLE : opts.settle);
  const readBack = async () => {
    const m = new Map();
    for (const tr of tracks) m.set(tr.label, (await trackSpans(sequence, tr.kind, tr.track)).sort(bySpanStart));
    return m;
  };
  const judge = (m) => {
    const problems = [];
    let bad = 0;
    for (const tr of tracks) {
      const got = m.get(tr.label);
      if (got.length !== tr.next.length) {
        problems.push(`${tr.label} has ${got.length} pieces after closing the holes, ${tr.next.length} were expected`);
        bad++;
        continue;
      }
      got.forEach((a, i) => {
        const w = wanted.get(`${tr.label}:${i}`);
        const d = Math.max(Math.abs(a.S - w.S), Math.abs(a.E - w.E), Math.abs(a.I - w.I), Math.abs(a.O - w.O));
        if (!(d <= FILL_TOL)) {
          bad++;
          if (problems.length < 3) problems.push(`${tr.label} piece ${i + 1} of ${got.length} reads ${a.S.toFixed(3)}-${a.E.toFixed(3)} (source ${a.I.toFixed(3)}-${a.O.toFixed(3)}), expected ${w.S.toFixed(3)}-${w.E.toFixed(3)} (source ${w.I.toFixed(3)}-${w.O.toFixed(3)})`);
        }
      });
    }
    if (bad > problems.length) problems.push(`... ${bad} pieces are off in total`);
    return problems;
  };
  let problems = [];
  await waitFor(async () => {
    problems = judge(await readBack());
    return problems;
  }, (x) => x.length === 0, 12, 100);
  const filledJobs = jobs.filter((j) => j.tr.kind === "video");
  const seconds = (filledJobs.length ? filledJobs : jobs).reduce((a, j) => a + j.hole, 0);
  return { filled: jobs.length, seconds, ms: Date.now() - t0, problems };
}

/** The plan the delete works from, read from the live timeline: {t, grid, pairs, aTracks, unmatched, set, plan}. Read-only. */
async function gapPlanNow(items, o, sequence) {
  const t = await collectTarget(sequence, o.hint);
  const grid = await frameGrid(sequence);
  const { pairs, aTracks, unmatched } = pairPieces(t);
  const set = C().planCutSet(items, Object.assign({}, o.plan, { clips: true, chapters: false })); // keep ranges: the clips (padded, merged); chapters are not ranges
  const plan = C().planGapDelete(t.descs, set.ranges, { frame: grid.frame, scope: o.scope || null, maxDeletePct: o.maxDeletePct, minKeep: o.minKeep, audioUnmatched: unmatched });
  return { t, grid, pairs, aTracks, unmatched, set, plan };
}

/**
 * Deletes the GAP pieces (the stretches between the clips) from the timeline with a ripple delete, so the clips end up back to back.
 * `items` are the planned markers (planMarkers); opts = {backup, plan (padding / merge, same as the cut), scope ({min, max} when limited to one
 * chapter), hint, maxDeletePct, minKeep, expect ({deleteCount, keepCount}: what the preview showed), chunk, onProgress, shouldStop}.
 *
 * Safety, in this order, all BEFORE anything is touched: every piece is classified keep / gap / uncertain from the part of the source it plays
 * (core.planGapDelete); the run refuses on an uncertain piece, on a video piece without its linked audio, when the kept time differs from what
 * the plan says, when it would delete more than maxDeletePct, or when fewer than minKeep pieces would be kept; and, when `expect` is given,
 * when the timeline no longer matches the preview. Then ONE forced backup (opts.backup). The delete runs in chunks of DELETE_CHUNK gap pieces,
 * video and linked audio together (MediaType.ANY, ripple = true). After every chunk the timeline is read back: every remaining piece must
 * keep its source and length, and may sit at most one frame per removed piece further right than a ripple puts it (0.7.2 log: Premiere closes
 * each removed piece by its length minus 0 to 1 frame). Those holes are then closed by lengthening the piece in front of each (fillHoles) and
 * the whole timeline is read back again. The first mismatch stops the run and says what is left.
 * Stop finishes the chunk it is in. Returns {deleted, total, rounds, chunks, stopped, deletedSeconds, keepPieces, keepSeconds}.
 * A failure throws a PremiereError with .state = {kind: "delete", deleted, total, round, note}.
 */
async function deleteGaps(items, opts, log) {
  const o = opts || {};
  const { project, sequence } = await activeContext();
  const { t, grid, pairs, aTracks, set, plan } = await gapPlanNow(items, o, sequence);
  const stopAsked = () => !!(o.shouldStop && o.shouldStop());
  log(`Gap plan: ${plan.text}. ${set.ranges.length} keep ranges from the clips${o.scope ? ` inside chapter "${o.scope.name}"` : ""}; ${plan.outside.length ? `${plan.outside.length} pieces outside the chapter are left alone; ` : ""}the kept time is ${plan.keepSeconds.toFixed(1)} s, the plan says ${plan.expectedKeepSeconds.toFixed(1)} s.`);
  if (!plan.ok) throw new PremiereError(`Nothing was deleted. ${plan.problems.join(" ")}`);
  if (o.expect && (o.expect.deleteCount !== plan.deleteCount || o.expect.keepCount !== plan.keepCount)) {
    throw new PremiereError(`Nothing was deleted: the timeline is not what the preview showed (preview: delete ${o.expect.deleteCount}, keep ${o.expect.keepCount}; now: delete ${plan.deleteCount}, keep ${plan.keepCount}). Look at the new preview and confirm again.`);
  }
  const total = plan.deleteCount;
  const chunk = Math.max(1, Math.floor(o.chunk) || DELETE_CHUNK);
  const chunks = Math.ceil(total / chunk);
  let done = 0, deletedSeconds = 0, round = 0, stopped = false, holeCount = 0, holeSeconds = 0;
  const progress = (extra) => {
    if (!o.onProgress) return;
    try {
      o.onProgress({ round, rounds: chunks, done, total, ...extra });
    } catch (e) {
      /* a broken progress display must never stop the delete */
    }
  };
  const result = () => ({ deleted: done, total, rounds: round, chunks, stopped, deletedSeconds, keepPieces: plan.keepCount, keepSeconds: plan.keepSeconds, holes: holeCount, holeSeconds });
  progress({ phase: "plan" });
  if (!total) return result();
  if (stopAsked()) return { ...result(), stopped: true };
  const keys = pairs.map((p) => sourceKey(p.v));
  if (new Set(keys).size !== keys.length) throw new PremiereError("Nothing was deleted: two pieces on the timeline play the same part of the source, so they cannot be told apart. Delete the duplicate by hand first.");
  const gapKeys = new Set(plan.del.map((c) => keys[c.index]));

  const SE = P().SequenceEditor;
  const editor = SE && typeof SE.getEditor === "function" ? await SE.getEditor(sequence) : undefined;
  if (!editor) throw new PremiereError("SequenceEditor.getEditor(sequence) is not available here.");
  const others = await countOtherItems(sequence, t, aTracks);
  if (others > 0) log(`Note: ${nOf(others, "item")} on other tracks (not touched by the plugin). A ripple delete may move them; the Test ripple delete experiment shows whether it does on your Premiere.`);
  if (o.backup) await ensureBackup(project, sequence, log, true); // forced: a recent backup of an earlier step does not cover a delete
  log(`Deleting ${total} gap pieces (${plan.deleteSeconds.toFixed(1)} s) from V${t.trackIndex + 1}${aTracks.length ? ` and ${aTracks.map((a) => "A" + (a + 1)).join(", ")}` : ""} in ${nOf(chunks, "batch", "batches")} of up to ${chunk}, ripple on; keeping ${plan.keepCount} pieces (${plan.keepSeconds.toFixed(1)} s).`);

  const fail = (message, note) => {
    const err = new PremiereError(`Stopped in batch ${round} of ${chunks} after ${done} of ${total} gap pieces were deleted: ${message}`);
    err.state = { kind: "delete", deleted: done, total, round, note: note || "" };
    return err;
  };
  let cur = await readPieceTracks(sequence, t, aTracks);
  while (true) {
    const gapV = cur.v.filter((c) => gapKeys.has(sourceKey(c)));
    if (!gapV.length) break;
    if (stopAsked()) {
      stopped = true;
      break;
    }
    round++;
    progress({ phase: "round-start" });
    const batch = gapV.slice(0, chunk);
    const vIdx = new Set(batch.map((c) => cur.v.indexOf(c)));
    const aIdx = new Map();
    const picked = batch.map((c) => c.item);
    for (const at of aTracks) {
      const idx = new Set();
      for (const v of batch) {
        const k = cur.a.get(at).findIndex((x) => Math.abs(x.S - v.S) < 0.05 && Math.abs(x.E - v.E) < 0.05);
        if (k < 0) throw fail(`A${at + 1} has no piece at ${v.S.toFixed(3)} -> ${v.E.toFixed(3)} (the video gap there). Nothing was deleted in this batch.`, "Nothing in the failed batch was deleted.");
        idx.add(k);
        picked.push(cur.a.get(at)[k].item);
      }
      aIdx.set(at, idx);
    }
    const keepV = cur.v.length - vIdx.size;
    const keepA = new Map(aTracks.map((at) => [at, cur.a.get(at).length - aIdx.get(at).size]));
    log(`Batch ${round} of ${chunks}: removing ${batch.length} gap pieces (${batch.reduce((a, c) => a + (c.E - c.S), 0).toFixed(1)} s)...`);
    let ms;
    try {
      ms = await removeItems(project, editor, picked, { ripple: true, media: "any", label: `LuckyTwitch: delete gaps (batch ${round}/${chunks})` });
    } catch (e) {
      throw fail(msg(e), "Premiere refused the edit; nothing in this batch should have changed.");
    }
    const next = await waitFor(
      () => readPieceTracks(sequence, t, aTracks),
      (x) => x.v.length === keepV && aTracks.every((at) => x.a.get(at).length === keepA.get(at)),
      20,
      150
    );
    // Premiere closes each removed piece by its length minus 0 to 1 frame (0.7.2 log): allow that, nothing else
    const problems = [];
    const vCheck = C().checkRippleHoles(cur.v, vIdx, next.v, grid.frame);
    if (!vCheck.ok) problems.push(`V${t.trackIndex + 1}: ${vCheck.problems.join("; ")}. ${driftText(cur.v, vIdx, next.v, grid.frame)}`);
    const aChecks = new Map();
    for (const at of aTracks) {
      const aCheck = C().checkRippleHoles(cur.a.get(at), aIdx.get(at), next.a.get(at), grid.frame);
      aChecks.set(at, aCheck);
      if (!aCheck.ok) problems.push(`A${at + 1}: ${aCheck.problems.join("; ")}. ${driftText(cur.a.get(at), aIdx.get(at), next.a.get(at), grid.frame)}`);
    }
    if (problems.length) throw fail(`after the ripple delete the timeline is not what it should be (a hole of up to one frame per removed piece is expected and gets closed; this is more than that, or the pieces changed). ${problems.join(" | ")}. Ripple may not behave as assumed: run Troubleshooting > Test ripple delete on a copy and send the log.`, "The failed batch may be partly applied: look at the timeline (Ctrl+Z undoes it) or use the backup copy.");
    done += batch.length;
    deletedSeconds += batch.reduce((a, c) => a + (c.E - c.S), 0);
    // close the holes (each at most about a frame), then read the whole timeline back
    const fillTracks = [{ kind: "video", track: t.trackIndex, label: `V${t.trackIndex + 1}`, next: next.v, check: vCheck }];
    for (const at of aTracks) fillTracks.push({ kind: "audio", track: at, label: `A${at + 1}`, next: next.a.get(at), check: aChecks.get(at) });
    let fill;
    try {
      fill = await fillHoles(project, sequence, fillTracks, { label: `LuckyTwitch: close holes (batch ${round}/${chunks})` });
    } catch (e) {
      throw fail(`${done} gap pieces are deleted, but closing the holes Premiere left failed: ${msg(e)}`, "The pieces of this batch are deleted; some holes of about one frame may be left. Ctrl+Z (closing, then the delete) or the backup copy.");
    }
    if (fill.problems.length) throw fail(`${done} gap pieces are deleted, but after closing the holes Premiere left the timeline different from what was asked: ${fill.problems.join(" | ")}`, "The pieces of this batch are deleted; the holes may be only partly closed. Ctrl+Z (closing, then the delete) or the backup copy.");
    const framePart = (sec) => (grid.frame > 0 ? ` = ${(sec / grid.frame).toFixed(1)} frames` : "");
    if (fill.filled) {
      holeCount += vCheck.fills.length + (vCheck.leadFill ? 1 : 0);
      holeSeconds += vCheck.holeSeconds;
    }
    cur = fill.filled ? await readPieceTracks(sequence, t, aTracks) : next;
    log(`Batch ${round} done in ${ms} ms: ${done} of ${total} gap pieces deleted. ${fill.filled ? `Premiere left ${nOf(vCheck.fills.length + (vCheck.leadFill ? 1 : 0), "hole")} (${(vCheck.holeSeconds * 1000).toFixed(1)} ms${framePart(vCheck.holeSeconds)} in all, for ${nOf(batch.length, "removed piece")}); closed by lengthening the piece in front of each (${fill.ms} ms). ` : "Premiere left no hole. "}Every remaining piece checked (source and length unchanged).`);
    progress({ phase: "round-done" });
  }
  if (stopped) log(`Stopped on request after batch ${round}: ${done} of ${total} gap pieces are deleted. Run it again to finish: it works out what is left.`);
  else log(`All ${done} gap pieces are deleted. V${t.trackIndex + 1} now has ${cur.v.length} pieces${cur.v.length ? `, ending at ${cur.v[cur.v.length - 1].E.toFixed(3)} s` : ""}.`);
  return result();
}

/**
 * Where the pieces ended up compared with where a ripple of exactly the removed pieces puts them, in plain words. Positive = too far right
 * (the gap closed by less than the removed length). before = the track's pieces before the delete, removed = Set of indexes into it,
 * after = the pieces now. Reads the first and the last remaining piece and divides the last one's error by the pieces removed before it.
 */
function driftText(before, removed, after, frame) {
  const expected = C().rippleExpectation(before, removed, true);
  if (!expected.length || expected.length !== after.length) return "";
  const keptBefore = before.filter((_, i) => !removed.has(i));
  const lastS = keptBefore[keptBefore.length - 1].S;
  const n = before.filter((c, i) => removed.has(i) && c.S < lastS).length;
  const d = (i) => (after[i].S - expected[i].S) * 1000;
  const first = d(0), last = d(expected.length - 1);
  const per = n ? last / n : 0;
  const fr = frame > 0 ? ` = ${(per / (frame * 1000)).toFixed(2)} frames` : "";
  return `Drift: first remaining piece ${first.toFixed(1)} ms, last ${last.toFixed(1)} ms (+ = too far right) after ${n} removed pieces before it: about ${per.toFixed(2)} ms per removed piece${fr}.`;
}

const nOf = (n, one, many) => `${n} ${n === 1 ? one : many || one + "s"}`; // not called `plural`: markers-core.js declares that at top level in the same global scope

/** How many items sit on tracks other than the cut's own video track and its linked audio tracks (a ripple delete may move them). Never throws. */
async function countOtherItems(sequence, t, aTracks) {
  let n = 0;
  const vCount = (await safe(() => need(sequence, "getVideoTrackCount", "Sequence")())) || 0;
  for (let i = 0; i < vCount; i++) if (i !== t.trackIndex) n += ((await safe(() => trackSpans(sequence, "video", i))) || []).length;
  const aCount = (await safe(() => need(sequence, "getAudioTrackCount", "Sequence")())) || 0;
  for (let i = 0; i < aCount; i++) if (!aTracks.includes(i)) n += ((await safe(() => trackSpans(sequence, "audio", i))) || []).length;
  return n;
}

/** Probe (read-only): how the delete would classify the pieces on the timeline right now, and whether the safety guard lets it through. */
async function probeGapPlan(items, log, opts, hint) {
  const { sequence } = await activeContext();
  const o = Object.assign({}, opts || {}, { hint });
  const { t, grid, pairs, aTracks, unmatched, set, plan } = await gapPlanNow(items, o, sequence);
  log(`Gap plan for ${t.used.length} piece(s) of "${t.mediaName}" on V${t.trackIndex + 1} (${t.how}); frame ${grid.frame ? (grid.frame * 1000).toFixed(2) + " ms" : "unknown"}; ${set.ranges.length} keep ranges from the clips.`);
  log(`Linked audio: ${aTracks.length ? aTracks.map((a) => "A" + (a + 1)).join(", ") : "(none)"}; ${unmatched ? `${unmatched} video piece(s) without a matching audio piece` : "every video piece has its audio piece"}.`);
  log(`Keep ${plan.keepCount} pieces (${plan.keepSeconds.toFixed(1)} s), delete ${plan.deleteCount} pieces (${plan.deleteSeconds.toFixed(1)} s, ${plan.deletePct.toFixed(1)}%), ${plan.uncertain.length} uncertain${plan.outside.length ? `, ${plan.outside.length} outside the chapter` : ""}. The plan says ${plan.expectedKeepSeconds.toFixed(1)} s should be kept (difference ${plan.keepDiff.toFixed(2)} s, allowed ${plan.tolerance.toFixed(1)} s).`);
  log(plan.ok ? (plan.nothing ? "Verdict: nothing to delete." : "Verdict: the safety guard lets this through.") : `Verdict: REFUSED. ${plan.problems.join(" ")}`);
  const sample = (list, label) => list.slice(0, 6).forEach((c) => log(`  ${label} ${c.piece.start.toFixed(3)} -> ${c.piece.end.toFixed(3)} (${c.seconds.toFixed(2)} s), source ${c.piece.inPoint.toFixed(3)} -> ${c.piece.outPoint.toFixed(3)}${c.why ? `: ${c.why}` : ""}`));
  sample(plan.uncertain, "uncertain");
  sample(plan.del, "gap");
  sample(plan.keep, "keep");
}

/**
 * EXPERIMENT (changes the project: run it on a COPY of the project; Ctrl+Z undoes it, many steps). Needs a timeline already cut into pieces
 * (V1 + A1, with an empty V2 / A2 above). It removes pieces in several ways and measures what Premiere did, to answer: is the second
 * argument of createRemoveItemsAction really "ripple", do the later pieces move by exactly the removed length, what happens to audio and to
 * other tracks, do several non-adjacent pieces in one action close every gap, and how long does an action take for 1, 10 and 100 pieces.
 */
async function testRippleDelete(log, hint) {
  const { project, sequence } = await activeContext();
  const t = await collectTarget(sequence, hint);
  const { pairs, aTracks } = pairPieces(t);
  const grid = await frameGrid(sequence);
  const tol = grid.frame > 0 ? grid.frame / 4 : 0.005; // see deleteGaps: strict, so a one-frame shortfall shows
  if (pairs.length < 8) throw new PremiereError(`This test needs the timeline cut into at least 8 pieces of the file's video (found ${pairs.length}). Run Cut at clips first, on a copy of the project.`);
  const SE = P().SequenceEditor;
  const editor = SE && typeof SE.getEditor === "function" ? await SE.getEditor(sequence) : undefined;
  if (!editor) throw new PremiereError("SequenceEditor.getEditor(sequence) is not available here.");
  const ws = await workspaceFor(sequence, t);
  const aTrack = aTracks.length ? aTracks[0] : -1;
  const ovTrack = ws.video;
  const oaTrack = aTrack >= 0 ? (ws.audio.find((a) => a.track === aTrack) || { free: -1 }).free : -1;
  log(`Ripple test on ${pairs.length} pieces of "${t.mediaName}" on V${t.trackIndex + 1}${aTrack >= 0 ? ` and A${aTrack + 1}` : " (no linked audio)"}; test clips go on ${ovTrack >= 0 ? "V" + (ovTrack + 1) : "(no free video track)"} and ${oaTrack >= 0 ? "A" + (oaTrack + 1) : "(no free audio track)"}. Frame ${grid.frame ? (grid.frame * 1000).toFixed(2) + " ms" : "unknown"}. THIS CHANGES THE PROJECT: Ctrl+Z undoes it.`);
  const readAll = async () => ({
    v: (await trackSpans(sequence, "video", t.trackIndex)).sort(bySpanStart),
    a: aTrack >= 0 ? (await trackSpans(sequence, "audio", aTrack)).sort(bySpanStart) : [],
    ov: ovTrack >= 0 ? (await trackSpans(sequence, "video", ovTrack)).sort(bySpanStart) : [],
    oa: oaTrack >= 0 ? (await trackSpans(sequence, "audio", oaTrack)).sort(bySpanStart) : [],
  });
  const r3 = (x) => (Math.round(x * 1000) / 1000).toFixed(3);
  const ms1 = (x) => `${(x * 1000).toFixed(1)} ms`;

  // test clips on V2 / A2, after the piece the first scenario removes: copies of two later pieces, same place and length
  const zero = tick(0);
  const clone = need(editor, "createCloneTrackItemAction", "the sequence editor");
  let testClips = 0;
  const base = await readAll();
  const at = Math.min(base.v.length - 2, Math.floor(base.v.length / 2) + 3);
  if (ovTrack >= 0 || oaTrack >= 0) {
    try {
      const src = base.v[at];
      const srcA = aTrack >= 0 ? base.a.find((x) => Math.abs(x.S - src.S) < 0.05 && Math.abs(x.E - src.E) < 0.05) : null;
      await transaction(project, "LuckyTwitch ripple test: test clips", (comp) => {
        if (ovTrack >= 0) comp.addAction(clone(src.item, zero, ovTrack - t.trackIndex, 0, false, false));
        if (oaTrack >= 0 && srcA) comp.addAction(clone(srcA.item, zero, 0, oaTrack - aTrack, false, false));
      }, SETTLE);
      const got = await waitFor(readAll, (x) => (ovTrack < 0 || x.ov.length) && (oaTrack < 0 || !srcA || x.oa.length), 10, 100);
      testClips = got.ov.length + got.oa.length;
      log(`Test clips placed: ${got.ov.length} on V${ovTrack + 1}, ${got.oa.length} on A${oaTrack + 1}, at timeline ${r3(src.S)} -> ${r3(src.E)} (after the piece that is removed first).`);
    } catch (e) {
      log(`Could not place the test clips (${msg(e)}): the other-tracks question stays unanswered.`, true);
    }
  } else log("There is no free V2 / A2: the other-tracks question stays unanswered.", true);

  const choose = (n, spec) => {
    if (spec.pattern === "middle") return n >= 4 ? { idx: [Math.floor(n / 2)], asked: 1 } : null;
    if (spec.pattern === "adjacent") return n >= 6 ? { idx: [Math.floor(n / 2), Math.floor(n / 2) + 1], asked: 2 } : null;
    const count = Math.min(spec.count, Math.floor((n - 2) / 2)); // every other piece: none touches another, the first and the last stay
    if (count < 2) return null;
    const step = Math.max(2, Math.floor((n - 2) / count));
    const idx = [];
    for (let i = 1; idx.length < count && i < n - 1; i += step) idx.push(i);
    return { idx, asked: spec.count };
  };
  const results = [];
  const scenario = async (spec) => {
    const before = await readAll();
    const pick = choose(before.v.length, spec);
    if (!pick || (spec.minCount && pick.idx.length < spec.minCount)) {
      log(`--- ${spec.name}: skipped (not enough pieces left on the timeline for this test).`);
      results.push({ spec, skipped: true });
      return;
    }
    const vSel = pick.idx.map((i) => before.v[i]);
    const aIdx = [];
    if (spec.withAudio && aTrack >= 0) {
      for (const v of vSel) {
        const k = before.a.findIndex((x) => Math.abs(x.S - v.S) < 0.05 && Math.abs(x.E - v.E) < 0.05);
        if (k >= 0) aIdx.push(k);
      }
    }
    const aSel = aIdx.map((k) => before.a[k]);
    log(`--- ${spec.name}: ${pick.idx.length} piece(s)${pick.idx.length < pick.asked ? ` (asked for ${pick.asked}, only this many fit)` : ""}, first at ${r3(vSel[0].S)} -> ${r3(vSel[0].E)}; selected ${vSel.length} video + ${aSel.length} audio item(s); ripple=${spec.ripple}, mediaType ${spec.media}, shiftOverLapping=${!!spec.shiftOverLapping}.`);
    let ms;
    try {
      ms = await removeItems(project, editor, [...vSel.map((c) => c.item), ...aSel.map((c) => c.item)], { ripple: spec.ripple, media: spec.media, shiftOverLapping: spec.shiftOverLapping, label: `LuckyTwitch ripple test: ${spec.name}` });
    } catch (e) {
      log(`${spec.name}: Premiere refused the edit: ${msg(e)}`, true);
      results.push({ spec, failed: msg(e) });
      return;
    }
    const after = await waitFor(readAll, (x) => x.v.length < before.v.length || x.a.length < before.a.length, 12, 100);
    const track = (label, b, a, selectedIdx) => {
      const removedIdx = a.length === b.length - selectedIdx.length ? selectedIdx : a.length === b.length ? [] : null;
      if (removedIdx === null) {
        log(`  ${label}: ${b.length} -> ${a.length} pieces: unexpected count (selected ${selectedIdx.length}).`);
        return { label, odd: true };
      }
      const rip = C().checkSpans(C().rippleExpectation(b, removedIdx, true), a, tol);
      const none = C().checkSpans(C().rippleExpectation(b, removedIdx, false), a, tol);
      const text = removedIdx.length === 0
        ? `nothing was removed there${none.ok ? ": every piece stayed in place" : ": but pieces moved (" + none.problems[0] + ")"}`
        : `${removedIdx.length} removed; later pieces moved left by exactly the removed length: ${rip.ok ? "YES" : "NO"}${rip.ok ? ` (max error ${ms1(rip.maxErr)})` : ""}; stayed where they were (a gap is left): ${none.ok ? "YES" : "NO"}${!rip.ok && !none.ok ? ` (${rip.problems[0]})` : ""}`;
      log(`  ${label}: ${b.length} -> ${a.length} pieces; ${text}.`);
      if (removedIdx.length) {
        const drift = driftText(b, new Set(removedIdx), a, grid.frame);
        if (drift) log(`  ${label}: ${drift}`);
        const hs = C().checkRippleHoles(b, new Set(removedIdx), a, grid.frame);
        const frames = (x) => (grid.frame > 0 ? ` = ${(x / grid.frame).toFixed(2)} frames` : "");
        log(`  ${label}: ${hs.ok ? "holes" : "NOT within one frame per removed piece"}: ${hs.fills.length + (hs.leadFill ? 1 : 0)} hole(s) with a removed piece in front, ${(hs.holeSeconds * 1000).toFixed(1)} ms${frames(hs.holeSeconds)} in all for ${removedIdx.length} removed piece(s); biggest single hole ${(Math.max(0, hs.leadFill ? hs.leadFill.hole : 0, ...hs.holes.map((h) => h.hole)) * 1000).toFixed(1)} ms.${hs.ok ? "" : " " + hs.problems[0]}`);
      }
      const holes = removedIdx.length ? C().checkRippleHoles(b, new Set(removedIdx), a, grid.frame) : null;
      return { label, removed: removedIdx.length, ripple: rip.ok, stayed: none.ok, err: rip.maxErr, holes };
    };
    const rv = track(`V${t.trackIndex + 1}`, before.v, after.v, pick.idx);
    const ra = aTrack >= 0 ? track(`A${aTrack + 1}`, before.a, after.a, aIdx) : null;
    // other tracks: did a test clip move, and by how much would a ripple of the removed ranges move it?
    const ranges = vSel.map((c) => ({ S: c.S, E: c.E }));
    const others = [];
    for (const [label, b, a] of [[`V${ovTrack + 1}`, before.ov, after.ov], [`A${oaTrack + 1}`, before.oa, after.oa]]) {
      if (!b.length || !a.length) continue;
      const moved = b[0].S - a[0].S;
      const wanted = C().shiftAfter(b[0].S, ranges);
      others.push({ label, moved, wanted });
      log(`  ${label} test clip: ${moved > tol ? `MOVED left by ${r3(moved)} s` : moved < -tol ? `moved RIGHT by ${r3(-moved)} s` : "STAYED where it was"} (a ripple of the removed pieces would move it ${r3(wanted)} s).`);
    }
    log(`  the edit took ${ms} ms.`);
    results.push({ spec, n: pick.idx.length, ms, rv, ra, others });
    await sleep(100);
  };

  await scenario({ name: "A: 1 piece, video+audio, ripple=true", pattern: "middle", ripple: true, media: "any", withAudio: true });
  await scenario({ name: "B: 1 piece, video+audio, ripple=false", pattern: "middle", ripple: false, media: "any", withAudio: true });
  await scenario({ name: "C: 1 piece, ripple=true, shiftOverLapping=true", pattern: "middle", ripple: true, media: "any", shiftOverLapping: true, withAudio: true });
  await scenario({ name: "D: 10 non-adjacent pieces, ripple=true", pattern: "spaced", count: 10, ripple: true, media: "any", withAudio: true });
  await scenario({ name: "E: 2 adjacent pieces, ripple=true", pattern: "adjacent", ripple: true, media: "any", withAudio: true });
  await scenario({ name: "F: up to 100 non-adjacent pieces, ripple=true", pattern: "spaced", count: 100, minCount: 11, ripple: true, media: "any", withAudio: true });
  // I: what the 0.7.3 delete does for real: ripple, then close the holes by lengthening the piece in front, then read everything back
  const closeScenario = async () => {
    const name = "I: 3 non-adjacent pieces, ripple=true, then close the holes (the 0.7.3 delete)";
    const before = await readAll();
    const pick = choose(before.v.length, { pattern: "spaced", count: 3 });
    if (!pick || pick.idx.length < 2) {
      log(`--- ${name}: skipped (not enough pieces left).`);
      results.push({ spec: { name }, skipped: true });
      return;
    }
    const vSel = pick.idx.map((i) => before.v[i]);
    const aIdx = [];
    if (aTrack >= 0) for (const v of vSel) {
      const k = before.a.findIndex((x) => Math.abs(x.S - v.S) < 0.05 && Math.abs(x.E - v.E) < 0.05);
      if (k >= 0) aIdx.push(k);
    }
    log(`--- ${name}: removing ${vSel.length} video + ${aIdx.length} audio piece(s) (first at ${r3(vSel[0].S)} -> ${r3(vSel[0].E)}).`);
    let ms;
    try {
      ms = await removeItems(project, editor, [...vSel.map((c) => c.item), ...aIdx.map((k) => before.a[k].item)], { ripple: true, media: "any", label: `LuckyTwitch ripple test: ${name}` });
    } catch (e) {
      log(`${name}: Premiere refused the edit: ${msg(e)}`, true);
      results.push({ spec: { name }, failed: msg(e) });
      return;
    }
    const after = await waitFor(readAll, (x) => x.v.length === before.v.length - vSel.length && (aTrack < 0 || x.a.length === before.a.length - aIdx.length), 12, 100);
    const vIdx = new Set(pick.idx);
    const aSet = new Set(aIdx);
    const tracks = [{ kind: "video", track: t.trackIndex, label: `V${t.trackIndex + 1}`, next: after.v, check: C().checkRippleHoles(before.v, vIdx, after.v, grid.frame) }];
    if (aTrack >= 0) tracks.push({ kind: "audio", track: aTrack, label: `A${aTrack + 1}`, next: after.a, check: C().checkRippleHoles(before.a, aSet, after.a, grid.frame) });
    const bad = tracks.filter((x) => !x.check.ok);
    if (bad.length) {
      log(`  ${bad.map((x) => `${x.label}: ${x.check.problems.join("; ")}`).join(" | ")}: more than one frame per removed piece, or the pieces changed: nothing was closed.`);
      results.push({ spec: { name }, n: vSel.length, ms, closed: false, why: "ripple outside one frame per removed piece" });
      return;
    }
    const holeCount = tracks[0].check.fills.length + (tracks[0].check.leadFill ? 1 : 0);
    let fill;
    try {
      fill = await fillHoles(project, sequence, tracks, { label: "LuckyTwitch ripple test: close holes" });
    } catch (e) {
      log(`  closing the holes failed: ${msg(e)}`, true);
      results.push({ spec: { name }, n: vSel.length, ms, closed: false, why: msg(e) });
      return;
    }
    log(`  ${holeCount} hole(s) after the ripple (${(tracks[0].check.holeSeconds * 1000).toFixed(1)} ms in all); ${fill.filled ? `closed with ${fill.filled} lengthening edit(s) in ${fill.ms} ms; read back: ${fill.problems.length ? "NOT as asked: " + fill.problems.join("; ") : "every piece exactly where asked"}` : "nothing to close"}.`);
    results.push({ spec: { name }, n: vSel.length, ms, closed: fill.problems.length === 0, holes: holeCount, filled: fill.filled });
    await sleep(100);
  };
  await closeScenario();
  await scenario({ name: "G: video+audio selected, MediaType.VIDEO, ripple=true", pattern: "middle", ripple: true, media: "video", withAudio: true });
  await scenario({ name: "H: video only selected, MediaType.ANY, ripple=true", pattern: "middle", ripple: true, media: "any", withAudio: false });

  // clean up the test clips (they sit on the empty workspace tracks, so everything found there is ours)
  const left = await readAll();
  const mine = [...left.ov, ...left.oa];
  if (testClips && mine.length === testClips) {
    try {
      await removeItems(project, editor, mine.map((c) => c.item), { ripple: false, media: "any", label: "LuckyTwitch ripple test: remove test clips" });
      log(`Removed the ${testClips} test clip(s) again.`);
    } catch (e) {
      log(`Could not remove the test clips (${msg(e)}): delete them by hand (they are on V${ovTrack + 1} / A${oaTrack + 1}).`, true);
    }
  } else if (mine.length) log(`${mine.length} item(s) are on V${ovTrack + 1} / A${oaTrack + 1}; they were not removed because they are not exactly the ${testClips} test clip(s). Delete them by hand if they are leftovers.`);

  // the answers, in plain words
  const get = (letter) => results.find((r) => r.spec.name.startsWith(letter + ":"));
  const yn = (b) => (b ? "YES" : "NO");
  log("===== RESULT of the ripple test (copy the whole log and send it) =====");
  const A = get("A"), B = get("B"), Cc = get("C"), D = get("D"), E = get("E"), F = get("F"), G = get("G"), H = get("H");
  if (A && A.rv) {
    log(`1. Later V pieces moved left by exactly the piece's length (A, ripple=true): ${yn(A.rv.ripple)}.`);
    if (A.ra) log(`2. A${aTrack + 1}: the linked audio piece was removed with it and later audio pieces moved too (A): ${yn(A.ra.removed > 0 && A.ra.ripple)}${A.ra.removed === 0 ? " (the audio piece was not even found at the same place)" : ""}.`);
    if (A.others.length) log(`3. Other tracks (test clips on V2 / A2 after the piece): ${A.others.map((o) => `${o.label} ${o.moved > tol ? "MOVED left" : "STAYED"}`).join(", ")}.`);
    else log("3. Other tracks: not answered (no test clip could be placed).");
  } else log("1-3. Scenario A did not run or failed: see above.");
  if (A && A.rv && B && B.rv) log(`4. The second argument is really "ripple": ${yn(A.rv.ripple && B.rv.stayed && !B.rv.ripple)} (true closed the gap: ${yn(A.rv.ripple)}; false left a gap: ${yn(B.rv.stayed)}).`);
  else log("4. Second argument: not answered (A or B did not run).");
  if (Cc && Cc.rv) log(`   shiftOverLapping=true changed anything compared with the plain ripple: ${yn(!(Cc.rv.ripple && Cc.ra && Cc.ra.ripple))} (V ripple ${yn(Cc.rv.ripple)}${Cc.ra ? `, A ripple ${yn(Cc.ra.ripple)}` : ""}).`);
  if (D && D.rv) log(`5. ${D.n} NON-adjacent pieces in one action closed every gap correctly: V ${yn(D.rv.ripple)}${D.ra ? `, A ${yn(D.ra.ripple)}` : ""}.`);
  if (E && E.rv) log(`   2 ADJACENT pieces in one action: V ${yn(E.rv.ripple)}${E.ra ? `, A ${yn(E.ra.ripple)}` : ""}.`);
  const times = [A, D, F].filter((x) => x && x.ms !== undefined).map((x) => `${x.n} piece${x.n === 1 ? "" : "s"}: ${x.ms} ms`);
  log(`6. Time of one remove action: ${times.join("; ") || "not measured"}.`);
  if (G && G.rv) log(`7. Video+audio selected but MediaType.VIDEO: V ripple ${yn(G.rv.ripple)}; audio: ${G.ra ? (G.ra.removed === 0 ? "its pieces stayed (not removed)" : G.ra.ripple ? "removed and closed" : "removed, not closed") : "n/a"}.`);
  if (H && H.rv) log(`8. Video-only selection with MediaType.ANY: V ripple ${yn(H.rv.ripple)}; audio: ${H.ra ? (H.ra.removed === 0 && H.ra.stayed ? "untouched (audio piece stayed and nothing moved)" : H.ra.removed === 0 ? "pieces moved or changed: see above" : "removed too") : "n/a"}.`);
  const holeRows = [A, Cc, D, E, F, G].filter((x) => x && x.rv && x.rv.holes);
  if (holeRows.length) {
    const per = (x) => {
      const h = x.rv.holes;
      return `${x.spec.name[0]} ${x.rv.removed ? (h.holeSeconds / (grid.frame || 1) / x.rv.removed).toFixed(2) : "0.00"}`;
    };
    log(`9. Hole left by Premiere's ripple, in frames per removed piece: ${holeRows.map(per).join(", ")}. Every scenario within one frame per removed piece, nothing closed too far, sources and lengths unchanged: ${yn(holeRows.every((x) => x.rv.holes.ok))}.`);
  } else log("9. Holes: not measured (no ripple scenario ran).");
  const I = get("I");
  if (I && I.closed !== undefined) log(`10. Closing the holes by lengthening the piece in front (scenario I, what the 0.7.3 delete does): ${yn(I.closed)}${I.closed ? ` (${I.holes} hole(s) closed, all pieces read back exactly where asked)` : I.why ? ` (${I.why})` : ""}.`);
  else log("10. Closing the holes: not measured (scenario I did not run).");
  log("If 9 and 10 are YES, the 0.7.3 delete (ripple, close the holes, verify) works on your Premiere, whatever lines 1 and 5 say.");
  log("If A shows YES / YES and D is YES, a plain ripple was already exact on your Premiere.");
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

/** Selects exactly these track items on the sequence and reads the selection back: {count, rows: ["V2 12.000-20.000", ...]} or null when this Premiere will not do it. */
async function selectOnly(sequence, items) {
  let sel;
  P().TrackItemSelection.createEmptySelection((s) => {
    sel = s;
    for (const it of items) s.addItem(it, false);
  });
  if (!sel) return null;
  await need(sequence, "setSelection", "Sequence")(sel);
  await sleep(SETTLE * 2);
  const back = await safe(() => sequence.getSelection());
  const list = back ? asArray(await back.getTrackItems()) : null;
  if (!list) return null;
  const rows = [];
  for (const it of list) {
    const ti = await safe(() => read(it, "trackIndex"));
    const sp = await safe(() => itemSpan(it));
    rows.push(`track ${ti === undefined ? "?" : ti + 1}${sp ? ` ${sp.S.toFixed(3)}-${sp.E.toFixed(3)}` : ""}`);
  }
  return { count: list.length, rows };
}

/**
 * EXPERIMENT (0.7.4): does cloning the video clip WITH alignToVideo = true keep the video and its audio together (linked)?
 * The cut engine clones video and audio as two separate edits (alignToVideo = false), and the pieces come out unlinked. Here ONE clone
 * call is made on the video clip under the playhead, with alignToVideo = true, onto the empty tracks above. Then it reports what
 * appeared and compares what selecting the original clip selects with what selecting the copy selects (a linked clip selects its audio
 * too, if this Premiere's selection follows links). The real answer is your eyes: click the copy in the timeline.
 * One undo step. Nothing is removed afterwards.
 */
async function testAlignToVideo(log) {
  const { project, sequence } = await activeContext();
  const t = secOf(await need(sequence, "getPlayerPosition", "Sequence")());
  const vids = await spans(sequence, "video", () => {});
  const hit = vids.find((c) => t > c.S + 0.05 && t < c.E - 0.05);
  if (!hit) throw new PremiereError("The playhead is not inside a video clip (put it a few frames inside one).");
  const allA = await spans(sequence, "audio", () => {});
  const aud = allA.find((a) => Math.abs(a.S - hit.S) < 0.01 && Math.abs(a.E - hit.E) < 0.01);
  if (!aud) throw new PremiereError("That video clip has no audio clip with the same start and end, so there is nothing to keep together.");
  const SE = P().SequenceEditor;
  const editor = SE && typeof SE.getEditor === "function" ? await SE.getEditor(sequence) : undefined;
  if (!editor) throw new PremiereError("SequenceEditor.getEditor(sequence) is not available here.");
  const clone = need(editor, "createCloneTrackItemAction", "the sequence editor");
  const freeV = await freeTrackAbove(sequence, hit, vids, () => {});
  const freeA = await freeTrackAbove(sequence, aud, allA, () => {});
  if (freeV < 0 || freeA < 0) throw new PremiereError(`Needs an EMPTY ${freeV < 0 ? "video" : "audio"} track above the clip (add one and try again).`);
  log(`Test on V${hit.track + 1} "${hit.name}" ${hit.S.toFixed(3)} -> ${hit.E.toFixed(3)} and its audio A${aud.track + 1}. The copy goes to V${freeV + 1} / A${freeA + 1}.`);

  // 1. what selecting the ORIGINAL clip alone selects (the control: does this Premiere's selection follow links at all?)
  const before = await safe(() => selectOnly(sequence, [hit.item]));
  log(before ? `Control: selecting only the original video clip gives a selection of ${before.count} item(s): ${before.rows.join("; ")}.` : "Control: this Premiere would not select or read back a selection.");

  // 2. ONE clone call on the video clip, alignToVideo = true
  const zero = tick(0);
  await transaction(project, "LuckyTwitch test: clone with alignToVideo", (comp) => {
    comp.addAction(clone(hit.item, zero, freeV - hit.track, freeA - aud.track, true, false));
  }, SETTLE * 3);
  const v2 = await waitFor(() => findSpan(sequence, "video", freeV, hit.S, hit.E), Boolean);
  const a2 = await waitFor(() => findSpan(sequence, "audio", freeA, hit.S, hit.E), Boolean);
  log(`Video copy on V${freeV + 1}: ${v2 ? "appeared" : "did NOT appear"}.`);
  log(`Audio copy on A${freeA + 1} at the same place: ${a2 ? "appeared" : "did NOT appear"}.`);
  if (!a2) {
    const afterA = await spans(sequence, "audio", () => {});
    const extra = afterA.filter((c) => !allA.some((o) => o.item === c.item) && !(c.track === aud.track && Math.abs(c.S - aud.S) < 0.01));
    log(`Audio clips now: ${afterA.length} (before: ${allA.length}).${extra.length ? " New ones: " + extra.slice(0, 6).map((c) => `A${c.track + 1} ${c.S.toFixed(3)}-${c.E.toFixed(3)}`).join("; ") : ""}`);
  }
  if (v2) {
    const after = await safe(() => selectOnly(sequence, [v2.item]));
    log(after ? `Selecting only the video COPY gives a selection of ${after.count} item(s): ${after.rows.join("; ")}.` : "Selecting the copy: this Premiere would not select or read back a selection.");
    if (before && after) {
      if (before.count > 1 && after.count > 1) log("-> Selection follows links, and the copy selects its audio too: the copy looks LINKED.");
      else if (before.count > 1 && after.count === 1) log("-> Selection follows links, but the copy selects only itself: the copy looks UNLINKED.");
      else log("-> The selection API does not follow links on this Premiere (the original selects only itself), so this cannot tell. Use the check below.");
    }
  }
  log("YOUR CHECK: click the temp video copy on the timeline. Does its temp audio copy light up with it? Also try dragging it a little (Ctrl+Z after). If the audio follows, alignToVideo keeps the link: tell me. Ctrl+Z (one step) removes the temp copies.");
}

/**
 * PROBE (read-only, 0.7.5): where do the markers of the video clip and of its audio clip live? For the video clip under the playhead and
 * the audio clip with the same start and end: which project item each plays, whether it is the SAME one, how many markers each has,
 * and whether Markers.getMarkers accepts a timeline clip itself as owner. If both play the same project item, they share one set of
 * markers, so they cannot be removed from the audio alone.
 */
async function probeMarkerOwners(log) {
  const { sequence } = await activeContext();
  const t = secOf(await need(sequence, "getPlayerPosition", "Sequence")());
  const vids = await spans(sequence, "video", () => {});
  const hit = vids.find((c) => t > c.S + 0.05 && t < c.E - 0.05);
  if (!hit) throw new PremiereError("The playhead is not inside a video clip (put it a few frames inside one).");
  const allA = await spans(sequence, "audio", () => {});
  const aud = allA.find((a) => Math.abs(a.S - hit.S) < 0.01 && Math.abs(a.E - hit.E) < 0.01);
  log(`Video V${hit.track + 1} ${hit.S.toFixed(3)} -> ${hit.E.toFixed(3)}; audio: ${aud ? "A" + (aud.track + 1) : "no audio clip with the same start and end"}.`);
  const rows = [];
  for (const [label, c] of [["video", hit], ["audio", aud]]) {
    if (!c) continue;
    const raw = await safe(() => read(c.item, "projectItem"));
    const cast = raw ? await clipProjectItem(c.item) : undefined;
    const id = raw ? await safe(() => read(raw, "id")) : undefined;
    const name = raw ? await safe(() => read(raw, "name")) : undefined;
    const why = [];
    const onSource = cast || raw ? await listMarkers(cast || raw, why, 2) : [];
    const onClip = await listMarkers(c.item, why, 1);
    rows.push({ label, raw, id });
    log(`${label}: plays project item ${name === undefined ? "(name unreadable)" : JSON.stringify(name)}, id ${id === undefined ? "(unreadable)" : id}; markers on that project item: ${onSource.length}; markers when the timeline clip itself is the owner: ${onClip.length}.`);
    why.forEach((w) => log(`   ${w}`));
  }
  if (rows.length === 2) {
    const [v, a] = rows;
    const same = (v.id !== undefined && v.id === a.id) || (v.raw && v.raw === a.raw);
    log(same
      ? "RESULT: video and audio play the SAME project item, so they share one set of markers: removing them from the audio would remove them from the video too."
      : "RESULT: video and audio play DIFFERENT project items (or the ids could not be compared); send me this log.");
  }
}

/** Probe (read-only): what the Project-panel selection calls give on this Premiere, and which of the selected items count as clips. */
async function probeSelection(log) {
  const project = await activeProject();
  const PU = P().ProjectUtils;
  line_("ProjectUtils (static)", PU, log);
  if (!PU || typeof PU.getSelection !== "function") return log("ProjectUtils.getSelection() is not offered by this Premiere: markers cannot be added from a Project-panel selection.", true);
  const sel = await attempt(log, "ProjectUtils.getSelection(project)", () => PU.getSelection(project));
  log(`getSelection(project) gave: ${sel == null ? "nothing" : "an object"}`);
  if (typeof PU.getProjectViewIds === "function") {
    const ids = await attempt(log, "ProjectUtils.getProjectViewIds()", () => PU.getProjectViewIds());
    log(`Project panel view ids: ${(asArray(ids) || []).join(", ") || "(none)"}`);
  }
  const PI = P().ProjectItem;
  const CP = P().ClipProjectItem;
  const sources = await selectionSources(project);
  log(`Selection sources that answered: ${sources.map((x) => x.via).join(" | ") || "(none)"}`);
  for (const { via, sel: one } of sources) {
    const raw = await selectionItems(one);
    log(`${via}: ${raw.length} item(s)`);
    if (raw[0]) line_("a selected item", raw[0], log);
    // 0.7.0: for each selected item, the three things projectSelectionClips needs, so the cause of "0 clips" is visible
    for (const [i, item] of raw.slice(0, 5).entries()) {
      const name = await safe(() => read(item, "name"));
      const type = await safe(() => read(item, "type"));
      const typeNames = PI && type !== undefined ? Object.keys(PI).filter((k) => /^TYPE_/.test(k) && PI[k] === type) : [];
      const cast = CP && typeof CP.cast === "function" ? await attempt(log, `    ClipProjectItem.cast(item ${i + 1})`, () => CP.cast(item)) : undefined;
      const rawPath = await attempt(log, `    getMediaFilePath on item ${i + 1}`, async () => read(item, "mediaFilePath"));
      const castPath = cast ? await attempt(log, `    getMediaFilePath on the cast of item ${i + 1}`, async () => read(cast, "mediaFilePath")) : undefined;
      log(`  [${i + 1}] name: ${name === undefined ? "(unreadable)" : JSON.stringify(name)}; type: ${type === undefined ? "(unreadable)" : type}${typeNames.length ? ` (${typeNames.join("/")})` : ""}; ClipProjectItem.cast: ${!CP || typeof CP.cast !== "function" ? "not offered" : cast ? "gave an object" : "gave nothing"}; media path on the item: ${rawPath || "(none)"}; on the cast: ${castPath || (cast ? "(none)" : "n/a")}`);
      if (cast && cast !== item) line_(`    members of the cast of item ${i + 1}`, cast, log);
    }
  }
  if (PI) log(`ProjectItem type constants: ${Object.keys(PI).filter((k) => /^TYPE_/.test(k)).map((k) => `${k}=${PI[k]}`).join(", ") || "(none)"}`);
  const clips = await projectSelectionClips(project);
  log(`Selected clips with a media file: ${clips.length}`);
  clips.slice(0, 10).forEach((c) => log(`  "${c.name}" (${c.mediaPath})`));
  if (!clips.length) log("Click the video in the Project panel (so it is highlighted there) and press this again.");
}

const LT_ADAPTER_API = {
  addMarkers, checkMarkers, removeMarkers, findMarkersFile, inspectTimeline, backupSequence, probeSelection, projectSelectionClips,
  addTestMarkers, probe, probeClips, probeAudio, probeEditor, probeClasses, probeDetection, probeCutPlan, probeAll,
  addClipTestMarkers, testCutAtPlayhead, testSplitAtPlayhead, testAlignToVideo, probeMarkerOwners, cutAtClipEdges, deleteGaps, probeGapPlan, testRippleDelete, DELETE_CHUNK,
  PremiereError, _setPremiere: (m) => { pproModule = m; },
};
if (typeof module !== "undefined" && module.exports) module.exports = LT_ADAPTER_API;
if (typeof window !== "undefined") window.LTAdapter = LT_ADAPTER_API;
