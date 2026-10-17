# LuckyTwitch Markers (Premiere Pro panel)

Imports the `.markers.json` that LuckyTwitch Downloader writes next to each part, as **colored markers on your active sequence**: one color for game changes, clip markers colored by how many views the clip has, the clip's creator, views and link in the marker comment. It adds to the sequence you are editing instead of importing a separate sequence like the XML does.

### What changed in 0.7.3: the delete closes the holes Premiere's ripple leaves

**What your 0.7.2 log shows (numbers worked out from the log, in frames of 16.67 ms):**

| Scenario | Removed pieces | Hole left in all | Per removed piece |
|---|---|---|---|
| A: 1 piece, ripple=true | 1 | 1 frame (later pieces moved 3178.98 frames; the piece was 3179.94 long) | 1.00 |
| C: same with shiftOverLapping=true | 1 | 1 frame | 1.00 |
| G: MediaType.VIDEO | 1 | 1 frame | 1.00 |
| E: 2 adjacent pieces | 2 | 2 frames | 1.00 |
| D: 10 non-adjacent pieces | 10 | 8 frames | 0.80 |
| F: 99 non-adjacent pieces | 99 | 71 frames | 0.72 |
| the real batch of 60 | 60 | 43 frames | 0.72 |

- **It is per removed piece, between 0 and 1 frame each, and never more than 1 frame in any measurement.** It is not a constant frame per action (1 piece in an action left 1 frame, 99 pieces left 71, not 1), not per batch, and `shiftOverLapping` makes no difference. The average (0.72 to 0.80) is not a constant either, so a fixed compensation of the expected positions cannot be right.
- **Scenario B (ripple=false) left every piece exactly in place and removed it, so the second argument really is "ripple".** The NO in lines 1, 4 and 5 of your RESULT block is this 0-to-1-frame shortfall, not a wrong guess about the argument.
- After the ripple, the kept pieces sit on whole frames (0.017 s, 30.033 s, 60.050 s are frames 1, 1802, 3603), while before it the cut points sat a fraction of a frame off the frame lines (17261.998 s is 1035719.88 frames). My reading, **inferred and not proven**: Premiere rounds the shift to whole frames, so a removed piece whose length is not a whole number of frames closes by a frame less. It fits the 0.72 average and the first four pieces (exactly 1 frame each), but I have not seen Premiere's own arithmetic.
- Also in the log: with video **and** audio selected, ripple moved the test clips on V2 / A2 too (about the removed length, with the same shortfall); with a **video-only** selection (H) it removed the piece and moved nothing at all, not even V1; with MediaType.VIDEO (G) the audio pieces were removed and not closed. The delete uses video + audio + MediaType.ANY, as before. Because other tracks do move, delete the gaps **before** you add music or overlays (you already do).

**What 0.7.3 does about it (verified on the fake timeline only):**

1. Batches of up to 60 gap pieces are ripple-deleted exactly as before.
2. The read-back check is no longer "every piece exactly where a ripple puts it". Every remaining piece must keep its source in / out and its length (quarter frame), and the hole in front of it may be **0 to 1 frame for each removed piece in front of it** (plus a quarter frame of reading noise); nothing may close too far (that would be an overlap), and no hole may appear where nothing was removed. Anything else stops the run, as before (3 frames short per piece, a ripple that does nothing, audio left behind...).
3. **The holes are closed, in the same batch, by lengthening the piece in front of each hole until it meets the next one** (`createSetEndAction`, video and linked audio in one edit), and the hole in front of the first piece by pulling its start back to where a ripple puts it (`createSetStartAction`; the source in point moves along, as the cut saw on your Premiere). Nothing is moved, so nothing can overlap. Then every piece of every track is read back: touched pieces at their new edge with the source in / out moved by exactly the added length, untouched pieces exactly as before. A hole under 1 ms is left alone.
4. The log says it: "Batch 1 done in 640 ms: 60 of 109 gap pieces deleted. Premiere left 43 holes (716.7 ms = 43.0 frames in all, for 60 removed pieces); closed by lengthening the piece in front of each ... Every remaining piece checked." The Done line says it too.
5. Stop and resume work as before: a batch is never left half closed unless a check fails, and then it stops and says what is left (including the case "the gap pieces are deleted but the holes are only partly closed").

**What this changes in your edit, so you can decide if you accept it:** a clip can end up **up to one frame longer at its end** (the extra frame is the source after the clip, which is inside the padding you set, or a bit of the next stretch if the padding is 0), and the first clip starts one frame earlier. The timeline ends up to about 0.7 s longer over the whole VOD than an exact ripple would give (43 frames over 108 clips in your first batch). Clips are back to back with no hole. The pieces still count as the clips: running the delete again finds nothing to delete (when a clip has two removed pieces in a row in front of it, the second run may call that piece "uncertain" because it is now 2 frames longer than the clip plus padding; it then refuses without touching anything).

**Test ripple delete** (still on a copy, still pressed twice) has a new scenario **I** (3 non-adjacent pieces: ripple, then the same hole-closing the real delete uses, then a read-back of everything) and two new lines in the RESULT block: **9** (hole per removed piece for each ripple scenario, and whether all are within one frame per removed piece) and **10** (did closing the holes read back exactly as asked). If 9 and 10 are YES on your Premiere, the real delete will work; if 10 is NO it says what Premiere did instead. Please run it before the real delete and send the log.

**Not checked on a real Premiere (fake timeline only): please test on a copy of the project.**
1. `createSetEndAction` used to **lengthen** a piece into the empty space after a ripple (the cut only shortens the original with it), and `createSetStartAction` pulling the first piece's start back with its in point (seen carrying the in point in the cut, but there it moves forward). Scenario I measures both. If the in point does not move along, the run stops after the delete with a message, not silently.
2. That a batch of 60 never leaves more than 1 frame per removed piece: your real batch had 0.72, the experiment up to 1.00 for single pieces and for 99 pieces 0.72, so there is margin, but not a proof.
3. That the extended piece may reach the end of its source: the last clip of a VOD that ends at the end of the file has no next piece, so it is never extended; a clip followed by a hole inside the file always has source after it.
**Not built on purpose:** moving the kept pieces with `createMoveAction` instead. Adobe's docs only say it "moves the inPoint of the track item to a new time, by shifting it by a number of seconds" and nobody has measured on your Premiere whether the offset is relative, whether it may be negative, or whether linked audio follows. Lengthening needs none of that, so it comes first; if scenario I fails, the move is the next experiment.
**Unchanged:** the Project-panel selection probe still waits for your log (open item 1 of 0.6.x), and *Do it all* still forces one backup on a resume (item 2).
- To undo a failed delete: Ctrl+Z (the closing is its own undo step, so the delete and the closing take two) or open the backup sequence. If you still have the project where the 0.7.2 delete stopped after its first batch, that timeline has 1-frame holes and 156 pieces left: undo it or reopen the backup first, because 0.7.3 expects to be the one that closes the holes it creates.
- Tests: 159 (was 144): the new core check, Premiere closing 0 or 1 frame short per piece at the size of the real VOD, fractions of a frame, 3 frames short and closing too far (refused), Stop with holes, closing that does nothing, setStart that does not carry the in point, the experiment's scenario I, and the Done line.

### What changed in 0.7.2

- **Found on the first real delete (9.5 h VOD):** Premiere's ripple worked (60 gap pieces went from V1 and A1 in the first batch, 156 of 216 pieces left), but each kept piece ended up one more frame to the right than a ripple of the removed length gives (piece 2 by 2 frames, piece 3 by 3 frames...), i.e. a 1-frame hole before every kept piece. The read-back check stopped the run, as designed; 0.7.1 only noticed because the error added up. Reading it as "each removed piece is closed one frame short" is an inference from three pieces, not yet measured.
- **The read-back check is now strict** (a quarter of a frame, was a whole frame), so a one-frame shortfall is caught even when only one piece is removed.
- **The failure message and Test ripple delete now measure the drift:** "Drift: first remaining piece 16.7 ms, last 3000.0 ms (+ = too far right) after 60 removed pieces before it: about 50.00 ms per removed piece = 3.00 frames." Run the experiment on a copy and send the log: it shows whether the shortfall is a constant frame per removed piece, whether it depends on selecting several pieces at once, and whether `shiftOverLapping` changes it. No workaround is built yet, on purpose.
- To undo a failed delete: Ctrl+Z once (a batch is one undo step) or open the backup sequence made right before it.

### What changed in 0.7.1

- **Fix: 0.7.0 did not start** ("Module not found: ./premiere-adapter.js" in the log). The adapter declared a top-level `plural` that `markers-core.js` already declares; the panel loads both as classic scripts in one global scope, so the adapter failed to load. Node's `require` hides that kind of clash, so `test/scripts-load.test.js` now loads the scripts the way the panel does. Nothing else changed.

### What changed in 0.7.0: delete the gaps (ripple delete)

After Do it all the timeline is cut into pieces at every clip edge. 0.7.0 deletes the pieces you do not want (the stretches between the clips) with a ripple delete, so what is left is the clips back to back.

- **Delete the gaps** (red button under the Cut buttons). It looks at the pieces on the timeline and sorts each one by the part of the *source* it plays: **keep** (inside a keep range: the clips, with your padding and merge settings; chapters are not ranges), **gap** (touches no range) or **uncertain** (holds only part of a clip, because a cut is missing or the padding / merge settings changed since you cut). Only gaps are ever deleted. The button label and the line under it are the preview: "Will delete 108 pieces, 31,096 s, 90.4%; keep 108 pieces, 3,284 s, after one backup."
- **Two clicks.** The first click re-reads the timeline, shows the preview and arms the button ("Click again to delete 108 pieces"). Nothing is changed. The second click (within 30 s, and only while the preview is unchanged: changing any setting cancels it) runs. The run re-checks everything and refuses if the timeline no longer matches the preview.
- **Safety guard, all before anything is touched.** It refuses when: any piece is uncertain; a video piece has no linked audio piece with the same start and end (the audio would be left behind); fewer than *Need at least N pieces to keep* (default 1) would be kept; it would delete more than *Refuse to delete more than N %* (default **99**: a real VOD keeps only about 10%, so deleting around 90% is normal); or the time the classification keeps differs from what the plan says should be kept (the clip ranges clamped to what the timeline plays) by more than a tolerance of a few frames per clip edge. Settings > *Delete the gaps: safety*.
- **Forced backup.** One backup of the sequence right before the delete (the 30-minute "fresh backup" skip does not apply). With the backup box off it says so in the preview.
- **How it deletes.** In batches of up to 60 gap pieces: the video pieces and their linked audio pieces together in one `createRemoveItemsAction(selection, ripple = true, MediaType.ANY, false)`. After every batch the timeline is read back and **every remaining piece on V1 and the linked audio tracks must sit exactly where a ripple of the removed pieces puts it, with the same source** (within a frame); the first mismatch stops the run and says how many gap pieces are deleted and that the failed batch may be partly applied (Ctrl+Z, or the backup). **Stop** finishes the batch it is in; pressing the red button again works out what is left and asks for the confirmation again. Progress: "deleting gaps · batch 2/4 · 60 of 109 gap pieces".
- **Only in chapter** works with it: pieces entirely outside the chapter are left alone; a piece crossing the chapter's edge is uncertain and refuses.
- **Do it all** has a new last step, *Delete the gaps* (Settings > Do it all, off by default). The confirmation comes **before** the run: the first press of Do it all shows "This run will delete the gaps at the end: ..." (worked out from the pieces the cut *will* make) and arms the button; the second press runs backup, markers, cut, delete. A run never stops to ask. If the delete step finds the timeline different from that preview it refuses and says so. Auto-run never runs a recipe that deletes.
- **Other tracks.** The plugin only touches V1 and its linked audio. If other tracks hold items, the log notes it before deleting; whether a ripple delete moves them depends on your Premiere (the experiment below answers it).
- **Troubleshooting > Gap plan** (read-only, also part of *Run all probes*): the classification, the guard's verdict and a few example pieces, so you can see what the red button would do.
- **Troubleshooting > Test ripple delete** (experiment, **run it on a copy of the project**, on a timeline already cut into at least 8 pieces; press it twice, the first press only arms it; many undo steps). It puts test clips on the empty V2 / A2 after the first piece, then removes pieces in eight ways and measures every result: 1 piece with ripple true / false / shiftOverLapping; 10 non-adjacent pieces; 2 adjacent pieces; up to 100 non-adjacent pieces; MediaType.VIDEO with video and audio selected; a video-only selection. At the end the log has a **RESULT** block answering: do later V pieces move left by exactly the piece's length, is the linked audio removed and closed too, do other tracks move, is the second argument really "ripple", do several non-adjacent pieces close every gap, how long one action takes for 1 / 10 / up to 100 pieces. Please send that log.
- **Project selection probe** now prints, for each selected item, its name, type (with the `ProjectItem.TYPE_*` name), whether `ClipProjectItem.cast` gave an object, and the media path on the item and on the cast, to find out why 0.6.x accepted 0 clips. `projectSelectionClips` itself is unchanged until that log is seen.
- Tests: 140 (was 101). The fake timeline's `createRemoveItemsAction` now implements ripple (selected tracks / all tracks / ignored / audio left behind) and media types; new tests cover the classifier, the guard (including numbers shaped like the 9.5 h VOD), batching, Stop and resume, refusals before anything is touched, a batch that misbehaves, other media on the track, the experiment's answers under each behavior, and the panel (preview, two clicks, cancelling, Do it all with the delete step, auto-run).

**Not checked on a real Premiere (only on the fake timeline / fake DOM): please test on a copy of the project and send the Troubleshooting log.**
1. **That the second argument of `createRemoveItemsAction` is "ripple"** and that a selection holding V1 and A1 pieces with `MediaType.ANY` closes the gap on both tracks. Run *Test ripple delete* first. If the answers are not YES, the real delete will refuse at its first batch check (it verifies, it does not assume).
2. Whether a ripple delete moves items on other tracks, and how long an action takes for many pieces (the batch size 60 is a guess until the timings are known).
3. Whether the track items kept in memory stay valid after a delete: the engine avoids relying on it by re-reading the tracks before every batch.
4. That the panel stays responsive and Stop is clickable while Premiere works on a batch.
5. The classification on your real cut timeline: use *Gap plan* first. Cuts land within half a frame of the request; the tolerance for "on the edge" is half a frame plus 10 ms.
**Not built:** the fallbacks (disabling the gap pieces with `createSetDisabledAction`, or closing the gaps with `createMoveAction`). They only make sense once the experiment shows what ripple does; the delete engine stops at the first check that fails instead of switching method by itself.
Unchanged on purpose: *Do it all* still forces one backup per run, including a resume after Stop (open item 2 of 0.6.x).

### What changed in 0.6.1

- Found with the 0.6.0 probes on a real Premiere: `ProjectUtils.getSelection(project)` came back empty. The panel now also asks each Project panel for its own selection (`getProjectViewIds` + `getSelectionFromViewId`) when that happens, and the *Project selection* probe prints every route it tried.
- The *Cut plan* probe counts only the cuts still to make (after the frame snapping the real cut uses), so on an already cut timeline it says "No cut left to make" instead of counting points that sit 3 ms from an existing cut. It also shows a clip that was split over several pieces as one line.
- Seen in the same log and left as it is: cuts land 3 to 8 ms before the requested time in the first 35 minutes (Premiere's own frame grid). Every cut is checked to be within 20 ms of the request, and requests come straight from source time, so nothing builds up over a long VOD.

### What changed in 0.6.0: Do it all

- **Do it all** (top of the actions card): one button that runs your saved recipe. The recipe is three tick-boxes in **Settings > Do it all**: *Add the markers*, *Cut at clips*, *Cut at chapters* (default: markers + clips). The button label is a live summary: "Do it all: 21 markers + cut 19 clips". Ripple delete is not part of it (planned for 0.7.0).
- **Pre-flight, before anything is touched.** It checks that a file is loaded, that the markers have a place to go, that the file's video is on the timeline, that **an empty track exists above V1 and above each linked audio track** (the cut needs them; before, it failed halfway), and that enough clips fall inside what the timeline plays (*Need at least N clips*, default 1). The result is one line under the button ("Will add 21 markers, then cut at clips: 28 cuts in 5 rounds, after one backup of the sequence." or "Not ready: ...") with the ticked/crossed checks under *pre-flight checks*. If a check fails, nothing is changed. If everything in the recipe is already done, it says so and does nothing.
- **One backup per run.** Do it all makes one backup copy of the sequence (only when the recipe cuts and the backup box is on) and the cut inside it makes none. The single *Cut at clips / chapters* buttons skip their backup when this panel already made one of the same sequence in the last 30 minutes (this session only).
- **Progress and Stop.** While it runs the buttons are locked and you see "Step 2/2 · cutting · round 4/6 · 14 of 38 cuts" with a bar. **Stop** finishes the round it is in (a round is never cut short, so the timeline stays consistent) and stops. Run it again to finish: points that already have a cut are skipped. The single Cut buttons show the same progress and Stop.
- **Stops at the first failure and says what is left**: which steps are done, which were not run, how many cuts were made, and whether temporary copies are still on the workspace tracks.
- **Only in chapter** (under the Do it all line, shown when the file has chapters): limits the markers and the cut points to one chapter. A clip that crosses the chapter's edge keeps only the part inside it for cutting; for markers a clip belongs to the chapter it *starts* in.
- **Project-panel selection.** The panel looks next to the clip selected in the Project panel for the `.markers.json`, and markers on the clip go on that clip, so you can add markers right after importing, **before the video is on a timeline** (not even a sequence is needed). Order for "on the clip": the Project-panel clip that is this file's video, the file's video on the timeline, any clip selected in the Project panel, the selected/first timeline clip.
- **Markers on the sequence are placed through the clip that plays each marker** (source time to timeline time, also after you trimmed or cut). A marker that no clip plays is left out and counted. The old setting *The part starts at the sequence start / the playhead* is gone; the file's video must be on the timeline for this placement.
- **Opt-in auto-run** (Settings > Do it all, off by default): when a markers file is found by itself, the recipe runs once for that file if the pre-flight passes and there is still something to do. A file you chose by hand is never run for you.
- **Less log noise**: "(detect) stopped: No project is open" no longer repeats every 4 seconds; any other detection error is logged once.
- New probe in Troubleshooting: **Project selection** (also part of *Run all probes*), to see what `ProjectUtils.getSelection` returns on your build.
- Tests: 99 (was 55). The fake-timeline tests cover progress, Stop and the follow-up run, the shared backup, the workspace facts and the failure state; `test/ui.test.js` covers the label, pre-flight, Do it all, Stop, chapter limit, auto-run and the quiet log.

**Not checked on a real Premiere (only on the fake timeline / fake DOM): please test on a copy of the project and send the Troubleshooting log.**
1. What `ProjectUtils.getSelection(project)` returns (the code accepts an array, or an object with `items` / `getItems()`, and keeps only items that have a media file path). Use the *Project selection* probe first.
2. That the backup recency check can read the sequence's `guid` (else `sequenceID`, else `name`). If none can be read, every cut button still makes its backup, as in 0.5.0.
3. The whole Do it all sequence in one go (backup, markers, cut), and *Cut at clips + chapters* as one pass.
4. That the panel repaints the progress while Premiere is busy with a round, and that Stop is clickable then.
5. Markers on the sequence mapped through the real clip data, and the pre-flight's empty-track check against your real V2/A2 (linked audio is still recognised by the same start and end as the video).
6. Auto-run timing (it is offered the chance after every timeline look: panel shown, focus, after each action).
Known limit: *Remove these markers* with markers on the sequence maps through the timeline as it is now, so it will not find them if you moved the clips since.

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
2. Import the video and select it in the Project panel, or put it on a sequence (a sequence is only needed for cutting).
3. Open the panel. If the `.markers.json` is next to the video (or the project) it is loaded by itself; otherwise press **Choose .markers.json…** and pick it. A card shows the stream, the part and how many game changes and clips it holds. Press **Do it all** (your saved recipe), or **Add N markers** and the Cut buttons one by one. Where they go (on the clip, so they follow your cuts, or on the sequence), the colors and the filters are under **Settings**, which you set once. If the picker will not open on your Premiere, open **Troubleshooting** and paste the file's text there.

The plain `.markers.xml` option is still there for anyone who does not want the plugin.

- **Colors:** Premiere only has eight marker colors (Green, Red, Purple, Orange, Yellow, White, Blue, Cyan). Clips use three tiers by view count; the thresholds and colors are editable and remembered.
- **Only what matters is shown:** color menus for games appear when game changes are ticked; the three view tiers appear when *Color by views* is on, otherwise one color for all clips.
- **Where:** on the clip (default, they follow your cuts) or on the sequence, each at the place where the clip that plays it has it.
- **Undo:** one Undo removes everything an import added (markers and colors are two steps if coloring runs).

## Diagnostics

Open **Troubleshooting** at the bottom of the panel (it opens by itself when something goes wrong). It holds the paste box, the two diagnostics buttons and the copyable log.

**Run all probes** runs every read-only probe below in one go: copy the log and send it. The buttons next to it run them one by one.

- **API** lists what this Premiere build offers on the objects the plugin uses.
- **Gap plan** (0.7.0) is a dry run of the delete: how each piece is classified (keep / gap / uncertain) and what the safety guard says. Nothing is changed.
- **Clips** lists the video clips on the timeline with where each sits and which part of its source it plays. **Audio** does the same for audio and says which audio clip looks linked to which video clip.
- **Editor** shows what the sequence editor offers (looking for anything like a razor). **Classes** lists the members of many classes and the values of the `Constants` enums.
- **File detection** runs the search for the markers file and prints every step (the paths it opened, what each folder holds).
- **Cut plan** is a dry run: for the loaded file and the target clip it prints where the clips *would* be cut on the timeline, how many cuts, and how long the result would be. Nothing is changed.

Experiments (they change the project; Ctrl+Z undoes them):

- **Test ripple delete** (0.7.0) measures what the ripple delete does on your Premiere, on a copy of the project (see the 0.7.0 notes above).
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
