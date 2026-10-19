# HANDOFF: tkinter to PySide6 migration

**Living file.** The agent updates it at the end of every phase, in the same PR as the phase. A new session reads this file first, then PLAN.md (the full plan), then the Phase section it is about to do. If this file and the code disagree, say so to the user before doing anything.

Last updated: 2026-10-18 (before Phase 0). Last completed phase: none.

## 1. Status

| Phase | Name | State | Tag | PR |
| --- | --- | --- | --- | --- |
| 0 | Baseline and decisions | not started | | |
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
- **All migration work is on the branch `qt-migration`**, one short branch and one pull request per phase.
- **Versioning:** pre-releases `v0.x.y-alpha.N` / `-beta.N`, then `v2.0.0` at cutover (see RELEASE_NOTES_QT.md for which phase gets which tag).
- **First release `v0.0.1-alpha.1` is only a pipeline test** (it contains the unchanged tkinter app).

Still to confirm with the user (before Phase 1; ask, do not assume):
- D1 Python and PySide6 versions (proposal: Python 3.12 as in CI, current stable PySide6 6.x; check that a wheel exists for the Python in use).
- D2 Timeline as a custom QWidget with QPainter (proposal) or QGraphicsView.
- D3 A Bridge(QObject) with typed signals instead of the tagged queue, and a SettingsBinder instead of tk variables.
- D4 QSS styling from the existing palette tokens on the Fusion style.
- D5 QAbstractTableModel and QTableView for the VOD list and the queue.
- D6 Ship Qt alongside tkinter for at least one release before deleting tkinter.
- D7 What Phase 9 (redesign) should look like: the user provides references.

## 3. Rules for the agent (short version; PLAN.md section 1 is the full one)

- One phase per session. Stop at the end, report against the Definition of Done, wait for approval.
- Parity first. Layout and design changes only in Phase 9.
- Do not touch `luckytwitch_engine.py`, `weblink.py`, `premiere-plugin/`, `premiere-plugin-cep/`. Report bugs there, do not fix them.
- The tkinter app stays shippable until Phase 8: new code goes in new packages (`qt_ui/`, `core/`); old files change only where a phase says so.
- Qt widgets, QPixmap and dialogs only on the GUI thread; workers use signals.
- Settings JSON keys stay identical.
- Every deliberate difference goes in MIGRATION_LOG.md. Never improve behavior silently.

## 4. Branch, tags and releases

| What | Name | Triggers a release? |
| --- | --- | --- |
| Integration branch | `qt-migration` | No (CI builds it, nothing is published) |
| Phase branch | `qt/phase-N-<name>` | No; merged into `qt-migration` by pull request |
| End of a phase | tag `migration-phase-N` | No (the workflow only reacts to tags starting with `v`) |
| Pre-release | tag `v0.x.y-alpha.N` or `-beta.N` | Yes: published as a pre-release, never as Latest; notes come from `docs/migration/RELEASE_NOTES_QT.md` |
| Cutover | tag `v2.0.0` | Yes: a normal release; notes come from `RELEASE_NOTES.md` |

Rules the workflow enforces for a tag: the first line of the notes file (`RELEASE_NOTES_QT.md` for tags containing a dash, `RELEASE_NOTES.md` otherwise) must be `## <the tag>`. The newest entry goes at the top.

Start of a phase:
```
git switch qt-migration
git pull
git switch -c qt/phase-N-name
```
End of a phase: push the branch, open a pull request into `qt-migration` (not main), merge it, then:
```
git switch qt-migration
git pull
git tag migration-phase-N
git push origin migration-phase-N
```

## 5. Warnings

- **Installer collision.** The Windows installer for every build uses the same app id and install folder as the stable app, and the data folder (settings, Twitch login, tools) is shared. A pre-release installed over a real install replaces it. Before the first Qt installer is published (Phase 8, or earlier if a Qt pre-release is installable) give the Qt build its own app id, install folder and data folder name, or keep testers off their main install.
- **Duplicated helpers.** `core/` copies the UI-free helpers from `luckytwitch_downloader.py` (they cannot be imported from there because that module imports tkinter, and the existing tests monkeypatch those names on it). Main is frozen, so the copies will not drift; remove the duplication at cutover.
- **Two timeline tests** (`tests/test_gui_timeline.py`, split at a clip and refreshing the clips) were failing before the redesign work started: the test expects a clip mark at 600 but `clip_start()` returns 600.4. Re-check in Phase 0 and decide: fix or mark expected-fail with a reason.
- `progress-eta.patch` sits in the repository root; check in Phase 0 whether it is still relevant.

## 6. State of the code when this was written (v1.16.0)

- `luckytwitch_downloader.py` about 1,650 lines (App class, Search and Queue tabs, Twitch sign-in dialog, links, queue worker). `ui/`: `widgets.py` 560, `timeline.py` 726, `options_tab.py` 441, `plan_tab.py` 302, `theme.py` 251, `common.py` 72. These sizes are from a copy taken just before v1.16.0 was finished; re-measure in Phase 0.
- Engine `luckytwitch_engine.py` (about 145 KB) and `weblink.py` do not import tkinter.
- GUI tests: nine `tests/test_gui_*.py` files, 197 tests, which need a real Tk and display.
- CI: `.github/workflows/build.yml` builds Windows, macOS arm64 and macOS Intel on Python 3.12, tests and packages the two Premiere plugins, and publishes a release for every tag `v*`.

## 7. Next step

Phase 0 (see PLAN.md). First, ask the user to confirm D1 to D6 above. Nothing in Phase 0 changes the app.

## 8. Update checklist (end of every phase)

1. Status table: state, tag, PR.
2. "Last updated" line and "Last completed phase".
3. Decisions: move confirmed items from "to confirm" to "made".
4. Warnings: add anything new that the next session must know.
5. Next step: the exact first action of the next phase.
6. PHASE_NOTES.md: the new entry.
