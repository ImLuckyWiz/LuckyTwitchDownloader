## v0.8.0-beta

**First complete PySide6 (Qt 6) release candidate.** All four tabs (**Search**, **Plan**, **Options**, and **Queue & log**), the interactive **Timeline** with storyboard thumbnails and muted-audio stretches, **Twitch sign-in**, **chat overlay rendering**, and **`luckytwitch://` links** now run on PySide6.

### Safe side-by-side beta install
- **Does not overwrite your stable 1.x install.** Because this tag is a pre-release (`v0.8.0-beta.1`), the Windows installer uses its own application ID (`LuckyTwitch (Beta)` in `%LOCALAPPDATA%\Programs\LuckyTwitch-Beta`), its own macOS bundle identifier (`com.luckytwitch.app.beta`), and its own data folder (`LuckyTwitch-beta`). Your existing 1.x installation, settings, and Twitch login stay untouched.
- Note: if you leave the installer's **Open luckytwitch:// links** box ticked, `luckytwitch://` links from the browser will open this beta build until you switch them back in **Options → Tools → Links from web pages**.

### What is included
- **Search tab & Twitch sign-in:** search streamers, browse recent channels, filter VODs with background thumbnail loading, and sign in with Twitch device-code login or your own client ID/secret.
- **Plan tab & interactive Timeline:** `QPainter` timeline strip with ruler, CRC32-coloured game bars, red muted-audio stretches (`Show muted`), storyboard thumbnails, floating hover preview, magnetic snapping (6 px) to game changes, clips, and muted stretches, double-click game isolation, mouse-wheel zoom anchored at the cursor, 100-step undo (`Undo` / `Ctrl+Z`), cut points editor with live plan preview, and `Clips → chapters` table.
- **Options tab:** all 7 sections (`Output`, `Cuts`, `Chapters`, `Premiere Pro`, `Chat`, `Clips`, `Tools`), live filename/folder examples with clickable token chips, saved-chat overlay rendering, and background tool setup.
- **Queue & log tab:** colour-coded job queue and log, indeterminate and determinate progress bar with `Job n/m` prefix, safe cancellation, and confirmation before closing while a job is running.

## v0.0.1-alpha.1

**Pipeline test. This is not the PySide6 app yet.** It is the current tkinter app (same code as v1.16.0) built from the `qt-migration` branch, published as a pre-release to check that the branch, the tag, the notes and the build all work. No PySide6 code exists yet.

### What to know
- **Do not install it over your normal LuckyTwitch.** The Windows installer uses the same install folder and the same app id as the stable one, and the app keeps its settings and Twitch login in the same data folder. If you want to try it, use a separate machine or a virtual machine.
- Nothing was removed or changed in the app itself.
- What is new is only in the repository: `docs/migration/` (the migration plan, the hand-off file and the phase notes) and the build workflow, which now publishes tags like `v0.0.1-alpha.1` as pre-releases that never become the Latest release.

### Version plan for the migration
- `v0.0.1-alpha.1`: this one (pipeline test, Phase 0).
- `v0.6.0-alpha.1`: after Phase 6, the first Qt build that can load a VOD, set cut points and queue a job.
- `v0.7.0-alpha.1`: after Phase 7 (the timeline).
- `v0.8.0-beta.1`: after Phase 8 (installers and packaging for PySide6).
- `v2.0.0`: the cutover; the Qt app replaces the tkinter app.

Phases 1 to 5 are not published; they only get a git tag (`migration-phase-N`).
