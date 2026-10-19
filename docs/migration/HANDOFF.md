# HANDOFF: tkinter to PySide6 migration

**Living file.** The agent updates it at the end of every phase, in the same commit as the phase. A new session reads this file first, then PLAN.md (the full plan), then the Phase section it is about to do. If this file and the code disagree, say so to the user before doing anything.

Last updated: 2026-10-19 (Phase 0 approved by the user). Last completed phase: 0.

## 1. Status

| Phase | Name | State | Tag | PR |
| --- | --- | --- | --- | --- |
| 0 | Baseline and decisions | approved | migration-phase-0 | |
| 1 | Skeleton and plumbing | not started | | |
| 2 | Widget kit | not started | | |
| 3 | Queue and log tab | not started | | |
| 4 | Search tab and Twitch sign-in | not started | | |
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

## 5. Warnings

- **Installer collision.** The Windows installer for every build uses the same app id and install folder as the stable app, and the data folder (settings, Twitch login, tools) is shared. A pre-release installed over a real install replaces it. Before the first Qt installer is published (Phase 8, or earlier if a Qt pre-release is installable) give the Qt build its own app id, install folder and data folder name, or keep testers off their main install.
- **Duplicated helpers.** `core/` copies the UI-free helpers from `luckytwitch_downloader.py` (they cannot be imported from there because that module imports tkinter, and the existing tests monkeypatch those names on it). Main is frozen, so the copies will not drift; remove the duplication at cutover.
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

Phase 0 is approved. The user approved it **without running the Windows checks** of the Phase 0 session (full pytest on Windows, `tools\hello_qt.py` with a real display, the Windows screenshots). So nothing says yet that PySide6 runs on the user's Windows machine. In Phase 1, ask the user to run `python -m pip install -r requirements-qt.txt` and `python tools\hello_qt.py --check` first, and paste the output. The optional Windows screenshots can still be taken at any time with:
```
python tools\baseline_screenshots.py docs\migration\baseline\windows
```
(keep the window visible and on top while it runs; it uses a temporary folder, not your settings or Twitch login).

Phase 1 (PLAN.md section 6): create `qt_ui/` and `luckytwitch_qt.py`, the theme module (palette tokens, generated QSS, per-platform fonts, icon from `assets/`), the main window (1020x910, minimum 900x560, top bar, info line, four empty tabs, progress bar and status line), `core/` with copies of the settings, recent, config, status and log helpers, and the Bridge with one signal per message kind in PLAN.md section 3.4. First action of that session: install `python3-tk` and `requirements-qt.txt`, run the full suite to confirm 798 pass, then read `PARITY.md` sections "Window, focus and tab order" and "Theme, icon and widgets".

## 8. Update checklist (end of every phase)

1. Status table: state, tag (the PR column stays empty: there are no pull requests).
2. "Last updated" line and "Last completed phase".
3. Decisions: move confirmed items from "to confirm" to "made".
4. Warnings: add anything new that the next session must know.
5. Next step: the exact first action of the next phase.
6. PHASE_NOTES.md: the new entry.
