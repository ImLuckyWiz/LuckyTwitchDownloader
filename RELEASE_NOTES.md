## v1.12.0

This release updates the Premiere Pro plugin (0.5.0). The downloader itself is unchanged; existing downloads, settings and marker exports continue to work as before.

### Premiere Pro plugin
- **Cut at clips** and **Cut at chapters** add timeline cuts at clip markers or game/category changes from a `.markers.json` file.
- Cuts are mapped from the video's source time onto the timeline, so they work with footage that has already been trimmed or cut. The plugin targets the matching video, ignores points outside the played source range, and avoids adding cuts where one already exists.
- Choose how much footage to keep before and after clips, merge nearby clips, and make a backup sequence before cutting. The dry-run cut plan now matches the actual cut plan.
- A more compact panel shows the loaded marker file and the portion of the video present on the timeline, with live counts for the available cuts.
- Existing marker import and `.markers.xml` export remain available.

**Before cutting:** leave an empty video track and an empty audio track above the footage. Cutting uses multiple Premiere edits and has not yet been verified on a real Premiere project with multiple clips in one run. Keep the backup enabled and try it on a copy of your project first.

## v1.11.0

A redesign of the rest of the app, to match the new Options tab from v1.10. Nothing was removed and nothing works differently: saved settings, the queue and the files the app writes are the same as before.

### Search tab
- When you are not signed in, a purple banner says so and has a **Sign in...** button. Searching is switched off until you sign in.
- Every list explains itself while it is empty: what to do first, "nothing found for ..." after a search with no results, "this streamer has no VODs" with the reason, and "loading..." while a page is being fetched.
- The VOD header counts the videos (and says when there are more to load). "Double-click a VOD to use it" now sits next to the **Use this VOD** button.
- Results and Recent streamers are cards. Column headings line up with their columns.
- At the smallest window size the title above the VOD list wraps instead of squeezing the video-type drop-down.

### Plan tab
- The page is three cards: **Timeline**, **Cut points** and **Clips -> chapters**.
- The chapters option is a switch, like the ones in Options (the last checkbox in the app is gone).
- The **Add to queue** buttons and the one-line summary of your cuts stay visible at the bottom while you scroll. The summary turns red only while the cuts are wrong.
- Hints wrap to the width of their card, and the chapter column is wide enough for its title.
- The timeline's help line wraps instead of being cut off at the smallest window size.
- Keyboard: Tab now goes through the Plan tab from top to bottom and ends on **Add to queue**, then **Add & start** (before, the bottom bar came first).

### Queue & log tab
- Each job is coloured by its status, with a small icon in front: grey `○ queued`, purple `▶ running...`, green `✓ done (3 files)`, red `✕ failed`, amber `■ cancelled`.
- A one-line count sits above the list, for example "1 running · 2 queued · 1 done · 1 failed".
- An empty queue says "Nothing in the queue yet" and has a **Go to the Plan tab** button.
- The log is coloured: errors red, warnings amber, successes green, timestamps and "Queued:" lines muted.
- New **Copy log** and **Clear log** buttons under the log, handy for bug reports.

## v1.10.1

### Fixed
- **Long parts crashed Premiere Pro when imported.** Parts longer than about 1 h 40 min (a 2 h 09 min part was the one that showed it) opened fine in video players but made Premiere Pro quit while importing them. Newer ffmpeg builds write the MP4 header with a very fine time unit (1/720000 s instead of 1/1000 s), and on long parts the numbers in the edit list stop fitting in 32 bits, which Premiere's importer cannot handle. The app now always asks ffmpeg for the normal unit. Audio and video stay in sync, nothing is re-encoded, and the parts are the same size.
- A part that was already finished by yt-dlp with the wrong header is rewritten (stream copy, header only, a few seconds) instead of just being moved.

### Good to know
- Parts you already downloaded keep the problem. To fix one without downloading it again: `ffmpeg -i "part.mp4" -map 0 -c copy -movie_timescale 1000 "part-fixed.mp4"`
- MKV output is not affected.

## v1.10.0

### Added
- **A new look.** The app has a new icon (a purple rounded square with a white download arrow), used in the window, the taskbar, the installer and the Mac app. The theme keeps the dark and purple colors but is flatter and roomier:
- The main button of each screen is filled purple (**Get info**, **Search**, **Use this VOD**, **Start queue**).
- Checkboxes are rounded, fields get a purple outline when you click in them, scrollbars are slimmer, and tabs and tables have more room.
- The base font is a bit bigger (10 instead of 9).
- **The Options tab has a sidebar.** Instead of one long page, the sections are on the left and only one shows at a time: **Output**, **Cuts**, **Chapters**, **Premiere Pro**, **Chat**, **Clips** and **Tools**. The Up and Down keys move through them.
- Every setting is a row with its name, a one-line hint and the control on the right. The longer explanations are in the small **i** next to the name: hover it.
- All on/off settings are now **switches**.
- The Premiere options (plugin `.markers.json`, game changes, `.markers.xml`, `.clips.json`) are together in **Premiere Pro**.
- Settings you set once and rarely touch are under a collapsed **Advanced** line in Output, Cuts, Premiere Pro and Chat: download threads, file and folder names, auto threshold, the plain `.markers.xml`, `.clips.json`, and the chat format and emotes.
- **File names are easier to set up.** The file name, stream folder, single-clip name and chapter title fields have clickable `{token}` buttons that insert the token where your cursor is, and an **Example:** line that shows the real result as you type. Once you load a VOD, the example uses that VOD's name. The stream folder field greys out while *Organize in subfolders* is off.

### Good to know
- Nothing was removed and nothing changed in how files are written. Your saved settings carry over as they are, and the Premiere plugin is unchanged.
- *Add clips as chapters* is still in the Plan tab. The Chapters section in Options holds how the chapters look (title, tail, gap name).
- The Search, Plan and Queue tabs get their new look in the next release.

## v1.9.0

### Added
- **A proper app icon.** LuckyTwitch now has its own icon: a purple download arrow with a cut through its shaft. It shows in the window title bar, the taskbar / Dock, the Start menu and desktop shortcut, and in the installer and uninstaller (no more default Python feather).

### Changed
- **A fresher look, same colors.** The dark theme with the purple accent stays, but everything is cleaner:
- The main action of each screen is now a solid purple button: **Get info**, **Search**, **Use this VOD** and **Start queue**. The other buttons are flat and light up when you hover them.
- Check boxes are rounded and turn purple when ticked.
- Fields get a purple outline while you type in them, and the text boxes no longer show a white frame.
- Scrollbars are thinner and have no arrows, tabs are flatter and roomier, tables have more breathing room, and the progress bar is thinner.
- The text is slightly bigger (10 pt instead of 9 pt) to make it easier to read.

### Good to know
- This is the first part of a bigger visual update. The **Options** tab will get a new layout in the next version; nothing moved yet.
- Nothing about how the app works changed: your settings, queue, cut points and downloads behave exactly as before, and the Premiere plugin and its `.markers.json` files are untouched.
- Tests: the app's tests were extended with checks for the icon files, the new look and the new switch widget.

## v1.8.0

### Added
- **Put the markers on the video itself, not just on the sequence (Premiere plugin 0.3.0).** The panel now has two buttons side by side: **To sequence** and **To clip**.
- **To sequence** works as before: the markers sit on the timeline at fixed times.
- **To clip** puts the markers on the video you have selected in the timeline (or the first video clip if none is selected). They belong to the video, so they **follow it through your cuts**: razor it, ripple-delete a piece or move it, and every marker stays on the same moment of the stream.
- **A new look for the plugin panel.** It is organized in three steps: *Marker file*, *What to import* and *Add the markers*.
- After you pick a `.markers.json`, a card shows the stream, the part and how many game changes and clips it holds.
- Each color menu has a dot showing the color, so you see what you are choosing.
- Only the options that matter are shown: the game colors when game changes are ticked, the three view tiers when *Color by views* is on (otherwise one color for all clips), and nothing for clips when clips are off.
- Each button says how many markers it will add, and a status line under them shows progress, success or the error.
- **Troubleshooting section.** The paste box, the diagnostics buttons and the copyable log moved into a collapsed section at the bottom of the panel. It opens by itself when something goes wrong.

### Fixed
- **Marker colors now get applied on every import.** On some Premiere Pro 2026 setups the markers were added but stayed in Premiere's default color, and the panel showed *could not read the markers back from the sequence*. The plugin now reads the markers back fresh after adding them (and retries briefly), so all of them are colored. Checked on Premiere Pro 2026 with a full 53-marker import, both on the sequence and on a clip.
- **macOS builds no longer fail at random** with *hdiutil: create failed - Resource busy*. Creating the DMG now retries a few times.

### Good to know
- **To sequence or To clip?** Use *To clip* if you are going to cut the video (that is the usual case): the markers move with the footage. Use *To sequence* if you only want reference marks on the timeline. Pressing both adds the markers twice, once on the video and once on the sequence.
- **Importing again adds the markers again.** One Undo (Ctrl/Cmd+Z) removes the last import; do that before importing a second time.
- **The playhead option** (*The part starts... at the playhead*) only applies to *To sequence*. *To clip* always uses the video's own time, so the markers line up when the clip plays the part from its start.
- Nothing changes in how the files are written: your existing `.markers.json` files work as they are, and the Python app is unchanged apart from the macOS build fix.
- To update the plugin, install the new version over the old one. With `LuckyTwitch-Premiere-Plugin.ccx`, open it with Creative Cloud. If your PC does not open `.ccx` files, unzip `LuckyTwitch-Premiere-Plugin.zip` and run `install-dev.bat`. Restart Premiere afterwards. If you used `install-dev.bat` before and now install the `.ccx`, run `install-dev.bat -Uninstall` first so there are not two copies.
- The plugin keeps using the same settings storage, so your colors and view tiers should carry over. If they reset, just set them again.

## v1.7.2

### Fixed
- **The Premiere Pro plugin now works.** The panel in v1.7.1 and earlier could start dead: *Choose .markers.json…* did nothing and nothing was shown. It now starts reliably, opens the file picker, and imports the markers (and their colors) into the active sequence. Checked on Premiere Pro 2026.
- **The panel looks right and can be scrolled.** Text was black on gray boxes; the controls now have proper colors for Premiere's dark theme (and light theme). A scroll bar was added so everything is reachable.

### Added
- **A real plugin file: `LuckyTwitch-Premiere-Plugin.ccx`.** Double-click it and Creative Cloud installs the plugin, no more copying folders. The `.zip` (with `install-dev.bat`) is still there for a manual install.
- **A log you can copy** in the plugin panel, with *Copy log* and *Clear log* buttons, plus a *Diagnostics* section to check the plugin against your Premiere.
- **A paste box** under *Choose .markers.json…*: if the file picker will not open on some Premiere, paste the file's text there instead.

### Good to know
- To install or update the plugin: double-click `LuckyTwitch-Premiere-Plugin.ccx` and restart Premiere. If you installed it before with `install-dev.bat`, run `install-dev.bat -Uninstall` first so there are not two copies.
- The Python app is unchanged since v1.7.1.

## v1.7.1

### Fixed
- **The exact segment download now works on newer Twitch VODs.** Some VODs are served as fMP4 (with an init section, `#EXT-X-MAP`), and the app refused them with *"Could not use the segment download (unsupported playlist tag #EXT-X-MAP)"* and fell back to the old method. The segment download now handles fMP4 playlists (and byte ranges), so the part starts at a known segment boundary and the markers line up exactly, instead of being up to 10 s off.

### Good to know
- Encrypted playlists and playlists with discontinuities still use the old method, as before. When that happens, the log line says why.

## v1.7.0

### Added
- **Premiere Pro plugin (beta): colored markers.** In Options → Chapter details, tick *Also export a .markers.json for the LuckyTwitch Premiere plugin*. Each part (or the full VOD) gets a `.markers.json` next to it with every marker's kind (clip or game), time, views and clip details. The new panel in `premiere-plugin/` (download `LuckyTwitch-Premiere-Plugin.zip` from this release) imports it as **colored markers straight onto your active sequence**, instead of bringing in a separate sequence like the XML does.
- In the panel you choose what to import (games, clips, minimum views) and the colors: one color for game changes, and clip markers colored by view tiers (for example red from 50 views, orange from 10, yellow below). The clip's creator, views and link go in the marker comment. Choices are remembered. Markers can start at the beginning of the sequence or at the playhead, and one Undo removes an import.
- The plugin needs Premiere Pro 2026. Install steps are in `premiere-plugin/README.md`. A **Diagnostics** section in the panel helps check that the plugin and your Premiere agree.
- The format of the file is documented in `docs/markers-format.md`. It carries a version number, so a newer file opened by an older plugin gives a clear message instead of failing silently.

### Good to know
- **The `.markers.xml` option is unchanged.** It is a separate checkbox, so you can use the XML, the plugin file, or both. Premiere's XML import still has no marker color, so the XML keeps its `GAME:` prefix.
- *Also mark the game / category changes* now applies to both files. If it is the only marker option ticked, you still get the `.markers.xml` with the games, as before. If the plugin file is ticked as well, the games go into the `.markers.json` (tick the XML option too if you also want them there).
- Marker times in the `.markers.json` count from the start of the part, like the XML. The file also says where the part sits in the VOD (`part.start` / `part.end`), which helps to line it up with the chat file.
- Colors are not stored in the file: the plugin picks them, so you can change the scheme without downloading again. Premiere has eight marker colors to choose from.
- Both marker options are off by default, so nothing changes for existing setups.

## v1.6.0

### Added
- **Chat download (Twitch VODs).** In Options → Chat, tick *Also download the chat of each part*. Each part gets a chat file next to it (`name.chat.json`, or `.txt` / `.html`) that covers exactly the stretch of the VOD the part covers, using the real start and end of the file. *Embed emotes and badges* makes the file bigger but lets it render offline.
- The first time you use it, the app downloads **TwitchDownloaderCLI** (version 1.56.5) into the tools folder, the same way it does with yt-dlp and ffmpeg. Tools shows its status. If you already have a copy next to the app or on your PATH, that one is used.
- **Game markers for Premiere Pro.** In Options → Chapter details, tick *Also mark the game / category changes*. The `.markers.xml` next to each part (or the full VOD) then gets one marker per game, named `GAME: <game>`, spanning the whole stretch, for example `GAME: Just Chatting` from 0:00:00 to 1:00:00 and then `GAME: Resident Evil 2`. For a part, only the games inside it are marked, with times relative to the part. It works with or without the clip markers; when both are on they share the same file. The games are the same ones the Timeline shows as colored bars.

### Good to know
- **Chat times count from the start of the VOD**, not from the start of the part (this is how the `.json` is written). The `start` and `end` inside the file say which stretch it covers. Chat times are whole seconds, so expect up to a second of difference against the video.
- If the chat cannot be downloaded (deleted VOD, no internet, GitHub unreachable), the video is still downloaded and the log says why. A cancelled or failed chat download leaves no empty file behind.
- Chat is skipped for single clips and for links that are not Twitch VODs.
- Premiere's XML import has no marker color, so the `GAME:` prefix is what tells the game markers apart from the clip markers.
- Game markers are off by default, and so is chat, so nothing changes for existing setups.
- TwitchDownloader is MIT licensed and is downloaded on demand, not bundled. See Credits in the README.

## v1.5.2

### Fixed
- **"Download only these parts": the file could start up to 10 s before the time you typed, which shifted the chapters and the Premiere Pro markers.** The app now downloads whole 10-second segments of the VOD itself, so it knows exactly where each file starts. Chapters and Premiere markers (`.markers.xml`) now match the Twitch player.
- The file can still begin a few seconds before your time (at the previous 10-second mark), never after. Times that are multiples of 10 s (for example 20:00:00 or 1:00:00) start exactly.
- The log now shows one line per part with the real start and end, for example `Part 1 starts at 0:20:00 (asked 0:20:03, 3 s early) and ends at 0:21:10`, so you can compare it with the Twitch player.

### Changed
- **Exact cuts** (the re-encode option) with "download only these parts" now cut from the downloaded segments, so the file starts at the exact second you typed. Before, this option still started up to 10 s early.

### Good to know
- If the segment method cannot be used for a VOD, the app falls back to the previous method and says so in the log. In that case the markers can still be up to 10 s off.
- If you already downloaded parts with clip chapters or Premiere markers using "only these parts", download them again to get the corrected positions.
- The "download the full VOD, then split" strategy was already accurate and is not changed.

## v1.5.1

### Fixed
- **Clips were out of sync: they appeared one clip-length too late.** Twitch reports the position of a clip as the moment it *ends*, and the app used it as the moment it *starts*. Every clip start was shifted by the length of the clip (a 60 s clip showed up 60 s late). The start is now calculated as end − length. This fixes all of these at once:
- the **At** column in the Clips table;
- the green clip marks on the timeline;
- **Split at selected clip**;
- **Download selected clips** (the cut now covers the clip itself and not the part after it);
- the clip **chapters** inside the downloaded file;
- the **Premiere Pro markers** (`.markers.xml`): In is now at the start of the clip and Out at its end.
- Example: a 60 s clip that ends at 0:22:15 now starts at 0:21:15 (before, it was shown at 0:22:15).

### Good to know
- If you already downloaded parts with clip chapters or Premiere markers, download them again to get the corrected positions. Old `.markers.xml` files are wrong by the length of each clip.
- Markers can still be 1–2 seconds off in Premiere. When a part is cut without re-encoding, it starts at the nearest keyframe and not at the exact second you typed. This is a separate, small difference and is not changed in this version.

## v1.5.0

### Added
- **Timeline** at the top of the Plan tab: the whole VOD on one strip, so you can see where the streamer changed game and place your cuts with the mouse. It shows:
- one coloured bar per game (the same game always has the same colour);
- preview thumbnails of the VOD, loaded in the background;
- green marks for the clips;
- the parts you will download, with skipped sections left dark.
- **Editing on the timeline:**
- click the thumbnails to cut there (cuts snap to game changes and clips);
- drag a cut line to move it, right-click it to remove it;
- click a part to skip it, click a skipped section to bring it back;
- double-click a game bar to make it its own part (Shift + double-click: keep only that game).
- **Zoom and move:** mouse wheel to zoom, Shift + wheel or the scroll bar to move, **Fit** to see the whole VOD again, **Undo** (or Ctrl+Z) to take back the last edit. Hover anywhere to see the time, the game and a bigger thumbnail.
- The **Cut points** text box still works and stays in sync: type there and the timeline follows, edit the timeline and the text changes.

### Fixed
- **Split at selected clip** used twice on the same clip no longer writes an empty range like `0:59:57 - 0:59:57`. The second split now does nothing.

### Good to know
- Thumbnails are a few minutes apart on long VODs (every 5 seconds on a 15-minute one), so use them to find the place and type the exact time when you need precision.
- Without Pillow, or if Twitch has no thumbnails for a VOD, the timeline works without pictures. VODs without game information show no game bars.
- On macOS, right-click means two-finger click or Ctrl + click.

## v1.4.2

No visible changes in this version. The app looks and behaves exactly as in v1.4.1. This release reorganizes the code and adds automated tests, to make future updates safer.

### Under the hood
- The Plan tab code now lives in its own module (`ui/plan_tab.py`), with shared colours and fonts in `ui/common.py`.
- Added an automated test suite (203 tests) covering the download engine and the Plan tab.

### Known issue
- **Split at selected clip**, used twice on the same clip, writes an empty range (for example `0:59:57 - 0:59:57`) into the cut text, which the planner then rejects. Not fixed yet.

## v1.4.1

### Fixed
- **Open folder opened the Documents folder on Windows** instead of showing the downloaded file. It now opens the right folder with the file highlighted, also when the name has spaces.

### Changed
- **Search tab:** a little space between each VOD thumbnail and its title.

## v1.4.0

### Added
- **Search tab.** Find a VOD without leaving the app or copying links from Twitch:
- Type a streamer name and press Enter. An exact channel name opens right away; otherwise pick one from the results (● marks channels that are live).
- See their VODs with thumbnails, title, date, length and views. Switch between **Past broadcasts**, **Highlights** and **Uploads**, and press **Load more** for older ones.
- Double-click a VOD (or press **Use this VOD**) to load it in the Plan tab, ready for cut points.
- **Recent streamers**: the channels you open are remembered for next time (**Clear recent** empties the list).
- Searching needs the Twitch sign-in. When you are not signed in, the tab shows a warning with a **Sign in…** button.
- **Scrolling.** Every tab now has a scrollbar (and mouse-wheel support) when the window is too short to show everything, so no option is hidden any more. The minimum window height is lower too.

### Notes
- Thumbnails are cached in the app's data folder (`cache/thumbs`), so repeat searches load fast.
- Running from source now also needs Pillow: `pip install requests pillow` (it is in `requirements.txt`). The packaged apps include it.
- Twitch deletes VODs after a while and some streamers do not save them, so older broadcasts may not appear.

## v1.3.0

### Added
- **Open folder buttons.** Jump straight to your downloads without hunting for them:
- **Queue & log** tab: **Open folder** opens the folder of the selected queue item and highlights its first file in Explorer / Finder. With nothing selected it uses the last finished item, or the output folder if nothing has finished yet.
- **Options** tab: **Open folder** next to **Browse…** opens the output folder (it is created if it doesn't exist yet).

### Notes
- Works on Windows, macOS and Linux (Explorer, Finder, `xdg-open`).

## v1.2.1

### Changed
- **Premiere Pro markers now span the whole clip.** In the exported `.markers.xml`, each marker starts where the clip starts (including the lead-in) and ends where the clip ends (including the tail), instead of being a single point. If clips overlap and were merged into one chapter, the marker covers all of them.

### Notes
- Re-run the download of a part to get the new XML (the file is written when the part finishes).

## v1.2

### New
- **Export clips to Premiere Pro.** New option (Options > Chapter details > *Also export the clips as markers for Premiere Pro*) saves a `.markers.xml` next to each part, with one marker per clip. In Premiere: File > Import the XML, then drop the part's video into the new sequence at 0:00.
- Marker names follow your chapter title template, and the comment holds the creator, views and clip link.
- It works independently of "Add clips as chapters", so you can embed chapters, export the XML, or both. It uses the same clip filters and needs the Twitch sign-in, like chapters.
- Frame rate and resolution are read from the video with ffprobe (59.94 and 29.97 included).

### Notes
- The window is slightly taller by default (1020x910) to fit the new option.

## v1.1

### New
- **Download only a clip.** The new **Download only selected clip** button (Plan tab, under the clips table) adds the selected clip(s) straight to the queue. Only that stretch of the VOD is downloaded, and the file is named after the clip instead of the stream.
- **Multi-select in the clips table.** Select several clips (Ctrl/Shift) and each one is queued as its own download. *Split at selected clip* still works with a single clip.
- **Single clip options** (Options tab → *Single clip downloads*):
- File name template with the tokens `{clip_title} {creator} {views} {clip_id} {clip_duration}`, plus `{streamer} {date} {id} {title} {start} {end}`.
- Extra seconds added before and after the clip (3 s each by default).

### Fixed
- **Download progress.** When downloading only the parts, the progress bar and status stayed at 0% until the end and then jumped to 100%. The status bar now shows the real percentage, size, speed and ETA. If the downloader reports nothing, it falls back to the size written to disk.
- The log now shows progress every 10% of a download.
- Removed the duplicated percentage in the status bar.

### Notes
- The window is slightly taller by default (1020×880) to fit the new options.

## v1.0

Download Twitch VODs (or any yt-dlp supported link) and cut them into parts by timestamps, with optional Twitch clip chapters.

## Features

- **Cut by timestamps:** `0:00 - 30:00 - 1:30:00 - end` makes consecutive parts. Use `;` or a new line to skip gaps: `0:00 - 30:00 ; 2:00:00 - end`.
- **Smart download strategy:** downloads the full VOD and splits it, or downloads only the parts you asked for, whichever is cheaper (or force one).
- **Exact cuts** option, custom file/folder name templates, and the choice to keep the full VOD.
- **Clip chapters (optional):** build chapters from a VOD's Twitch clips, filtered by views, duration or top N (needs Twitch API credentials).
- **Progress and cancel:** live progress with speed, and cancelling stops everything and keeps the partial download so it can resume.
- **Zero setup:** yt-dlp and ffmpeg are downloaded automatically on first launch, and yt-dlp stays up to date.

## Downloads

- **Windows:** `LuckyTwitch-Setup.exe` (installs for your user, no admin rights needed).
- **macOS:** `LuckyTwitch-macos-arm64.dmg` for Apple Silicon (M1/M2/M3...), `LuckyTwitch-macos-x86_64.dmg` for Intel Macs.

## First launch

- **macOS:** the app is not notarized. Right-click it, choose **Open**, then **Open** again (once). If macOS says it is damaged, run `xattr -cr /Applications/LuckyTwitch.app`.
- **Windows:** SmartScreen may warn about an unknown publisher. Click **More info**, then **Run anyway**.
- Needs internet on first run to fetch yt-dlp and ffmpeg.

Settings and downloaded tools are stored in `%LOCALAPPDATA%\LuckyTwitch` (Windows) or `~/Library/Application Support/LuckyTwitch` (macOS). Downloads go to `Downloads/LuckyTwitch` by default.
