# LuckyTwitch Markers (Premiere Pro panel)

Imports the `.markers.json` that LuckyTwitch Downloader writes next to each part, as **colored markers on your active sequence**: one color for game changes, clip markers colored by how many views the clip has, the clip's creator, views and link in the marker comment. It adds to the sequence you are editing instead of importing a separate sequence like the XML does.

### What changed in 0.5.0: cut anything, any time

- **It works from source time, so it works on an already cut or trimmed timeline.** The marker times are seconds into the video file. For every timeline clip that plays that video, the panel reads which part of the source it plays and maps the cut points through it. Delete the first hour of a stream first, or cut by hand, or run the plugin twice: the cuts still land on the right frames, markers before the start of what the timeline plays are ignored, and a point that already has a cut is not cut again. Reversed-speed clips are skipped.
- **The right video is found by the file, not by selection.** The clips to cut are the ones that play the video the `.markers.json` was found next to (else the video named like the file, else the selected or first clip). Another video on the timeline is left alone. Only the lowest video track holding that video is cut.
- **New button: Cut at chapters** (the game / category changes). *Cut at clips* and *Cut at chapters* sit right under *Add markers*, each with a live count of what falls inside what the timeline plays ("Cut at 14 of 19 clips").
- **Compact panel.** The marker file is one line (details fold open); the buttons are at the top; a line says what the timeline plays of the video.
- **Settings > Cutting:** keep N seconds before / after each clip, merge clips closer than N seconds, and the backup box (moved here, on by default). Clips that touch or overlap, also after padding, become one clip: padding never adds a cut between them.
- Cut plan (dry run) now reports the same plan the cut will use (it used to look only at the first clip, which after a cut is a gap, so it said "0 cuts").
- New tests: the fake-timeline tests cover a deleted start, an already cut timeline, chapters, padding and other videos; `test/ui.test.js` checks the panel wiring with a fake DOM.
- Not yet checked on a real Premiere: cutting more than one clip in the same run, and the new button counts. Try it on a copy of the project first and send the log.

> **Status: beta (0.4.0).** Checked on a running Premiere Pro 2026 (0.3): the file picker, markers on the sequence and on the clip, and coloring. **New in 0.4 and not yet checked on a real Premiere:** finding the file by itself, *Remove these markers*, and everything under Probes / Experiments. If something does not work, run **Run all probes** (Troubleshooting) and send the log.

### What changed in 0.4.1: cutting

Premiere's UXP API has **no razor / Add Edit call** (Adobe confirms this in the community forum), so a cut is built from clone + trim actions: for each cut point the clip is copied to an empty track above, the original is shortened to the cut, the copy is trimmed to start at the cut, copied back down, and the temporary copy removed. Effects and speed are kept because the real clip is copied. *Test split (clone + trim)* in Troubleshooting is the one-cut test (checked on a real Premiere); **Cut at clip starts and ends** (card 3) runs it at every clip start and end of the loaded file, on the selected video clip (else the first one) and the audio clips with the same start and end.

- Needs an **empty video track and an empty audio track above** the clip (the workspace).
- It works in **halving rounds**: round 1 cuts the clip at the middle cut point, round 2 cuts both halves at their middle points at the same time, and so on, so 38 cut points take 6 rounds of 4 timeline edits (video and audio together) instead of 38 separate cuts.
- Every cut is checked (the second half must start at the cut and play the source from there); the first failure stops the run and says where. Nothing is deleted, only split.
- Each cut is several undo steps, so the panel makes a **backup copy of the sequence** first (box in card 3). Cut points are snapped to the sequence's frames.
- Not yet verified on a real Premiere with many cuts in a row: try a short part or a copy of the project first and send the log.

### What changed in 0.4

- **The panel finds the `.markers.json` by itself**: next to the video of the selected clip (else the first video clip), then next to the Premiere project. If it finds it, the card shows it and the **Add** button is ready; "Choose…" is only for when it does not. It looks again when you come back to the panel, and every few seconds while no file is loaded.
- **One Add button.** *To sequence / To clip* became a setting (**Markers go: on the clip / on the sequence**, default on the clip).
- **Settings are folded away** under the Add button, with a one-line summary, so the button is always on screen.
- **No duplicates**: pressing Add twice does not add the markers twice (it only recolors); **Remove these markers** takes the file's markers off the target again.
- **Probes** for the next feature (cutting the clips at each marker): Audio, Editor, Classes, File detection, Cut plan (dry run), *Run all probes*, and the experiment *Test cut at playhead*.
- The manifest now asks for **full file access** (`localFileSystem: "fullAccess"`), needed to read the folder next to the video without a picker. Premiere may ask you to allow it. Reinstall the plugin (version 0.4.0 is a new folder name).

Needs Premiere Pro 2026 (UXP panels; `minVersion` in `manifest.json` is 25.6.0).

## Install

**Double-click `LuckyTwitch-Premiere-Plugin.ccx`** (from the release page). Creative Cloud Desktop installs it, then restart Premiere Pro and open the panel from the Window menu (Window > UXP Plugins). Needs the Creative Cloud Desktop app, which Premiere comes with.

If an older copy was installed with `install-dev.bat`, remove it first (`install-dev.bat -Uninstall`) so two copies do not sit side by side.

### Manual install (if the .ccx will not open)

Unzip `LuckyTwitch-Premiere-Plugin.zip` and double-click `install-dev.bat`. It copies the plugin to `%APPDATA%\Adobe\UXP\Plugins\External\com.luckytwitch.premiere-markers_<version>` (Premiere only loads it if the folder is named `<manifest id>_<manifest version>`; the script reads both from `manifest.json`), replacing any earlier copy. Then restart Premiere Pro. Run it again after every change to the plugin. `install-dev.bat -Uninstall` removes it.

You may need **Enable developer mode** in Premiere's UXP plugin settings. If the panel does not show up, check the folder name first.

Alternative: **UXP Developer Tool** (Creative Cloud Desktop > All apps), Add Plugin, pick `manifest.json`, Load. The panel then appears under the Window menu.

## Use

1. In LuckyTwitch Downloader, tick **Also export a .markers.json for the LuckyTwitch Premiere plugin** (and **Also mark the game / category changes** if you want games). Download as usual. The `.markers.json` appears next to each part.
2. Put the part on a sequence in Premiere and make that sequence active.
3. Open the panel. If the `.markers.json` is next to the video (or the project) it is loaded by itself; otherwise press **Choose .markers.json…** and pick it. A card shows the stream, the part and how many game changes and clips it holds. Press **Add N markers**. Where they go (on the selected clip, so they follow your cuts, or on the sequence at fixed times), the colors and the filters are under **Settings**, which you set once. If the picker will not open on your Premiere, open **Troubleshooting** and paste the file's text there.

The plain `.markers.xml` option is still there for anyone who does not want the plugin.

- **Colors:** Premiere only has eight marker colors (Green, Red, Purple, Orange, Yellow, White, Blue, Cyan). Clips use three tiers by view count; the thresholds and colors are editable and remembered.
- **Only what matters is shown:** color menus for games appear when game changes are ticked; the three view tiers appear when *Color by views* is on, otherwise one color for all clips.
- **Where:** markers are placed from the start of the sequence, or from the playhead if you choose that (use it when the part does not start at 0:00 of the sequence).
- **Undo:** one Undo removes everything an import added (markers and colors are two steps if coloring runs).

## Diagnostics

Open **Troubleshooting** at the bottom of the panel (it opens by itself when something goes wrong). It holds the paste box, the two diagnostics buttons and the copyable log.

**Run all probes** runs every read-only probe below in one go: copy the log and send it. The buttons next to it run them one by one.

- **API** lists what this Premiere build offers on the objects the plugin uses.
- **Clips** lists the video clips on the timeline with where each sits and which part of its source it plays. **Audio** does the same for audio and says which audio clip looks linked to which video clip.
- **Editor** shows what the sequence editor offers (looking for anything like a razor). **Classes** lists the members of many classes and the values of the `Constants` enums.
- **File detection** runs the search for the markers file and prints every step (the paths it opened, what each folder holds).
- **Cut plan** is a dry run: for the loaded file and the target clip it prints where the clips *would* be cut on the timeline, how many cuts, and how long the result would be. Nothing is changed.

Experiments (they change the project; Ctrl+Z undoes them):

- **Test cut at playhead** tries to split the video clip under the playhead in two (and its audio), the way a razor would, by overwriting the second half with the same source range. It prints each step and the clips afterwards. It is the test for cutting at every clip.
- **Test clip markers** adds 3 markers to the *source* of the selected clip and reads them back.
- **Add test markers** puts eight markers at 0, 5, 10… seconds, each named with the color the plugin *thinks* its color index is. If a marker's color does not match its name, the color order in `src/markers-core.js` (`COLORS`) needs adjusting.

## Development

```
manifest.json            UXP manifest (panel entry point)
index.html               the panel
src/markers-core.js      pure logic: read and check the file, settings, colors, plan (tested)
src/premiere-adapter.js  every call into Premiere (the only file to fix when the API differs)
src/main.js              UI wiring (file search, settings, buttons)
test/                    node tests (fixture in test/fixtures; the repo's ../tests/fixtures copy is used when present)
```

```
npm run check     # syntax check
npm test          # needs Node 20+, no dependencies
```

The file format is described in [`../docs/markers-format.md`](../docs/markers-format.md).
