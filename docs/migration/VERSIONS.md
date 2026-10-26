# Versions

The user asked for **released versions while a phase is in progress, even half-made ones**. So every meaningful chunk of work ends in a numbered release: a zip of the whole repo (`lt-repo_phase<N>_v<K>.zip`) plus an entry below. An entry always says what is done, what is NOT done, and what was NOT run, so a half-made version is never mistaken for a finished one. A phase is only "done" when HANDOFF.md says so and the user approves it; versions are the steps on the way.

## Phase 5: Options tab

### v1  (2026-10-26)  code written, Qt tests NOT run

**Done (new or changed files):**
- `qt_ui/tabs/options.py`: the whole Options tab. Sidebar with the seven sections (one visible at a time, scroll back to the top on switch), cards and setting rows with the exact tkinter texts and tooltips, Advanced areas collapsed, switches, token chips, live «Example:» lines, «Stream folder name» greyed out while «Organize in subfolders» is off, Chat section with the overlay settings and the «Choose chat file…» button, Tools section (status text, update switch, «Update yt-dlp now», «Open tools folder», luckytwitch:// links).
- `qt_ui/binder.py`: `SettingsBinder` (decision D3): binds each control to a key of the settings dictionary; switches write booleans, everything else strings; loading a value never writes it back.
- `core/options.py`: `build_options()`, `build_filter()`, tolerant `num()` (copied from the tkinter app, no tkinter import).
- `core/examples.py`: the live example lines, computed with the engine's own `part_stem`, `stream_dir`, `_SafeDict`.
- `qt_ui/background_jobs.py`: the tools-setup thread and the saved-chat-overlay thread, reporting only through the Bridge.
- `qt_ui/main_window.py`: owns both jobs, `build_options()`, `render_saved_chat()` with the same dialogs as tkinter, «Cancel current» also stops an overlay, closing cancels it, `start_tools_setup()` (called after the window opens).
- `qt_ui/widgets.py` (+ `theme.py`): new `SpinBox`; `ComboBox`/`SpinBox` ignore the wheel without focus; darker fields on cards like tkinter. `qt_ui/dialogs.py`: folder and file pickers. `luckytwitch_qt.py`: starts the tools setup.
- `tests/test_qt_main_window.py`: «Options is empty» no longer true, the test now only checks Plan.
- `MIGRATION_LOG.md` entries 13 to 15.

**Checked here (no Qt available):** every file compiles; `core.options` and `core.examples` run and give the right defaults; a half-typed template (`{`, `{title`, `{0}`, `}{`, empty) never raises; all 33 Options settings are bound to a control (the other 5 of the 38 belong to the Plan tab).

**NOT done:** the golden test (Qt `build_options()` equals the tkinter `JobOptions`), the 37 Options tests ported to pytest-qt, PARITY.md ticks, `SETTINGS_KEYS.md` / `PHASE_NOTES.md` update, the hands-on check on Windows.

**NOT run:** the whole test suite. This session's sandbox had no network, so PySide6, pytest and pytest-qt could not be installed. The Qt code has never been executed. Expect small errors on the first run; run `python -m pytest tests -q -k qt` (Windows) and paste the output back.

### v2  (2026-10-26)  tests written, Qt tests run in the sandbox, Windows run pending

Only the changed files are in `phase-5-options-v2.zip` (no full repository zip this time, as the user asked).

**Done:**
- Fix for the warning of the v1 Windows run: a tools-setup (or overlay) thread that outlives its window no longer crashes on `emit` (`background_jobs._emit`). The `main()` test of `test_qt_main_window.py` no longer starts the real tools setup.
- The golden test (`tests/test_core_matches_tkinter.py`: 12 fixtures x 2 cut texts, real tkinter `build_options` / `build_filter` against `core.options`).
- `tests/test_core_options.py` (13) and `tests/test_qt_options_tab.py` (60 cases, ported from the 37 tkinter Options tests plus binder, signals, tools setup, overlay, wheel policy, tab order).
- PARITY.md (36 Options boxes + the wheel box ticked), SETTINGS_KEYS.md, PHASE_NOTES.md, HANDOFF.md.

**Checked here (Linux, PySide6 6.12.0, offscreen):** all changed files compile; `test_core_options.py` + `test_qt_options_tab.py` 73 passed; `test_qt_main_window.py` + `test_qt_queue_tab.py` 82 passed.

**NOT done:** the DoD table in PHASE_NOTES.md, the hands-on look at the Options tab on Windows, Phase 5 approval.

**NOT run:** the golden test (the sandbox has no tkinter), the full suite, anything on Windows. The PARITY ticks come from the Linux run; the Windows run confirms them.

### v3  (planned)
Whatever the Windows run of v2 shows, then the Definition of Done table.
