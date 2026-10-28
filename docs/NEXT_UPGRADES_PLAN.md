# Next Upgrades Plan

Status: In progress (Phase H done in v2.3.1; Phase V Windows verified; Phase L done in v2.4.0; Phase E done in v2.5.0; Phase W done in v2.6.0; Phase P in progress)

This document plans the next round of work for **LuckyTwitch Downloader** (app, now at v2.3.0) and the **LuckyTwitch Markers** Premiere Pro CEP panel (now at v0.14.0). All items were discussed and approved by the owner. It is written to be executed one phase at a time; every phase ends green before the next starts.

Status of this plan: **In progress** (Phase H done in v2.3.1; Phase V pending).

---

## 1. Executive Summary & Principles

* **Order:** housekeeping, then verification on real hardware, then Linux, then the engine split, then the custom window bar, then the Premiere panel, then new app features.
* **Never break what works:** the Python suite (1,456 tests) and the CEP Node suite pass today. Every phase keeps both green (`python -m pytest tests -q`, and `npm test` in `premiere-plugin-cep/`).
* **One phase per session**, tagged, with release notes per phase (same method as the PySide6 migration).
* **Nothing is verified "by reading".** Anything that touches real Premiere, a real Mac or a real VOD gets a checklist the owner runs and a log the owner sends back.
* **Settings stay compatible.** New settings have defaults that keep today's behaviour; old `luckytwitch_settings.json` files keep working.

---

## 2. Findings (what the repo looks like today)

| Area | Finding | Consequence |
|---|---|---|
| Update detection | Shipped in v2.3.0 (`core/updates.py`, `qt_ui/update_dialog.py`, status-bar pill, Options card). `docs/UPDATE_DETECTION_PLAN.md` still reads as a plan. | Mark it Done. |
| Premiere panel | The UXP panel was retired; `premiere-plugin-cep/` (v0.14.0) is the only panel. Do it all, resume, running lock, pre-flight and progress bar exist. No "limit to chapter" mode and no named recipes in its README. | Panel work in section 7 continues from CEP, not UXP. |
| Leftover file | `progress-eta.patch` at the repo root. Its change (`FfmpegProgress`) is already in `luckytwitch_engine.py`. | Delete it. |
| CI | `build.yml` still triggers on `qt-migration`; tests run on Python 3.12 only. | Drop the branch; add Python 3.14 to the test run. |
| Engine size | `luckytwitch_engine.py` has about 3,700 lines and 170 top-level defs/classes, already divided by comment banners (time helpers, planning, Twitch API, clips, Premiere export, source info, muted stretches, tools, downloading, HLS sections, splitting, chat). | Natural module boundaries already exist. |
| Platforms | README: Windows and macOS only. `docs/LINUX_BUILD_PLAN.md` says the code is about 95% Linux-ready. | Linux is mostly packaging. |
| Unverified | Chat overlay opened in Premiere and its speed/size on a multi-hour VOD (README); MP3 chapters (`QUALITY_AND_AUDIO_PLAN.md` section 6); `install-mac.command` on a real Mac (`DEVELOPMENT.md`); macOS "open the DMG" update flow. | Phase V. |

---

## 3. Phase H: Housekeeping release (v2.3.1)

Small, safe, no behaviour change in the app.

1. Delete `progress-eta.patch`.
2. `build.yml`: remove `qt-migration` from the push branches and its comment.
3. `build.yml` test step: run the Python tests on 3.12 **and** 3.14 (a small matrix for tests only; builds stay on 3.12). If a dependency has no 3.14 wheel yet, keep 3.14 as `continue-on-error` and say so in a comment.
4. Add a status line (`Status: Done in vX.Y.Z` or `Pending`) under the title of every plan in `docs/`.
5. Add `docs/README.md`: one line per document, with its status.
6. `RELEASE_NOTES.md`: new `## v2.3.1` section at the top (the workflow checks that the first line matches the tag).

Tests: none new. The existing suites must stay green; the CI matrix proves item 3.

Done when: CI is green on both Python versions and `docs/README.md` lists every file in `docs/`.

---

## 4. Phase V: Real-hardware verification (no features)

Output: `docs/VERIFICATION_CHECKLIST.md`, with the exact steps, what to look at and which log or screenshot to send back. The owner runs it; fixes found go into patch releases.

| # | Check | Where | What proves it |
|---|---|---|---|
| V1 | Chat overlay `.mov` (Animation) imports and plays in Premiere, with transparency | Windows + Premiere | Screenshot of the overlay over video |
| V2 | Overlay on a multi-hour VOD: time to draw, file size, memory | Windows | Log + file size per hour, compared with the README table |
| V3 | MP3 audio-only keeps chapters (ID3 `CHAP`) | Windows, any player that shows chapters | ffprobe output |
| V4 | `install-mac.command` installs the CEP panel and Premiere shows it | Real Mac | Screenshot + log |
| V5 | macOS update flow: pill, dialog, **Update now** opens the right DMG for the CPU | Real Mac | Screenshot |
| V6 | Windows silent update from the previous version keeps settings and tools | Windows | Before/after settings check |

If no Mac is available, V4 and V5 stay open and are listed as such in the README ("not verified on macOS").

---

## 5. Phase L: Linux AppImage (v2.4.0) — Done

Follows `docs/LINUX_BUILD_PLAN.md` (desktop entry, `build_linux.sh`, CI leg, AppImage plus tarball). Changes to that plan:

* **Open decision:** x86_64 only, or arm64 too. Proposal: ship **x86_64 first**; add arm64 in a later patch once the first AppImage is verified.
* The update dialog on Linux opens the release page (no self-replace), like the source-run case.
* README: add the Linux row to the download table and a short "first launch on Linux" note (`chmod +x`, FUSE on newer Ubuntu).
* Release job: add `release/*.AppImage` and `release/*.tar.gz` to the uploaded files and to `SHA256SUMS.txt`.

Tests: `tests/test_qt_packaging.py` gets cases for the `.desktop` file (valid keys, `MimeType` for `luckytwitch://`) and for the asset-name contract used by the updater.

Risk: the Nuitka standalone build on Ubuntu can miss Qt plugins. Mitigation: smoke test in CI (`--version` or a headless start with `QT_QPA_PLATFORM=offscreen`) before uploading.

---

## 6. Phase E: Split `luckytwitch_engine.py` (internal; ships as v2.5.0) — Done

**No behaviour change.** Goal: smaller modules in `core/`, each with its own tests, so later features are cheaper and safer.

### 6.1 Proposed map (confirmed in E0)

| New module | Takes (from the engine's banners) |
|---|---|
| `core/timeutil.py` | Time helpers |
| `core/planning.py` | Planning: cut points, parts, strategy |
| `core/twitch_api.py` | Twitch API, Device Code sign-in |
| `core/vod_search.py` | Streamers and VOD search |
| `core/chapters.py` | Clips to chapters |
| `core/premiere_export.py` | Premiere XML and `.markers.json` export |
| `core/source_info.py` | yt-dlp source info |
| `core/muted.py` | Muted stretches |
| `core/job.py` | Job description |
| `core/runtime.py` | Ctx: logging, progress, cancel, subprocess handling |
| `core/tools.py` | yt-dlp, ffmpeg, TwitchDownloaderCLI download/update |
| `core/download.py` | Downloading, HLS sections, MP4 timescale |
| `core/finalize.py` | Splitting and finalizing |
| `core/chat.py` | Chat download and overlay |

`core/timeline.py` already exists; the "Editing the parts from the timeline" banner is merged there or kept next to it (decision in E0).

### 6.2 Phases

* **E0, map and safety net:** list every public name per banner, who imports it (app, tests, tools), and write `docs/ENGINE_SPLIT_MAP.md`. Add a test that records the engine's public names, so nothing disappears silently.
* **E1 to En, one or two modules per phase**, lowest-risk first (time helpers, planning, muted, premiere export), the download and runtime code last. Each phase: move code, keep `luckytwitch_engine.py` re-exporting the same names, run both suites, tag `engine-split-phase-N`.
* **Final phase:** the engine file becomes a thin facade; release notes and the plan status are updated.

### 6.3 Risks

* **Monkeypatching in tests.** A test that patches `luckytwitch_engine.some_func` stops affecting code that now lives in another module, because the re-export is a different reference. Rule: tests patch **where the name is used**. E0 lists every such test up front.
* **Circular imports** between `runtime`, `tools` and `download`. Rule: dependencies only flow downward (time, planning, Twitch API, then runtime, then tools, then download, then chat).
* **Frozen builds (Nuitka).** Each phase checks that a build still starts (CI smoke test from phase L).

---

## 6A. Phase W: Custom window bar (ships as v2.6.0) — Done

Full plan: **[`NEW_WINDOW_BAR.md`](NEW_WINDOW_BAR.md)**. Summary here so this file stays the master roadmap.

**Goal:** replace the OS title bar of the main window with a bar drawn by the app (same theme, own minimize / maximize / close buttons), keeping the native behaviours: resize from the edges, shadow, Aero Snap, Snap Layouts on the maximize button, double-click maximize and the system menu. Optionally fold the command bar into the bar.

**Approach (to be confirmed by the W0 spike):** on Windows, keep the native window styles and answer `WM_NCCALCSIZE` / `WM_NCHITTEST` from `nativeEvent`; on Linux, a frameless window with `startSystemMove()` / `startSystemResize()` (experimental, opt-in); on macOS, Qt's expanded client area flags, only once a Mac is available. No new dependency, no change to `core/` behaviour, native frame stays available through a setting and `--native-frame`.

| Phase | What | Build |
|---|---|---|
| W0 | Spike on real Windows 10/11 (three options compared), decision recorded | none |
| W1 | Classic bar (OS bar replaced, command bar unchanged), Windows, behind a setting | pre-release |
| W2 | Maximized state, on-screen clamp of the saved position, DPI and multi-monitor, `--native-frame` | pre-release |
| W3 | Optional: command bar integrated into the bar | pre-release |
| W4 to W6 | Optional: Linux custom bar, macOS unified title bar, themed dialogs | later |

Tests: pure hit-test and geometry logic tested everywhere; Win32 glue tested on a Windows CI step; widget tests offscreen; a few existing tests adjusted on purpose (main window layout, icon catalog, contrast, welcome overlay).

Real-hardware test per phase: the Windows checklist in `NEW_WINDOW_BAR.md` section 10, run by the owner.

---

## 7. Phase P: Premiere panel next steps (v0.15.0 and later)

The editing logic is delicate and verified in real Premiere, so every item below keeps the rule: **plan, failsafe, confirm, verify after**, with the pure logic in `src/` plus Node tests and the mocks in `mock/`.

| Item | What | Notes |
|---|---|---|
| P1 | **Limit to chapter** | Choose one game/chapter and run markers, cuts and deletes only inside it, without deleting the rest first. The plan, failsafe and final check all use the chosen range. A separate run mode, off by default. |
| P2 | **Named recipes** | Save a settings set (padding, merge, ripple limit, what Do it all includes) under a name and pick it from a list. Replaces the single remembered set; the old values become the first recipe. |
| P3 | **Preferences from the downloader** | The app can write padding and ripple-limit defaults into `.markers.json` (new optional field, documented in `docs/markers-format.md`). The panel uses them as the starting values; the panel's own settings still win once changed. Old files without the field behave as today. |
| P4 | **Polish** | Whatever the owner finds in daily use after P1 to P3. Collected in a short list before the phase starts. |

Tests: new cases in `test/markers-core.test.js` and `test/guard.test.js`, new scenarios in the mocks (a chapter at the start, middle and end; a chapter with one clip), and a Python test that keeps `tests/fixtures/markers_sample.json` and the new field in sync.

Real-Premiere test per item: a copy of the project, run, send the log. Version bumps follow the panel's rule: manifest, `package.json` and the version shown in the panel move together.

---

## 8. Phase F: New app features (proposed order and versions)

Each feature is optional in the UI and has a switch where it could surprise someone.

### F1. Download history (v2.7.0)

* Records every finished job in a small JSON file in the data folder: VOD id, title, streamer, date, parts, folder, quality.
* Shown as a ✓ "Downloaded" badge on VOD cards and rows (Search tab and Plan strip), with the date; a **History** list to reopen the folder or load the VOD again.
* Setting to turn it off and a **Clear history** button. Stays local; nothing is sent anywhere.
* Tests: pure model in `core/history.py`; Qt tests for the badge and the list.

### F2. Streamer watch list (v2.7.0 or v2.8.0)

* Pin streamers; on start (and then at a throttle like the update check) look for VODs newer than the last one seen and show a toast and a badge on the Search tab. It **never downloads by itself**.
* Needs the Twitch sign-in already used by Search; silent on failure, like the update check.
* Tests: the "new since" logic with fixtures, throttling and failure rules.

### F3. Parallel queue jobs and bandwidth limit (v2.8.0)

* Setting "jobs at the same time" (default 1, so nothing changes), and an optional speed limit passed to yt-dlp (`--limit-rate`) and to the ffmpeg sections where possible.
* The queue model and runner already separate rows from the thread; the work is in making `Ctx` (logging, cancel, progress) per job and in disk-space and resume safety with several jobs.
* Risk: the same output folder used by two jobs; the planner must refuse colliding file names. Cancel must stop only its own job.

### F4. Spanish translation (v2.9.0)

* Move user-visible strings to a catalog (Qt `tr` / `.ts`, or a small dictionary layer if that is simpler to keep with Nuitka), with English as the source.
* Language picker in Options and a first-run default from the system language.
* Done as one phase per tab, last the engine's log messages. Tests check that every key exists in both languages and that placeholders match.
* Open decision: translate logs and errors too, or only the interface. Proposal: interface first; logs stay English (easier to search and report).

---

## 9. Release and Delivery Method

* Versions: **v2.3.1** (H), **v2.4.0** (L), **v2.5.0** (E), **v2.6.0** (W, window bar; pre-release builds first), then F1 to F4 as above. Panel versions go on their own line (**v0.15.0** onward) and are packaged by the same `plugin` job.
* Each session: one phase, tests green, release notes written, a delivery zip with **only the changed files**, then explicit `git add` paths, commit and push.
* Order can change if a bug in daily use jumps the queue; the plan is updated when that happens.

---

## 10. Open Decisions

1. Linux: x86_64 only first, arm64 later (proposed), or both from the start.
2. Python 3.14 in CI: must pass, or allowed to fail until all dependencies have wheels.
3. Engine split: merge the timeline banner into `core/timeline.py` or keep it separate.
4. Watch list: check at start only, or also every N hours while the app stays open.
5. Spanish: interface only (proposed) or logs and errors as well.
6. Is a real Mac available for V4 and V5, or do they stay "not verified"?
7. Window bar (Phase W): the open decisions are listed in `NEW_WINDOW_BAR.md` section 12 (Windows route after the spike, integrated command bar, default frame mode, Linux, dialogs, version slot).

---

## 11. Verification Checklist (per phase)

- [ ] `python -m pytest tests -q` is green (CI also green on the Python versions of the matrix).
- [ ] `npm test` and `npm run check` are green in `premiere-plugin-cep/` when the panel changed.
- [ ] Release notes section added; its first line matches the tag.
- [ ] README and `docs/README.md` match what shipped; the plan's status line is updated.
- [ ] Anything touching real Premiere, a real Mac or a real VOD has its log or screenshot from the owner.
- [ ] Old settings and old `.markers.json` files still load.
- [ ] When the window frame changed: the Windows checklist in `NEW_WINDOW_BAR.md` section 10 passes, and native mode (`--native-frame`) behaves as before.
