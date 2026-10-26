# HANDOFF: tkinter to PySide6 migration

**Living file.** The agent updates it at the end of every phase, in the same commit as the phase. A new session reads this file first, then PLAN.md (the full plan), then the Phase section it is about to do. If this file and the code disagree, say so to the user before doing anything.

Last updated: 2026-10-26 (Phase 4 done, waiting for approval). Last completed phase: 3 (approved by the user, tag `migration-phase-3`).

## 1. Status

| Phase | Name | State | Tag | PR |
| --- | --- | --- | --- | --- |
| 0 | Baseline and decisions | approved | migration-phase-0 | |
| 1 | Skeleton and plumbing | approved | migration-phase-1 | |
| 2 | Widget kit | approved | migration-phase-2 | |
| 3 | Queue and log tab | approved | migration-phase-3 | |
| 4 | Search tab and Twitch sign-in | done (waiting for approval; Windows tests clean, hands-on check open) | | |
| 5 | Options tab | not started | | |
| 6 | Plan tab (no timeline), Get info, links | not started | | |
| 7 | Timeline (7a to 7e) | not started | | |
| 8 | Packaging, CI, cutover | not started | | |
| 9 | Redesign beyond parity | optional, not started | | |

States: not started, in progress, done (waiting for approval), approved.

## 2. Decisions

Made by the user:
- **Main is frozen.** The 1.x app (last release v1.16.0) gets no updates until the PySide6 version is complete. So there is no port debt and no merging from main is needed. If a hotfix on main ever happens, record it here and merge main into `qt-migration`.
- **All migration work is committed directly on the branch `qt-migration`** (decided 2026-10-19). No branch and no pull request per phase; the agent never gives `git switch -c` or pull request steps unless the user asks for them for a risky phase. One commit per phase, then the tag `migration-phase-N`.
- **Versioning:** pre-releases `v0.x.y-alpha.N` / `-beta.N`, then `v2.0.0` at cutover (see RELEASE_NOTES_QT.md for which phase gets which tag).
- **First release `v0.0.1-alpha.1` is only a pipeline test** (it contains the unchanged tkinter app).

Confirmed by the user on 2026-10-19 (all as recommended in PLAN.md section 5):
- **D1** Python 3.12 (as CI) and PySide6 6.x, pinned to 6.12.0 in `requirements-qt.txt` (abi3 wheel for Python 3.10 and newer; installed and run in Phase 0).
- **D2** Timeline as a custom QWidget with QPainter (Viewport reused).
- **D3** A Bridge(QObject) with typed signals instead of the tagged queue, and a SettingsBinder instead of tk variables.
- **D4** QSS generated from the existing palette tokens, on the Fusion style.
- **D5** QAbstractTableModel and QTableView for the VOD list and the queue; QListView for the channel lists.
- **D6** Ship Qt alongside tkinter for at least one release before deleting tkinter.

Still open:
- **D7** What Phase 9 (redesign) should look like: the user provides references. Not needed before Phase 9.

Decided in Phase 1 (by the agent, not contested): `core/` modules read their file paths from `core.paths` when called, so tests monkeypatch `core.paths.SETTINGS_PATH` and friends. `_read_config`/`_write_config` became `read_config`/`write_config` in `core/config.py`. One `Bridge` signal per message kind, typed; "no value" is `""`. Qt tests run on the offscreen platform (`tests/conftest.py`). Palette tokens live in `core/palette.py`; `qt_ui/theme.py` generates the QSS from them. Phase 1 settings handling only reads: the SettingsBinder (Phase 5) and the save on close (Phase 3) do the writing.

Decided in Phase 3 (by the agent, not contested): the queue tab owns the queue (`QueueModel`), the worker (`QueueRunner`) and the log; the main window owns the progress bar, status line, `Job n/m` prefix and closing, and talks to the tab through signals and two hooks (`blocked_reason`, `output_dir`). Message boxes go through `qt_ui/dialogs.py` (tests replace those functions). The tests of closing and the data folder use the autouse fixture in `tests/conftest.py` (only for `test_qt_*.py`). See MIGRATION_LOG.md no. 4 to 7.

Where things are (decided in Phase 0): `PARITY.md`, `SETTINGS_KEYS.md`, `MIGRATION_LOG.md` and the `baseline/` folder are in `docs/migration/`, next to this file.

## 3. Rules for the agent (short version; PLAN.md section 1 is the full one)

- One phase per session. Stop at the end, report against the Definition of Done, wait for approval.
- Parity first. Layout and design changes only in Phase 9.
- Do not touch `luckytwitch_engine.py`, `weblink.py`, `premiere-plugin/`, `premiere-plugin-cep/`. Report bugs there, do not fix them.
- The tkinter app stays shippable until Phase 8: new code goes in new packages (`qt_ui/`, `core/`); old files change only where a phase says so.
- Qt widgets, QPixmap and dialogs only on the GUI thread; workers use signals.
- Settings JSON keys stay identical.
- Every deliberate difference goes in MIGRATION_LOG.md. Never improve behavior silently.
- The agent has no access to the repository and never runs git against it: it works on an uploaded zip and delivers a zip plus commands for the user to run (section 4).
- **Deliver in versions, not in one batch (decided by the user, 2026-10-26).** A phase can be delivered in semi-phases named `phase-N-<name>-v1`, `-v2`, and so on. Deliver a version as soon as there is something the user can run and look at, even if the phase is not done. Do not spend a session chasing errors that only show up in the Linux sandbox: run the full suite at the start of a session and at most once at the end, never in loops, and do not fight environment-dependent failures for more than a few minutes. Deliver what exists, say what was not run, list the exact checks for Windows, and let the user paste the logs; the next version fixes them one by one. Details: section 4, "Versions of a phase".
- **Hand over when going in circles, and let the user run the tests (decided by the user, 2026-10-26).** When the agent notices it is repeating fix-and-rerun cycles, or that the same kind of error keeps coming back, it stops, delivers what it has, and says what it was fixing and what it suspects. The agent writes the tests, but running them is the user's job on Windows: it delivers the test files and the exact commands, and the user pastes the results. In the sandbox the agent only does cheap checks (the files compile, one small test file of a few seconds, the baseline count at the start); it never runs the whole suite to "see what happens".

## 4. Branch, tags and releases

| What | Name | Triggers a release? |
| --- | --- | --- |
| Integration branch | `qt-migration` | No (CI builds it, nothing is published) |
| End of a phase | tag `migration-phase-N` | No (the workflow only reacts to tags starting with `v`) |
| Pre-release | tag `v0.x.y-alpha.N` or `-beta.N` | Yes: published as a pre-release, never as Latest; notes come from `docs/migration/RELEASE_NOTES_QT.md` |
| Cutover | tag `v2.0.0` | Yes: a normal release; notes come from `RELEASE_NOTES.md` |

Rules the workflow enforces for a tag: the first line of the notes file (`RELEASE_NOTES_QT.md` for tags containing a dash, `RELEASE_NOTES.md` otherwise) must be `## <the tag>`. The newest entry goes at the top.

### How work is delivered (the agent has no repository access)

- **Start of a session.** The user uploads a zip of the repository and pastes the session message. The zip is the source of truth for the code. If it disagrees with this file, tell the user before doing anything. The agent works on its own copy and never pushes, merges or tags. If the uploaded zip contains a `.git` folder, the agent does not read or modify it and never copies it into anything it delivers.
- **End of a session.** The agent delivers all four of these:
  1. `phase-N-<name>.zip`: ONLY the new and changed files, with paths relative to the repository root (including the updated HANDOFF.md and PHASE_NOTES.md). Not the whole repository. **The zip must never contain a `.git` folder** (extracting it over the repository would overwrite the user's Git history), nor `__pycache__`, `.pytest_cache`, build output or other generated files. Before delivering, the agent lists the zip's contents and checks that none of these are in it.
  2. Files to delete or rename, if any, as `git rm` / `git mv` commands.
  3. A block of ready-to-paste PowerShell commands (below) with the exact `git add` paths and the commit message.
  4. The checks the agent could not run in its own environment (real GUI, Windows or macOS behavior, the tkinter tests), written as commands for the user, with what output to paste back. A phase stays "done (waiting for approval)" until the user has run them.
- PLAN.md section 9 (the per-phase prompt) is superseded by the session message. Where PLAN.md says the agent tags or opens a pull request, the user does it with the commands below.

Commands the user runs at the end of a phase (the agent fills in the names, paths and message). The zips are in `$env:USERPROFILE\Downloads`; run from the repository folder:
```
$zip = "$env:USERPROFILE\Downloads\phase-N-name.zip"
git switch qt-migration
git pull
tar -tf $zip | Select-String -Pattern '(^|/)\.git(/|$)'   # must print NOTHING; if it prints anything, stop and do not extract
Expand-Archive -Path $zip -DestinationPath . -Force
git rm <files the agent lists>          # only if there are any
git add <exact paths the agent lists>   # not "git add -A": it would pick up stray files
git status
git commit -m "<message from the agent>"
git push origin qt-migration
git tag migration-phase-N
git push origin migration-phase-N
```
Check that `git status` shows the branch `qt-migration` and only the expected files before committing.
Pre-release tags (`v0.x.y-alpha.N`) follow the table above: the agent also provides the finished entry for RELEASE_NOTES_QT.md (newest at the top, first line `## <tag>`) and the tag commands.

Making the zip to upload at the start of a session (run it from the repository, on `qt-migration`, after `git pull`; it contains only tracked files, so no `__pycache__` or `.pytest_cache`):
```
git archive --format=zip -o ..\lt-repo.zip HEAD
```

### Versions of a phase (semi-phases)

The user can ask for, and the agent can offer, a delivery before a phase is finished. Rules:
- **Name:** `phase-N-<name>-v1.zip`, then `-v2`, and so on. Same format as a full delivery (only new and changed files, no `.git`, no caches; list the zip contents before sending), same PowerShell block with exact `git add` paths. The commit message says `Phase N (version K): ...`.
- **No tag** for a version. The tag `migration-phase-N` is made only when the whole phase is approved. The status table says `in progress (version K delivered)`.
- **Docs in every version:** HANDOFF.md (status row, Last updated, Next step) and a PHASE_NOTES.md entry marked `IN PROGRESS: version K` that says what is built, what was run, what was NOT run, the known problems and the Windows checks. PARITY.md ticks only for behaviours that have a passing test. MIGRATION_LOG.md entries as usual.
- **What the agent runs:** the full suite once at the start (to confirm the baseline number), targeted test files while working, at most one full run at the end. It never loops on full runs. If something fails only in the full run or only on Linux, it reports it with the log and the likely cause instead of continuing for a long time.
- **Stop signs (hand over, do not continue):** the third fix-and-rerun round on the same problem; errors that differ from run to run or between orders of tests; a full run that takes more than a couple of minutes; a failure that only the Linux sandbox shows. Then the agent writes down the symptom, what it tried and the suspected cause in PHASE_NOTES.md and delivers.
- **Tests are written by the agent and run by the user:** every version ships its new and changed test files, and the Windows checks list the test files in the order to run them. The agent says which of them it did not run at all.
- **The user's checks:** commands to run on Windows one at a time (the new test files first, then the touched ones, the full suite last), what to paste back, and what to look at by eye.
- **Next session:** starts from the user's pasted logs and the uploaded zip, fixes one problem at a time, and delivers `-v2`.

## 5. Warnings

- **Installer collision.** The Windows installer for every build uses the same app id and install folder as the stable app, and the data folder (settings, Twitch login, tools) is shared. A pre-release installed over a real install replaces it. Before the first Qt installer is published (Phase 8, or earlier if a Qt pre-release is installable) give the Qt build its own app id, install folder and data folder name, or keep testers off their main install.
- **The user runs Python 3.14 on Windows; CI and the agent's sandbox use 3.12.** PySide6 6.12.0 and the whole suite work on 3.14 (Windows run of Phase 1: 837 passed, 31 skipped, 2 failed, the two failures being old tkinter tests, fixed in the follow-up below). 31 tests skip on Windows because their fake CLI is a shebang script (`test_chat_overlay.py`, `test_chat_and_game_markers.py`); that is old and expected.
- **Two tkinter tests were environment-sensitive (fixed in the Phase 1 follow-up, tests only, no app code).** `test_gui_search_tab.py::test_the_streamer_lists_keep_working_as_before` compared `str(tree.cget("show"))` with `""`; Tk 3.14 returns an empty tuple, so the string was `"()"`. It now asserts "nothing shown". `test_gui_plan_redesign.py::test_the_footer_stays_visible_when_the_page_scrolls` used a withdrawn window, which Windows does not lay out (heights stay 1); it now maps the window fully transparent first. Both pass on Linux/xvfb; the Windows result is a user check (Phase 2 start).
- **Widget kit (Phase 2).** `qt_ui/widgets.py`; see PHASE_NOTES.md Phase 2 for the list. Rules for later phases: write `&&` for a literal ampersand in button, tab and label texts (Qt reads `&` as a shortcut mark); use `WrapLabel` for wrapped labels with a maximum width; call `ScrollPage.fix_tab_order()` after adding focusable widgets once the page is shown; `Toggle.clicked` is the user-only signal (the old `command`), `toggled` also fires for code. Check boxes, combo boxes and spin boxes are still not styled (first use: Phase 4 or 5), and the wheel-over-combo policy is a Phase 5 decision.
- **Taskbar identity.** `qt_ui/theme.py` uses the same Windows AppUserModelID (`LuckyTwitch.Downloader`) as the tkinter app, for parity. Give the Qt build its own with the installer app id (see Installer collision).
- **Queue & log tab (Phase 3).** `qt_ui/tabs/queue.py`, `queue_model.py`, `queue_runner.py`, `dialogs.py`; PHASE_NOTES.md Phase 3 has the list. Rules for later phases: put a job in the queue with `QueueTab.enqueue(job, label, n_parts, strategy)` (Phase 6 calls it from «Add to queue» / «Add & start»); a worker never touches a widget, it emits a Bridge signal; the tools setup and the saved-chat overlay (Phase 5) set `MainWindow.tools_busy` / `saved_chat_busy` / `tools_ctx` and call `tab_queue.set_running()`; tests replace `qt_ui.queue_runner.run_job` and the functions of `qt_ui/dialogs.py`. `MainWindow.closeEvent` saves `self.settings` (only when not empty) and removes `BEAT_PATH`: tests that close a window must run with the temp paths of `tests/conftest.py` (automatic in `test_qt_*.py`). `tools/queue_demo.py` shows the tab with fake jobs or one real job.
- **Duplicated helpers.** `core/` copies the UI-free helpers from `luckytwitch_downloader.py` (they cannot be imported from there because that module imports tkinter, and the existing tests monkeypatch those names on it). Phase 3 added `core/files.py` (`open_in_file_manager`) to the copies. Main is frozen, so the copies will not drift; remove the duplication at cutover. `tests/test_core_matches_tkinter.py` compares the copies with the originals (remove it at cutover too).
- **Two timeline tests** that used to fail: re-checked in Phase 0, they pass (they already compare with `pytest.approx(600.4)`). No fix and no xfail were needed. Nothing to do.
- **`progress-eta.patch`** in the repository root is stale: the engine already contains `FfmpegProgress` and its tests, and the patch no longer applies. Safe to delete (`git rm progress-eta.patch`); the user decides.
- **Line endings.** `luckytwitch_engine.py`, `tests/test_hls_sections.py` and some other files in the zip use CRLF; the docs and most other files use LF. Keep each file's existing style when editing. Delivered new files use LF.
- **PySide6 package size.** `pip install PySide6` also installs the Addons and WebEngine packages. The app will probably need only `PySide6-Essentials`; decide in Phase 8 together with the bundle-size limit. `requirements-qt.txt` uses `PySide6` for now.
- **Screenshots.** The baseline screenshots in `baseline/linux-xvfb/` come from Linux under xvfb (other fonts, no title bar, sample data). Real Windows screenshots are a user check (section 7).
- **No tkinter in the agent's sandbox by default.** It can be installed (`apt-get install -y python3-tk`) and the whole suite then runs under `xvfb-run -a`. Do that at the start of each session to run the GUI tests.

## 6. State of the code when this was written (v1.16.0)

- `luckytwitch_downloader.py` 1,645 lines (App class, Search and Queue tabs, Twitch sign-in dialog, links, queue worker). `ui/`: `widgets.py` 560, `timeline.py` 726, `options_tab.py` 441, `plan_tab.py` 302, `theme.py` 251, `common.py` 72. Re-measured in Phase 0: the same.
- Engine `luckytwitch_engine.py` (about 145 KB) and `weblink.py` do not import tkinter.
- Tests: 798 in total, all passing (Phase 0 baseline, `baseline/TEST_BASELINE.md`). 235 need a real Tk and display: nine `tests/test_gui_*.py` files (232) and 3 in `tests/test_muted_audio.py`. (Earlier text said 197; that was out of date.)
- CI: `.github/workflows/build.yml` builds Windows, macOS arm64 and macOS Intel on Python 3.12, tests and packages the two Premiere plugins, and publishes a release for every tag `v*`.

## 7. Next step

Phase 4 is built and its tests are clean on Windows (Python 3.14, 2026-10-26: Search tab 70 passed, Twitch dialog 37, queue and main window 82, full suite 1108 passed, 31 skipped; no teardown errors). It waits for the user's hands-on check of the Search tab and the sign-in dialog (PHASE_NOTES.md, Phase 4) and approval. After approval the user tags `migration-phase-4`. Then the user says when to start Phase 5 (Options tab, PLAN.md section 6); do not start it before that.

## 8. Update checklist (end of every phase)

1. Status table: state, tag (the PR column stays empty: there are no pull requests).
2. "Last updated" line and "Last completed phase".
3. Decisions: move confirmed items from "to confirm" to "made".
4. Warnings: add anything new that the next session must know.
5. Next step: the exact first action of the next phase.
6. PHASE_NOTES.md: the new entry.