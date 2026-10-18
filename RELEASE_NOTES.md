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
