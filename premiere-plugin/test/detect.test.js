"use strict";
// Finding the markers file by itself: Premiere and UXP's file system are mocked.
const test = require("node:test");
const assert = require("node:assert");
const Module = require("node:module");
const adapter = require("../src/premiere-adapter.js");

const MEDIA = "E:\\Videos\\2026-10-14 - DÚO\\IlloJuan - part1.mp4";
const MEDIA_DIR_URL = "file:/E:/Videos/2026-10-14%20-%20D%C3%9AO";
const PROJECT = "C:\\Proyectos\\edicion.prproj";
const PROJECT_DIR_URL = "file:/C:/Proyectos";

function file(name, text) {
  return { isFile: true, isFolder: false, name, nativePath: "X:\\" + name, read: async () => text };
}

/** folders: {url: [entries]}; urls not listed make getEntryWithUrl throw (like a path that cannot be opened). */
function setup({ folders, mediaPath = MEDIA, projectPath = PROJECT, selected = true }) {
  const tried = [];
  const fakeUxp = {
    storage: {
      localFileSystem: {
        getEntryWithUrl: async (url) => {
          tried.push(url);
          if (!folders[url]) throw new Error("no access");
          return { isFolder: true, getEntries: async () => folders[url] };
        },
      },
    },
  };
  const original = Module._load;
  Module._load = function (request, ...rest) {
    return request === "uxp" ? fakeUxp : original.call(this, request, ...rest);
  };
  const item = { getProjectItem: async () => ({ getMediaFilePath: async () => mediaPath }), getName: async () => "clip" };
  const sequence = {
    getSelection: async () => ({ getTrackItems: async () => (selected ? [item] : []) }),
    getVideoTrackCount: async () => 1,
    getVideoTrack: async () => ({ getTrackItems: async () => [item] }),
  };
  adapter._setPremiere({
    Constants: { TrackItemType: { CLIP: 1 } },
    Project: { getActiveProject: async () => ({ path: projectPath, getActiveSequence: async () => sequence }) },
  });
  return { tried, restore: () => (Module._load = original) };
}

test("finds <video>.markers.json next to the video, even with accents in the folder name", async () => {
  const env = setup({ folders: { [MEDIA_DIR_URL]: [file("IlloJuan - part1.mp4", ""), file("IlloJuan - part1.markers.json", "{json}"), file("IlloJuan - part2.markers.json", "{other}")] } });
  try {
    const why = [];
    const found = await adapter.findMarkersFile(why);
    assert.equal(found.name, "IlloJuan - part1.markers.json");
    assert.equal(found.text, "{json}");
    assert.equal(found.where, "next to the video");
    assert.equal(env.tried[0], MEDIA_DIR_URL);
  } finally {
    env.restore();
  }
});

test("falls back to the project folder when the video folder has none", async () => {
  const env = setup({ folders: { [MEDIA_DIR_URL]: [file("a.mp4", "")], [PROJECT_DIR_URL]: [file("IlloJuan - part1.markers.json", "{p}")] } });
  try {
    const found = await adapter.findMarkersFile([]);
    assert.equal(found.where, "next to the Premiere project");
    assert.equal(found.text, "{p}");
  } finally {
    env.restore();
  }
});

test("tries the other URL forms when the first one is refused, and gives null (not an error) when nothing is found", async () => {
  const env = setup({ folders: { "file:///E:/Videos/2026-10-14%20-%20D%C3%9AO": [file("IlloJuan - part1.markers.json", "{x}")] }, projectPath: "" });
  try {
    const found = await adapter.findMarkersFile([]);
    assert.equal(found.text, "{x}");
    assert.equal(env.tried.length, 2);
  } finally {
    env.restore();
  }
  const none = setup({ folders: {}, projectPath: "" });
  try {
    const why = [];
    assert.equal(await adapter.findMarkersFile(why), null);
    assert.ok(why.some((w) => /failed: no access/.test(w)), "the reason is in the log lines");
  } finally {
    none.restore();
  }
});

test("two markers files that cannot be told apart are not guessed", async () => {
  const env = setup({ folders: { [MEDIA_DIR_URL]: [file("x.markers.json", "{1}"), file("y.markers.json", "{2}")] }, projectPath: "" });
  try {
    assert.equal(await adapter.findMarkersFile([]), null);
  } finally {
    env.restore();
  }
});
