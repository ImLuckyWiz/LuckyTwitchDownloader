## v2.2.1

LuckyTwitch Downloader **v2.2.1** expands template tokens for both files and stream folders with broadcast date deconstruction, dominant game detection, duration tags, and resolution synonyms.

### What's new in 2.2.1:
- **Date Deconstruction Tokens:** Added `{stream_date}` (broadcast date), `{download_date}` (current download date), `{year}` (4-digit broadcast year), `{month}` (2-digit month), and `{day}` (2-digit day) to easily organize files and folders by air date.
- **Dominant Game / Category Tokens:** Added `{game}` and `{category}` tokens. For part files, it automatically detects the game with the longest duration during that specific part's time span; for stream folders, it detects the dominant game of the entire stream.
- **Duration Token:** Added `{duration}` token, formatting part lengths or total stream durations as standard tags (e.g. `01h30m00s`).
- **Quality & Resolution Tokens in Folders:** Added `{quality}` and `{resolution}` tokens to stream folder templates so different quality versions can be routed to separate subfolders.
- **Options Tab Token Chips & Previews:** Added clickable chips for all new tokens in **Options → Output** for both *File name* and *Stream folder name*, with live previews demonstrating real game segments and duration tags.

## v2.2.0

LuckyTwitch Downloader **v2.2.0** brings full stream quality selection, lossless audio-only extraction (.m4a / .mp3), real-time download size estimation, `{quality}` naming token support, and robust URL/input validation.

### What's new in 2.2.0:
- **Stream Quality Selector:** Choose any stream quality provided by Twitch (such as `1080p60 (Source)`, `720p60`, `480p`, etc.) or **Audio only** directly from the Plan tab's quality picker.
- **Real-Time Download Size Estimates:** The Plan tab preview now calculates and displays the estimated download size (e.g. `Quality: 720p60 · about 1.4 GB`) based on Twitch's declared stream bitrate.
- **Audio-Only Mode:** Extract and download audio directly without downloading the video stream. Audio can be saved as `.m4a` (lossless direct AAC stream copy with zero re-encoding) or converted to `.mp3` (192 kbps with ffmpeg for universal player compatibility). Chapters are preserved in both audio formats.
- **Default Quality & Audio Preferences:** Configure your preferred default quality and audio format in **Options → Output → Quality**. Each loaded VOD adopts your default quality automatically while remaining adjustable per VOD on the Plan tab.
- **`{quality}` File Name Token:** Added `{quality}` to the customizable file naming template chips in Options (e.g. `{streamer} - {date} - {id} - {quality} - part{n}`), making it easy to archive and distinguish different quality downloads of the same stream.
- **Intelligent URL & Drag-and-Drop Validation:** The app now validates pasted and dropped inputs before invoking yt-dlp. Accidental drags of multiline log text or invalid text now trigger a friendly warning instead of a yt-dlp crash dialog, and channel names are seamlessly redirected to the Search tab.

## v2.1.1

LuckyTwitch Downloader **v2.1.1** introduces intelligent title cleaning and manual title editing, smarter single-part file naming, and critical fixes for filename truncation and path previews.

### What's new in 2.1.1:
- **Clean Single-Part Naming:** File names now automatically omit ` - part1`, `_part1`, or `1of1` when a download only has a single part. MP4 video metadata title tags also write the clean title directly without adding redundant `(part 1/1)` tags.
- **Auto-Clean Stream Titles:** Automatically strips noisy Twitch chat bot commands (such as `!gsupps`, `!links`, `!clash`, `!merch`, `!discord`, `!drops`), promotional hashtags (`#ad`, `#sponsored`), and trailing delimiters left behind by streamers. Unicode emojis and pictographs are cleanly separated so words no longer merge together.
- **Auto-Clean Toggle Setting:** Added an **Auto-clean titles** toggle switch in **Options → Output**. Keep it enabled for clean file names, or switch it off anytime if you prefer raw Twitch stream titles verbatim.
- **Manual Title Editing in Plan Tab:** The stream title can now be edited directly from the **Plan tab** before queuing a download. Typing in the title field updates the loaded VOD strip, header info, and destination previews in real time. A **Reset** button allows restoring the original Twitch title in one click.
- **Fixed Filename Truncation on Titles with Periods:** Resolved a Python `pathlib.with_suffix()` bug where periods inside stream titles (e.g. `reactions. BIG ANNOUNCEMENT`) caused the downloader to treat the rest of the title as a file extension and discard it.
- **Fixed Destination Preview Extension:** Fixed a preview bug in the Options tab where container extensions were appended twice, causing `.mp4.mp4` in sample paths.

## v2.1.0

LuckyTwitch Downloader **v2.1.0** introduces a guided **First-Run Welcome & Quick Setup** experience alongside a comprehensive **60 FPS Motion System Upgrade** across the entire Qt 6 interface.

### What's new in 2.1:
- **First-Run Welcome & Quick Setup:** Guided full-bleed onboarding overlay for first launches. Choose your downloads folder, pick your preferred container format (`MP4` for universal video editor compatibility or `MKV` for crash resistance), and check your Twitch sign-in status in 5 seconds. Reopen anytime via the `F2` shortcut or `--welcome` CLI flag.
- **Dynamic Living Canvas:** Custom-painted ambient background with radial glow blending Twitch purple into emerald with an ongoing subtle breathing pulse loop.
- **60 FPS Motion System Core:** Rebuilt motion architecture featuring standardized duration tokens (`DURATION_MICRO`, `DURATION_FAST`, `DURATION_NORMAL`, `DURATION_ENTER`), `OutCubic` easing curves, and reusable motion helpers (`animate_opacity`, `animate_slide_and_fade`, `animate_value`, `animate_height`).
- **Tactile Micro-Interactions:** Modern spring-like knob stretch on toggle switches, subtle 1 px tactile depression padding on buttons, chips, and ghost controls, and smooth slide-and-fade tooltips.
- **Smooth Page & Shell Transitions:** Crossfade transitions between navigation tabs, animated reveal (0 → 48 px) and clear for the VOD strip, and animated onboarding card accordion on the Plan tab.
- **Dynamic Feedback & Visual Polish:** Indeterminate barberpole shimmer on downloading queue rows, breathing alpha pulse on red `LIVE` badges, smooth hover lifts on VOD cards, and smooth value tweening on progress meters.
- **Toast & Dialog Animations:** Slide-and-fade entries and dismissals for notification toasts with smooth vertical stack repositioning, plus animated accordion folds on dialog technical details.
- **Zero-Delay Accessibility Fallback:** Strict adherence to Windows `SPI_GETCLIENTAREAANIMATION` (reduced motion). When animations are disabled, all transitions resolve instantaneously without hanging timers.

## v2.0.0

LuckyTwitch Downloader now runs on **Qt 6 (PySide6)** with a completely reimagined, modern dark interface, crisp High-DPI vector iconography, and professional-grade workflow enhancements while preserving 100% backward compatibility with your settings, Twitch login, recent streamers, and Premiere Pro plugins.

### What's new in 2.0:
- **Reimagined Modern Dark Interface:** Designed from the ground up on Qt 6 with a full-height collapsible left navigation rail, unified command bar, quick VOD strip, and modern card layouts.
- **Custom Vector Iconography:** 33 bespoke vector icons rendered pin-sharp at any display resolution or High-DPI scaling factor.
- **Streamer Discovery & Rich VOD Views:** Instant streamer list with real Twitch profile avatars and bold red `LIVE` badges. Toggle between compact Table view and visual 16:9 Card Grid view with skeleton loading states, instant client-side title filter, and automatic infinite scrolling. Smart URL input automatically detects streamer handles and routes to Search.
- **Two-Column Responsive Plan Workspace:** Cut points and Clips view arrange side-by-side on wide screens. Interactive visual Part cards with game-colour stripes and smooth auto-looping marquee text for long titles. Instant strategy segmented control (`Auto`, `Full VOD + split`, `Only the parts`) and visual VOD coverage meter. Proportional view bars and one-click quick selection on clips.
- **Advanced Interactive Timeline:** Visual part pills with diagonal hatching for skipped sections, full-VOD overview minimap with draggable lens, interactive game legend chips with duration totals and isolate/highlight modes, green clip flags with hover metadata and auto-clustering, keyboard editing (`S` to split, `Delete`, arrow nudging, `Ctrl+Y` redo), non-blocking right-click context menu, and animated loading shimmer.
- **Rich Queue & Smart Collapsible Log Drawer:** Queue rows feature 16:9 storyboard thumbnails, bold titles, coloured status chips, in-row progress bars, and one-click `Open` buttons. Real-time summary header with grouped actions. Log drawer collapses to a 1-line colour-coded preview, auto-expands on errors, and adds severity filters (`All`, `Warnings`, `Errors`), log search, autoscroll pause, and log export. Thread-safe retry and live drag-and-drop / button reordering.
- **Searchable Options & Live Disk Space Preview:** Instant settings search filtering across all 7 sections with match counter and auto-expanding cards. Visual changed-from-default markers (`●`) with per-row Reset buttons and sidebar change count badges. Live output file path preview and real-time disk space gauge. Dedicated status rows for `yt-dlp` and `ffmpeg` with direct update actions.
- **Themed Modal Dialogs & Screen Reader Accessibility:** Replaced native OS message boxes with sleek dark themed dialogs featuring vector status icons, clean titles, user-friendly summaries, and expandable technical error folds with a one-click `Copy details` button. Full accessibility names and descriptions across all icon controls.
- **Seamless Upgrade from 1.x:** 100% drop-in replacement. Reads your existing `luckytwitch_settings.json`, `config.json`, and `tools/` folder. Backed by 731 automated Qt tests.

## v1.16.0

Draw the chat overlay from a chat file you already have. Nothing was removed and nothing works differently when you do not use it.

### Overlay from a saved chat
- **New button.** Options → Chat → **Draw the overlay from a saved chat** → *Choose chat file…*: pick a `name.chat.json` (saved earlier by this app or by TwitchDownloader) and the app draws `name.chat-overlay.mov` next to it, with the current overlay settings. Nothing is downloaded and neither the chat nor the video is touched. Before it starts you see what it will do: the streamer, the VOD, the stretch of the VOD the file covers, how many messages, the size, frame rate and type, and the name of the result. A file that is not a chat says why and nothing starts.
  - If `name.mp4` (or `.mkv`, `.mov`, `.ts`…) is next to the chat, the overlay takes its size and frame rate (unless you set them in Advanced).
  - If `name.markers.json` is next to it, the overlay is lined up to the fraction of a second, like a normal download. Without it, it is lined up to the whole second (up to 1 s ahead of the video if the part did not start on one). A `.markers.json` that belongs to another part is ignored.
  - It never overwrites an earlier overlay (a new one gets a number), and it runs in the background; **Cancel current** (Queue & log) stops it.
- **It needs internet** while it draws, to fetch emotes and badges from Twitch, BTTV, FFZ and 7TV (unless the chat was saved with the emotes embedded). A long chat can take from minutes to hours depending on the type.
- **Checked:** the real TwitchDownloaderCLI on a real chat file (offline, so without emotes) gave a 400 × 720, 30 fps overlay with an alpha channel, and the 0.4 s trim from a `.markers.json` was applied. **Not checked:** a full render with emotes and badges.
- **Tests:** 37 new tests (reading the chat file, finding the video and the `.markers.json`, the render itself, and the window), and every older test still passes.

## v1.15.0

The chat of each part as a video you can put over the footage in your editor. Nothing was removed and nothing works differently when you do not use it: the new option is off by default.

### Chat as a video (overlay)
- **New switch: Options → Chat → Chat as a video (overlay).** After each part is done, the app draws the chat of that stretch as a video next to it, called `name.chat-overlay.mov` (or `.mp4`). It works even if the stream had no chat on screen. In the editor, put it on the track above the video, at the start of the part, and place it where you want it. It is off by default.
- **How it is made.** With TwitchDownloaderCLI's `chatrender` (the same tool as the chat download). If the chat you save is a `.json`, that file is reused. If you save `.html` / `.txt`, or no chat at all, a temporary `.json` is downloaded and deleted when the overlay is finished.
- **Three types** (Options → Chat → Advanced → Overlay type). Sizes are for a very busy chat (3 messages a second, 400 × 1080), measured on a synthetic chat:
  - **Transparent · Animation, `.mov` (the default):** lossless, about **3.4 GB per hour**, about 7 times faster than real time in the test. Read by Premiere Pro and After Effects.
  - **Transparent · ProRes 4444, `.mov`:** the codec almost every editor knows, but about **28 GB per hour** and slower than real time. Use it if your editor does not read Animation.
  - **Black background · H.264, `.mp4`:** about **0.4 GB per hour**, not see-through. Set the clip's blend mode to **Screen** in the editor and the black disappears.
- **Advanced settings:** how it looks (outlined text with nothing behind it, or a dark semi-transparent panel), size (width × height; height 0 = the video's), text size, frame rate (like the video, 30 or 60) and smooth scrolling (redraws on every frame instead of 5 times a second; slower). Size and frame rate follow the real video by default.
- **Lined up with the part.** The overlay starts together with the part. The tool only trims in whole seconds, so the fractional part is corrected with ffmpeg (`-ss`); with the chat updating every 0.2 s, expect a tolerance of about 0.2 s. It can end up to a second after the part (ffmpeg's `-t` crashes the tool, so it is not used).
- **If it fails,** the video is still downloaded and the log says why. An unfinished overlay file is never left behind.

## v1.14.0

Links that open the app: any web page, document or program can now offer a link that opens LuckyTwitch Downloader with a VOD and its cut points already filled in. Nothing was removed and nothing works differently when you do not use it.

### Open a VOD from a link
- **New `luckytwitch://` links.** Clicking one opens the app (or brings the open window to the front; a second window never appears), goes to the **Plan** tab, fills in the VOD and the cut points, and presses **Get info** for you. For example: `luckytwitch://open?url=<VOD link>&cuts=0:20:00 to 3:30:00&label=My job` (values URL-encoded).
- **A link only fills in the form.** It never adds anything to the queue and never starts a download: you check the cut points and press the button. It cannot change settings, choose folders or file names, or run anything else.
- **Safe by design.** Only `http` and `https` addresses are accepted, never ones that point to your own computer or a private network, never with a user name or password, and every value is length-limited and stripped of control characters. A link the app cannot use shows a message saying why and changes nothing.
- **No mix-ups.** The VOD that was loaded is cleared first, so if the new one cannot be read, its cut points are never applied to the old one. If the app is still preparing yt-dlp and ffmpeg, or reading another VOD, the link waits and opens when it is free.
- **Windows:** the installer has a new option, ticked by default, that sets the links up for your user (no administrator rights). With the portable folder, or from source, press **Options → Tools → Links from web pages → Set up links**. The same card tells you when the links currently open another copy of the app and lets you take them over.
- **macOS:** the app bundle now declares the scheme, so links work once the app is in Applications. If a link does nothing, open the app once from Applications and try again.
- **For people who build pages:** the format is in `docs/link-format.md` (parameters, limits, what is refused, examples in HTML and JavaScript). Links have a version (`v=1`); parameters the app does not know are ignored, and a link made for a newer version asks the person to update.
- **How a second launch finds the open window:** it leaves the link as a small file in a `links` folder inside the data folder, which the open window checks twice a second. Nothing listens on the network.
- **Tests:** 48 new tests for the link format, the hand-off and the registration (with a stand-in for the Windows registry), and 17 more that drive the real window.

## v1.13.0

Muted audio (the parts Twitch silenced), feedback while «Get info» works, and a second Premiere Pro panel that does the whole edit in one button. Nothing was removed; the new option is off by default and the existing Premiere plugin is unchanged.

### Get info
- While «Get info» works the button reads **Loading...** (the dots move), the line under it says **Reading VOD info...**, and the bar at the bottom runs. Everything goes back when it finishes or fails. If a download is running, its progress bar is left alone.

### Muted audio
- «Get info» now also reads which stretches Twitch silenced (copyrighted audio) from the VOD's playlist. It is one extra small request; if it fails you simply see nothing.
- **Timeline:** a thin red line along the bottom of the game bars, a summary next to the zoom buttons (for example `25 stretches · 1:54:00 silenced by Twitch`), a note when you hover a muted stretch, and a **Show muted** switch to hide it. Cuts snap to the edges of muted stretches while it is on.
- **Parts list:** each part says how much of it is muted (`... · 0:09:00 muted`) and the line at the bottom adds up the total.
- **Premiere Pro:** new switch **Options → Premiere Pro → Muted audio**. With it (and the plugin `.markers.json` on) every `.markers.json` also lists the muted stretches of that part as `kind: "muted"` markers, in part time, cut at the part's edges. The file `version` is still 1, so the current plugin still opens these files and skips the markers it does not know; the plugin team can add the color later (see `docs/markers-format.md`).
- Single-clip downloads never get muted markers, like they never get the other extras.

### Premiere Pro: a second panel (CEP), the whole edit in one button
- **New panel: LuckyTwitch Markers (CEP)**, next to the existing UXP plugin, which is unchanged. Both read the same `.markers.json` and share the same planning code, so they plan exactly the same markers and cuts. Use the one you like, or install both. It lives in `premiere-plugin-cep/` and is on the release page as **`LuckyTwitch-Premiere-Plugin-CEP.zip`**.
- **Do it all.** One button, one confirm: it **adds the markers** to the video, **cuts** the timeline around every clip with the real razor (with the padding you choose, merging clips that are close), **deletes the gaps** with a ripple delete so the clips end up back to back, and **links video and audio** again. At the end it reads the whole result back from Premiere (pieces, audio in sync, no holes, length, links, markers) and only says *Done* if everything matches the plan. Measured on a real VOD plan (110 markers, 199 cuts, 100 deletes, 100 links): about 50 seconds.
- **Safe by design.** Before each step it reads the timeline again and refuses, saying why, if anything is off (other tracks in use, more than one clip on V1/A1, a trimmed or sped-up clip, drop-frame timecode, a markers file for another video, or a delete that would remove too much). After every chunk of work it checks the result, and the first failed check stops everything without retrying. **Stop** halts after the current chunk; pressing the button again **continues where it stopped**.
- **A panel that shows its plan.** Before you press anything it shows the markers file it found, what will happen (markers, cuts, deletes and links, with counts) and a rough time. While it runs there is a progress bar with one row per step, the time left, and a clear message at the end (done, stopped, cancelled or refused, with the reason). The log is there when you need it, with a **Copy log** button.
- **Single steps.** Markers only, cut only, delete only or link only, each with its own confirm and its own checks; a **Detailed check** that prints every safety check without touching anything; and **Remove the plan's markers**.
- **Settings:** keep N seconds before and after each clip, merge clips closer than N seconds, also cut at game changes, also add the markers, and the delete limits. They are remembered.
- **Install.** CEP panels are folders, not a single file like the `.ccx`: unzip and run `install.bat` (Windows) or `install-mac.command` (macOS), restart Premiere, and open **Window > Extensions > LuckyTwitch Markers**. The installer switches on Adobe's "allow unsigned panels" flag for you. See `premiere-plugin-cep/README.md`.
- **Which one?** The CEP panel needs a fresh sequence with the video alone on V1/A1 and does not make a backup copy (save the project first); in return it needs no empty tracks above and does everything in one go. The UXP plugin accepts any timeline, also one you already trimmed, and installs with a double-click. The comparison is in the CEP README.
- **Checked on:** Premiere Pro 26.5 on Windows. The macOS installer follows the same rules but has not been tried on a Mac yet.
- **Build:** the release workflow tests and packages the CEP panel in its own job (`plugin-cep`), and fails if its `markers-core.js` ever differs from the UXP plugin's.

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
