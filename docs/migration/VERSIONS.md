## Phase 9: UI redesign beyond parity

### 9h v1  (2026-10-26)  Final Polish & Release Readiness: ThemedDialog with expandable technical details, vector icons, accessibility attributes, NavRail full-height restructure, smart streamer detection, and clean terminal shutdown

**Done (new or changed files):**
- `qt_ui/dialogs.py`: implemented `ThemedDialog` with title, user-friendly summary, vector status icons (`info`, `alert`, `check`, `x`), collapsible technical error details (`#dialogDetails`, monospace font), and one-click `Copy details` button with safe C++ lifetime timer handling; reimplemented `info`, `warning`, `error`, `ask_yes_no`, `ask_ok_cancel`.
- `qt_ui/theme.py`: added `QDialog#themedDialog`, `QPlainTextEdit#dialogDetails`, and `QPushButton[variant="destructive"]` styles.
- `qt_ui/shell.py`, `qt_ui/timeline.py`, `qt_ui/tabs/search.py`, `qt_ui/twitch_dialog.py`: added `setAccessibleName` and `setAccessibleDescription` across all icon-only buttons.
- `qt_ui/main_window.py`: full-height left navigation rail restructure; smart channel handle/URL detection routing to Search tab on Enter/Get Info; auto-focus search edit.
- `luckytwitch_qt.py`: clean terminal SIGINT handler, wakeup timer, and sys.excepthook override.
- `tests/test_qt_dialogs.py`: 5 comprehensive tests for themed dialogs and accessibility.
- Docs updated: `MIGRATION_LOG.md` (no. 28), `PHASE_NOTES.md`, `VERSIONS.md`, `HANDOFF.md`, `RELEASE_NOTES.md`.

**Checked here (Windows, Python 3.14.7, PySide6 6.12.0, offscreen):**
- `python -m pytest tests/test_qt_dialogs.py tests/test_qt_main_window.py tests/test_qt_search_tab.py tests/test_qt_twitch_dialog.py tests/test_qt_shell.py -q` -> **149 passed** in 16.54s.
- `python -m pytest tests/ -k "qt" -q` -> **731 passed** in 98.24s.

**NOT done:** none.

**NOT run:** live interactive window inspection on Windows (`python luckytwitch_qt.py`).

### 9g v2  (2026-10-26)  Search & Shell Polish: full-height left NavRail, auto-focused search entry, smart streamer name detection in top VOD bar, and real CDN avatars

**Done (new or changed files):**
- `qt_ui/main_window.py`:
  - Full-height left NavRail: restructured central widget layout (`root_lay = QHBoxLayout(central)`) so the navigation rail anchors the entire left height of the window, with the command bar, tab views, and status bar residing in the main pane on the right.
  - Smart streamer name detection: added `extract_channel_input(text)` to recognize streamer handles (`illojuan`, `@illojuan`) and channel URLs (`twitch.tv/illojuan`). Entering a name into the top VOD bar automatically transitions to Search, populates the query, and executes the search instead of invoking yt-dlp with an invalid URL.
  - Auto-focused search input: switching or opening the Search tab immediately sets focus and selects all text in `search_edit`.
- `qt_ui/search_models.py`: added `channel_avatar_colour`, `load_avatar` (48 px high-DPI square pixmap loader), `ChannelDelegate` (24 px circular avatars with real Twitch profile picture or initial letter fallback + `#eb0400` `LIVE` pill badge), `VodGridDelegate` (220x192 16:9 VOD cards with duration pill overlay, 2-line title, `date · views` subtitle, hover lift, and `BG3` skeleton tile), and rounded skeleton placeholder in `ThumbDelegate`.
- `qt_ui/tabs/search.py`: added `avatar_ready = Signal(str, str)` for thread-safe avatar delivery to GUI thread; fixed `client.get("users", {"id": batch})` parameter shape; decoupled avatar downloads from `sv_gen`; added avatar fetching for recent streamers (`refresh_recent()`) and upon sign-in; added `VodGridView` (`QListView` in `IconMode` sharing `VodModel` and `selectionModel` with `VodTable`), `vod_stack`, `list_mode_btn` / `grid_mode_btn` (`set_view_mode`), `vod_filter_edit` (`set_vod_filter`, `visible_vod_rows`), and infinite scroll (`_on_vod_scroll`).
- `qt_ui/twitch_dialog.py`: added `copy_code_btn` (`copy_code()`) next to `code_label` with clipboard copy and `Copied!` feedback.
- `tests/test_qt_search_tab.py` & `tests/test_qt_twitch_dialog.py`: added 5 new Phase 9g tests (**74 passed** in `test_qt_search_tab.py`, **38 passed** in `test_qt_twitch_dialog.py`).
- Docs updated: `MIGRATION_LOG.md` (no. 27), `PHASE_NOTES.md`, `VERSIONS.md`, `HANDOFF.md`.

**Checked here (Windows, Python 3.14.7, PySide6 6.12.0, offscreen):**
- `python -m pytest tests/test_qt_search_tab.py tests/test_qt_twitch_dialog.py -q` -> **112 passed** in 9.88s.

**NOT done:** Phase 9h (final polish, accessibility & DPI check, screenshots, release notes).

**NOT run:** live interactive window inspection on Windows (`python luckytwitch_qt.py`).

### 9f v1  (2026-10-26)  The Timeline: rounded part pills & hatched skipped sections, keyboard editing & Redo, overview minimap, game legend chips, clustered clip flags, icon toolbar & zoom readout, context menu, snap feedback, and loading shimmer

**Done (new or changed files):**
- `core/timeline.py`: added Phase 9f pure helpers `SNAP_GAME`, `SNAP_CLIP`, `SNAP_MUTED`, `SNAP_EDGE`, `build_snap_kinds`, `snap_target`, `cluster_marks`, `game_key`, `game_totals`, `gaps_of`, and `minimap_lens`.
- `qt_ui/timeline.py`:
  - E1 Visual Part Styling: rounded part pills (`PART_RADIUS = 6.0`, squared at viewport-clipped edges) with `1 px` hover lift (`ACCENT_HOVER`), and diagonal hatching (`Qt.BrushStyle.BDiagPattern`, recorded in `drawn_skipped_rects`) across skipped sections (`gaps_of`).
  - E2 Keyboard Editing & Redo: `S` (`cut_at_hover`), `Delete`/`Backspace` (`remove_selected_cut`), `Left`/`Right` arrow nudging (`1 s`, `Shift` `10 s`, `Alt` `1 s`, coalesced within `0.8 s`), `Home`/`End` jump, `+`/`-`/`0` zoom, and `Ctrl+Y`/`Ctrl+Shift+Z` (`redo()`, `_future` stack, `btn_redo`).
  - E3 Overview Minimap (`TimelineMinimap`): 12 px full-VOD overview strip shown when zoomed in, with game colours, parts, cut lines, and a draggable/clickable lens (`drawn_lens`).
  - E4 Interactive Game Legend (`_FlowLayout`, `_LegendChip`): wrapping row of game colour chips sorted by total duration (`game_totals`); click isolates that game (`Shift+click` keeps only that game); hover highlights that game on the strip.
  - E5 Clips as Flags & Clustered Counter: green clip flags (`drawn_flags`) with hover tooltips (`clip_details`: title, creator, views) and automatic count badge clustering (`cluster_marks` when `< 9 px` apart).
  - E6 Icon Toolbar & Zoom Readout: vector icons (`minus`, `plus`, `fit`, `undo`, `redo`) from `qt_ui/icons.py` and live `zoom_label` (`Showing H:MM:SS of H:MM:SS` / `Showing the whole VOD · H:MM:SS`).
  - E7 & E8 Context Menu & Snap Feedback: non-blocking right-click `QMenu` on empty timeline (`Cut here`, `Skip this part`/`Keep this section`, `Isolate this game`, `Undo`, `Redo`), and visual snap guide line + pill (`snaps to: Game change` / `Clip` / `Muted edge` / `VOD edge`).
  - E9 States: loading shimmer (`_draw_shimmer`, respecting `Motion.enabled()`), striped placeholder when no storyboard is available, and pill backdrop behind status text.
- `qt_ui/tabs/plan.py`: added `_push_clip_marks()` passing formatted clip tooltip details (`title · by creator · N views`) to `self.timeline.set_clip_marks(...)`.
- `tests/test_qt_timeline.py`: updated card-order helper for Phase 9e's nested `lower_layout` and added 7 new Phase 9f test functions covering E1–E9 (**69 passed** in `test_qt_timeline.py`).
- Docs updated: `MIGRATION_LOG.md` (no. 26), `PHASE_NOTES.md`, `VERSIONS.md`, `HANDOFF.md`.

**Checked here (Windows, Python 3.14.7, PySide6 6.12.0, offscreen):**
- `python -m pytest tests/test_qt_timeline.py -q` -> **69 passed** in 8.13s.
- `python -m pytest tests/test_qt_plan_tab.py -q` -> **64 passed**.

**NOT done:** Phases 9g (Search & Twitch sign-in) and 9h (final polish & docs).

**NOT run:** live interactive window inspection on Windows (`python luckytwitch_qt.py`).

### 9e v2  (2026-10-26)  Plan page polish: filter squishing fix (2x2 grid), 1100 px breakpoint, auto-looping MarqueeLabel, interactive column resizing & Duration header

**Done (new or changed files):**
- `qt_ui/widgets.py`: added `MarqueeLabel` with auto-looping marquee animation (1.5 s initial pause, smooth horizontal scroll at 35 px/s, 1.5 s end pause, loop reset; static clean elision when `Motion.enabled()` is False; auto-pauses when hidden or text fits to consume 0% CPU).
- `qt_ui/tabs/plan.py`:
  - Filter squishing fix: converted `Clips → chapters` filter inputs into a clean 2x2 `QGridLayout` (`Min views`, `Min duration (s)`, `Top N (0 = all)`, `Lead-in (s)`), dropping minimum width from 610 px to 220 px.
  - Breakpoint raised: updated `WIDE_BREAKPOINT = 1100` so 2-column mode only activates when there is ample width.
  - Category marquee: updated `PartCard` to use `MarqueeLabel` for the game category title (`self.game_lbl`).
  - Table enhancements: updated `CLIP_COLUMNS` heading from `"Dur"` to full `"Duration"`; enabled `QHeaderView.ResizeMode.Interactive` so users can manually drag column dividers; enabled horizontal scrollbar (`ScrollBarAsNeeded`); added cell tooltips in `ClipModel.data` on `ToolTipRole`.
- `tests/test_qt_plan_tab.py` & `tests/test_qt_widgets.py`: updated responsive layout test for the 1100 px breakpoint, added Duration header and cell tooltip tests, and added `test_marquee_label_measurement_and_static_elision` (169 Qt tests passing across Plan, Main Window, and Widgets).
- Docs updated: `MIGRATION_LOG.md` (no. 25 updated), `PHASE_NOTES.md`, `VERSIONS.md`, `HANDOFF.md`, and `PHASE_9E_PLAN_POLISH.md`.

**Checked here (Windows, Python 3.14.7, PySide6 6.12.0, offscreen):**
- `python -m pytest tests/test_qt_plan_tab.py tests/test_qt_main_window.py tests/test_qt_widgets.py -q` -> **169 passed** in 27.89s.

**NOT done:** Phases 9f (Timeline polish), 9g (Search & Twitch sign-in), and 9h (final polish & docs).

**NOT run:** live interactive window inspection on Windows (`python luckytwitch_qt.py`).

### 9d v1  (2026-10-26)  The Options page: settings search, changed-from-default markers & reset, live output preview card with disk space, and dedicated tool status rows

**Done (new or changed files):**
- `qt_ui/widgets.py`: added `changed_dot`, `reset_btn`, and `set_changed()` on `SettingRow`; added `set_badge()` on `SideNav` to display modified setting count badges per section.
- `qt_ui/tabs/options.py`: G1 settings search bar (`search_entry`) with live match counter (`match_counter`); G2 `refresh_changed_markers()` updating `changed_dot`, `reset_btn`, and `SideNav` section badges; G3 `save_preview_card` displaying full live path and drive free space (`shutil.disk_usage`); G5 dedicated `ytdlp_row` and `ffmpeg_row` status rows.
- `tests/test_qt_options_tab.py`: added 4 new Phase 9d tests (64 total) verifying settings search filtering, changed markers & reset button click, save preview card with disk space, and tool status parsing.
- Docs updated: `MIGRATION_LOG.md` (no. 24), `PHASE_NOTES.md`, `VERSIONS.md`, `HANDOFF.md`.

**Checked here (Windows, Python 3.14.7, PySide6 6.12.0, offscreen):**
- `python -m pytest tests/test_qt_options_tab.py -q` -> 64 passed in 10.20s.
- `python -m pytest tests/test_qt_widgets.py tests/test_qt_main_window.py tests/test_core_matches_tkinter.py -q` -> 136 passed in 28.19s.

**NOT done:** Phases 9e (Plan layout), 9f (Timeline), 9g (Search & Twitch sign-in), and 9h (final polish & docs).

**NOT run:** live interactive window inspection on Windows (`python luckytwitch_qt.py`).

### 9c v1 (includes 9a A5 icons)  (2026-10-26)  The Queue page: rich rows delegate, real-time header counters, collapsible log drawer with filters/search/export, retry & live reorder, plus A5 vector icon layer

**Done (new or changed files):**
- `qt_ui/icons.py` (new, from `phase-9a-icons-v1.zip`), `tests/test_qt_icons.py` (new, 144 tests), `tools/widget_gallery.py`: A5 vector `QPainterPath` icon layer on a 24x24 grid (`icon()`, `pixmap()`, `_VectorIconEngine`, HiDPI-aware caching) wired into `qt_ui/shell.py` (`NavRail`, `CommandBar`, `VodStrip`) and `qt_ui/tabs/queue.py`.
- `qt_ui/queue_model.py`: added `ITEM_ROLE` and `PROGRESS_ROLE`, `progress`/`progress_text`/`thumb` fields on `QueueItem`, `threading.RLock()` (`self._lock`), `set_progress`, `set_running_progress`, `set_thumbnail`, `move_row`, `move_item`, `retry_item`, `next_queued`, `counts`, and `header_summary` (`N done · N running · N waiting · N failed`).
- `qt_ui/queue_runner.py`: updated `QueueRunner.start(items, model=None)` to pull the next queued item dynamically from `model` in current row order under `model._lock` while tracking seen row IDs on the worker thread.
- `qt_ui/tabs/queue.py` & `qt_ui/dialogs.py`: F1 `QueueRowDelegate` (16:9 thumbnail preview, bold title + `n parts · strategy` subtitle, coloured status chip, in-row progress bar when running, inline `Open` button on finished rows); F2 `counter_label` + `queue_progress` + grouped primary (`Start queue`, `Cancel current`) vs secondary (`Retry`, `↑`, `↓`, `Remove selected`, `Clear finished`, `Open folder`) buttons; F3 `log_preview_label` + `log_drawer` (`Collapsible`, collapsed by default, auto-opens on `err`) + severity filter chips (`All`, `Warnings`, `Errors`) + `log_search_entry` + `autoscroll_btn` + `save_log_btn` (`dialogs.save_file`); F4 `retry_failed_or_selected`, `retry_item`, `move_selected`.
- `qt_ui/main_window.py`: passes the current VOD storyboard thumbnail (`_current_vod_thumb()`) into `tab_queue.enqueue` and updates queued items when storyboard frames finish loading (`_on_frames_for_strip`).
- `tests/test_qt_queue_tab.py`: added 5 Phase 9c tests (75 total in `test_qt_queue_tab.py`) covering `counter_label`, `QueueRowDelegate` painting & inline `Open` button click, `log_drawer` collapse & auto-open on error, severity filter chips/search/autoscroll/save log, and `retry_failed_or_selected` + live waiting-row reordering during `QueueRunner` execution.
- Docs updated: `MIGRATION_LOG.md` (no. 23), `PHASE_NOTES.md`, `VERSIONS.md`, `HANDOFF.md`.

**Checked here (Windows, Python 3.14.7, PySide6 6.12.0, offscreen):**
- `python -m pytest tests/test_qt_queue_tab.py -q` -> 75 passed in 5.63s.
- `python -m pytest tests/test_qt_icons.py -q` -> 144 passed in 6.51s.
- `python -m pytest tests -q` (full repository suite) -> **1526 passed, 31 skipped, 0 failed** in 286.91s.

**NOT done:** Phases 9d–9h (Options polish, Plan layout, Timeline, Search & Twitch sign-in, final polish).

**NOT run:** live interactive window inspection on Windows (`python luckytwitch_qt.py`).

### 9b v1 (includes 9a v2)  (2026-10-26)  QSS token refactor, motion & button hover spike (9a v2), and The Shell: NavRail, PageStack, CommandBar, VodStrip, Toasts, Activity Pill, Shortcuts, UI State, and Plan Onboarding (9b v1)

**Done (new or changed files):**
- `qt_ui/motion.py` (new): A6 central `Motion` controller (`FAST_MS = 120`, `NORMAL_MS = 180`, `SLIDE_MS = 150`, `OutCubic`, Windows `SPI_GETCLIENTAREAANIMATION` check, `Motion.set_enabled(False)` in `tests/conftest.py`), `animate_height`, `animate_width`, and `ButtonHoverAnimator` (9a button hover spike).
- `qt_ui/theme.py` & `qt_ui/widgets.py`: A1–A3 QSS template substitution with `DESIGN_TOKENS`, rounded surfaces (`8 px` cards, `6 px` buttons, `4 px` inputs/chips), `FIELD_BORDER` input borders, `ACCENT_TEXT` on group titles/login code, `ACCENT_DIM` with `3 px` left accent bar on selected rows, `1 px solid ACCENT_HOVER` keyboard focus rings, shell QSS rules, and smooth `Collapsible` height animation when `Motion.enabled()` is true.
- `qt_ui/toast.py` & `qt_ui/notify.py` (new): B5 & B6 non-modal bottom-right `ToastCard` / `ToastHost` (4 s auto-dismiss, hover pause, action button, `✕` close button) and `notify.info` / `notify.success` / `notify.warning` / `notify.system_notify` with `notify.calls` test seam.
- `qt_ui/shell.py` (new): B1 `NavRail` (56 px collapsed / 176 px expanded, loaded-VOD dot, queue count badge, Up/Down arrow stepping, `# ICON NEEDED: <name>` seams) + `PageStack` (`QTabWidget`-compatible shim); B2 & B4 `CommandBar` (inline `Paste`/`✕` button, `Get info` CTA, live `●`/`○` Twitch account status); B3 `VodStrip` (48 px loaded-VOD bar with 16:9 storyboard thumbnail, title, metadata, `Open on Twitch`, `Clear`, click-to-open-Plan); B8 `ShortcutsDialog` (`F1`).
- `qt_ui/main_window.py` & `qt_ui/tabs/plan.py`: wired the shell, B2 drag-and-drop and clipboard VOD detection toast, B7 3 px top-edge progress bar and clickable `activity_pill`, B8 global shortcuts (`Ctrl+L`, `Ctrl+1..4`, `Ctrl+,`, `Ctrl+Enter`, `Ctrl+Shift+Enter`, `F1`), B9 `luckytwitch_ui.json` load/save, and B10 3-step empty-state onboarding card on `PlanTab`.
- `tests/conftest.py` & `tests/test_qt_widgets.py`: isolated `UI_STATE_PATH` and disabled `Motion` by default in `conftest.py`; updated `test_a_card_is_a_bordered_surface` top-border probe from `(0, 0)` to `(150, 0)` for `8 px` rounded cards.
- `tests/test_qt_notify.py` (new, 6 tests) & `tests/test_qt_shell.py` (new, 16 tests): 22 new tests covering motion, button hover spike, collapsible animation, `ToastCard`/`ToastHost`/`notify`, `NavRail`, `PageStack`, `CommandBar`, `VodStrip`, account chip, drag-and-drop, clipboard VOD toast, `activity_pill`, keyboard shortcuts, `UIState` persistence, and the Plan onboarding card.
- Docs updated: `MIGRATION_LOG.md` (no. 21 and 22), `PHASE_NOTES.md`, `VERSIONS.md`, `HANDOFF.md`.

**Checked here (Windows, Python 3.14.7, PySide6 6.12.0, offscreen):**
- `python -m pytest tests/test_qt_theme.py tests/test_qt_widgets.py tests/test_qt_contrast.py -q` -> 109 passed in 5.39s.
- `python -m pytest tests/test_qt_main_window.py tests/test_qt_plan_tab.py -q` -> 71 passed in 15.98s.
- `python -m pytest tests/test_qt_notify.py tests/test_qt_shell.py tests/test_qt_search_tab.py tests/test_qt_options_tab.py tests/test_qt_queue_tab.py -q` -> 222 passed in 25.86s (after fixing `ToastCard` deletion check in `test_qt_notify.py`: 22 passed in 4.05s in `test_qt_notify.py` + `test_qt_shell.py`).

**NOT done:** A5 SVG icon paths (`qt_ui/icons.py`, reserved for Claude — `# ICON NEEDED: <name>` seams are in place); Phases 9c–9h.

**NOT run:** live interactive window inspection on Windows (`python luckytwitch_qt.py`), full test suite in one invocation.

### 9a v1  (2026-10-26)  Design foundation: tokens, WCAG contrast repair, UI-state manager, and screenshot baseline

**Done (new or changed files):**
- `qt_ui/tokens.py`: A1 spacing scale (4 to 32 px), corner radius scale (4, 6, 8, 999 px), typography scale (9 to 16 pt), and QSS template dictionary `DESIGN_TOKENS`.
- `core/palette.py` & `ui/common.py`: A4 WCAG AA contrast repair (`MUTED` `#a3a6ad` passing 4.5:1 on `BG3`, `ACCENT_TEXT` `#b380ff` passing 4.89:1 on `BG2`, `BORDER_STRONG` `#484b52` for crisp card boundaries).
- `tests/test_qt_contrast.py`: 6 WCAG 2.1 relative luminance and contrast ratio tests.
- `core/ui_state.py` & `core/paths.py`: B9 UI state manager (`load_ui_state`, `save_ui_state`, `UIState` dataclass) persisting window geometry and drawer states into `luckytwitch_ui.json` without modifying `luckytwitch_settings.json`.
- `tests/test_qt_ui_state.py`: 4 tests covering defaults, JSON round-trip, corruption recovery, and OS error resilience.
- `tools/qt_screenshots.py`: automated script capturing offscreen snapshots of all 4 tabs at 1020x910 and 900x560 into `docs/migration/phase9/baseline/`.
- Docs updated: `MIGRATION_LOG.md` (no. 20), `VERSIONS.md`, `PHASE_NOTES.md`, `HANDOFF.md`.

**Checked here (Windows, Python 3.14.7, PySide6 6.12.0, offscreen):**
- `python -m pytest tests/test_qt_contrast.py tests/test_qt_ui_state.py tests/test_qt_theme.py tests/test_core_helpers.py tests/test_core_matches_tkinter.py -q` -> 91 passed in 48.50s.
- `python tools/qt_screenshots.py` -> 8 baseline screenshots generated in `docs/migration/phase9/baseline/`.

**NOT done:** A5 icons (assigned to Claude), A6 button hover animation spike (assigned to Argon).

**NOT run:** live hands-on inspection of the new tokens on Windows.

# Versions

The user asked for **released versions while a phase is in progress, even half-made ones**. So every meaningful chunk of work ends in a numbered release: a zip of the whole repo (`lt-repo_phase<N>_v<K>.zip`) plus an entry below. An entry always says what is done, what is NOT done, and what was NOT run, so a half-made version is never mistaken for a finished one. A phase is only "done" when HANDOFF.md says so and the user approves it; versions are the steps on the way.

## Phase 9: Redesign beyond parity

### v0  (2026-10-26)  plan only, docs only, no code

**Done (new or changed files):**
- `docs/migration/PHASE_9_PLAN.md` (new): the full redesign plan (see PHASE_NOTES.md Phase 9).
- Docs updated: `HANDOFF.md` (status row, D7 changed, D8 to D15 added, next step), `PLAN.md` (Phase 9 pointer), `PHASE_NOTES.md` (Phase 9 planning entry), `VERSIONS.md` (this entry).

**NOT done:** any code, any decision (D8 to D15 are the user's), the baseline Qt screenshots (planned for 9a as `tools/qt_screenshots.py`).

**NOT run:** the test suite (nothing but documents changed).

## Phase 8: Packaging, CI and cutover

### v1  (2026-10-26)  PyInstaller & Inno Setup cutover, pre-release isolation, CI pytest, and release notes complete

**Done (new or changed files):**
- `build_windows.bat`, `build_mac.sh`, `requirements.txt`: cut over to `luckytwitch_qt.py`, added `PySide6==6.12.0` to `requirements.txt`, wrote `build/version.txt` into the frozen bundle, collected `core` and `qt_ui`, excluded `tkinter` and unused `PySide6.Qt*` modules (`QtWebEngine*`, `QtQml`, `QtQuick*`, `QtMultimedia*`, `Qt3D*`, `QtCharts`, `QtPdf*`, `QtSql`, `QtNetwork*`, `QtSvg*`, `QtOpenGL*`, `QtPrintSupport`, `QtDesigner`, `QtHelp`, `QtUiTools`, `QtXml`, `QtTest`, etc.), and kept macOS `CFBundleURLTypes` (`luckytwitch://`) registration before `codesign`.
- `installer.iss`, `core/paths.py`, `qt_ui/theme.py`, `luckytwitch_qt.py`: isolated pre-release builds (versions containing `-`, e.g. `v0.8.0-beta.1`) into their own Windows `AppId`, install folder (`LuckyTwitch-Beta`), macOS bundle ID (`com.luckytwitch.app.beta`), taskbar ID (`LuckyTwitch.Downloader.Beta`), and data folder (`LuckyTwitch-beta`), while preserving the standard `LuckyTwitch` identity and `user_data_dir()` for stable releases (`v2.0.0`) so 1.x users keep their settings, login, recent streamers, and tools.
- `.github/workflows/build.yml`: installed `requirements-qt.txt` and `pytest`, added `QT_QPA_PLATFORM: offscreen` test steps on Windows (Qt + engine + tkinter) and macOS (Qt + engine), and passed the tag/version to `build_mac.sh`.
- `docs/migration/RELEASE_NOTES_QT.md` & `RELEASE_NOTES.md`: added top entries `## v0.8.0-beta.1` and `## v2.0.0`.
- `tests/test_qt_packaging.py` (new, 14 test cases) & `tests/test_qt_theme.py` (`test_build_scripts_use_the_icon` added): tests for packaging scripts, icon paths, module exclusions, macOS URL scheme order, pre-release vs stable path/installer isolation, CI workflow, and release notes headers.
- `tools/measure_build.py`: helper script that measures source startup times (`luckytwitch_qt.py` median 975 ms vs `luckytwitch_downloader.py` median 1511 ms on Windows) and reports `dist/LuckyTwitch` and `dist/LuckyTwitch-Setup.exe` sizes once built.
- Docs updated: `HANDOFF.md`, `PHASE_NOTES.md`, `VERSIONS.md`, `PARITY.md` (`test_build_scripts_use_the_icon` ticked), `MIGRATION_LOG.md` (no. 19).

**Checked here (Windows, Python 3.14.7, PySide6 6.12.0, offscreen):**
- `python -m pytest tests/test_qt_packaging.py tests/test_qt_theme.py tests/test_core_helpers.py tests/test_core_matches_tkinter.py tests/test_gui_theme_and_icon.py -q` -> 110 passed in 22.73s.
- `python tools/measure_build.py` -> Qt source startup min 954 ms / median 975 ms vs tkinter min 1490 ms / median 1511 ms (~35% faster).

**NOT done:** running `build_windows.bat` to produce `dist/LuckyTwitch-Setup.exe` and measuring the final `.exe` installer size on Windows; pushing a tag to run the GitHub Actions CI matrix on Windows + macOS.

**NOT run:** `build_windows.bat` (takes several minutes and modifies `dist/`/`build/`), full test suite in one invocation.

## Phase 7: Timeline (7a to 7e)

### v1  (2026-10-26)  Full Timeline (7a to 7e) and tests complete, targeted Qt tests green on Windows

**Done (new or changed files):**
- `core/timeline.py`: pure geometry, colour, step, zone and snapping helpers (`Viewport`, `nice_step`, `game_colour`, `zone_at`, `y_of`, `build_snap_points`, `snap_time`).
- `qt_ui/timeline.py`: `Timeline(QWidget)` and `TimelineCanvas(QWidget)` custom-painted with `QPainter` covering 7b (static paint of ruler, games, muted stretches, thumbnails, parts, cut/edge handles, toolbar, scrollbar, wrapping hint), 7c (storyboard thumbnail strip, dimmed skipped sections, PIL -> `QPixmap` conversion, hover frame preview, no-Pillow fallback), 7d (mouse press/drag/double-click/right-click/wheel zoom & pan, snapping, `Undo` button + `Ctrl+Z`/`Cmd+Z`, `on_edit` callback), and 7e (hover overlay line, time badge, cursor shapes, muted audio red bars and switch).
- `qt_ui/tabs/plan.py`: wired the real `Timeline` into `PlanTab` (replacing `TimelinePlaceholder`) and skipped background frame loading when `PIL.Image` is unavailable.
- `tests/test_qt_timeline.py`: 58 test functions (62 test cases) porting all 57 cases of `tests/test_gui_timeline.py` and the timeline/muted-audio tests of `tests/test_muted_audio.py`.
- Docs updated: `HANDOFF.md`, `PHASE_NOTES.md`, `VERSIONS.md`, `PARITY.md` (all 57 `test_gui_timeline.py` boxes + 3 `test_muted_audio.py` boxes ticked), `MIGRATION_LOG.md` (no. 16 resolved, no. 18 added).

**Checked here (Windows, Python 3.14.7, PySide6 6.12.0, offscreen):** `python -m pytest tests/test_qt_timeline.py tests/test_qt_plan_tab.py -q` -> 121 passed in 19.90s.

**NOT done:** the user's hands-on check of the interactive Timeline on a real VOD on Windows.

**NOT run:** the full test suite (`python -m pytest tests -q`), interactive run of `python luckytwitch_qt.py`.

## Phase 6: Plan tab (no timeline), Get info, links

### v1  (2026-10-26)  Phase 6 code and tests complete, targeted Qt tests green on Windows

**Done (new or changed files):**
- `qt_ui/tabs/plan.py`: full `PlanTab(ScrollPage)`, `ClipModel(QAbstractTableModel)`, and `TimelinePlaceholder(QWidget)` (stand-in for the Phase 7 custom QPainter timeline strip).
- `qt_ui/background_jobs.py`: `InfoRunner` (`get_source_info` + `fetch_clips_for_vod`) and `FramesRunner` (`load_storyboard_frames`), reporting via `Bridge.info_ok`, `Bridge.error`, and `Bridge.frames`.
- `qt_ui/main_window.py`: wired `PlanTab`, `on_get_info` (with 350 ms dot animation and indeterminate progress), `on_info_ok`, `on_info_error`, `add_to_queue`, `download_clips`, `start_link_listener`, `poll_links`, `bring_to_front`, `open_link`, `_retry_link`, and Options <-> Plan signals.
- `luckytwitch_qt.py`: `LuckyApplication(QApplication)` handling macOS `QFileOpenEvent`, command-line `luckytwitch://` link detection and single-instance `weblink.hand_off`.
- `qt_ui/theme.py`: `QLabel[role="err"]`, `QPlainTextEdit#cutPoints`, `QPlainTextEdit#planPreview`, `QWidget#timelineWell`.
- `tests/test_qt_plan_tab.py`: 55 test functions (59 test cases) porting `test_gui_plan_tab.py` (31), `test_gui_plan_redesign.py` (10), `test_gui_weblink.py` (16), and the Plan-tab tests of `test_gui_final_pass.py` (5).
- `tests/test_qt_main_window.py` & `tests/test_qt_queue_tab.py`: updated `test_all_four_tabs_are_populated`, the `LuckyApplication` monkeypatch, and `test_closing_without_a_heartbeat_file_is_fine` (since `MainWindow` now starts the link listener and writes `BEAT_PATH` on init).
- Docs updated: `HANDOFF.md` (Working modes note added, Phases 4 & 5 marked `approved`, Phase 6 marked `done (waiting for approval)`), `PHASE_NOTES.md`, `VERSIONS.md`, `PARITY.md` (62 boxes ticked), `MIGRATION_LOG.md` (no. 12 updated, no. 16–17 added), `SETTINGS_KEYS.md`.

**Checked here (Windows, Python 3.14.7, PySide6 6.12.0, offscreen):** `python -m pytest tests/test_qt_plan_tab.py tests/test_qt_main_window.py -q` -> 71 passed in 17.52s.

**NOT done:** the real custom QPainter timeline strip (belongs to Phase 7); the user's hands-on check of the Plan tab on Windows.

**NOT run:** the full test suite (`python -m pytest tests -q`), hands-on interactive run of `python luckytwitch_qt.py`.

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

### v3  (2026-10-26)  docs only, Windows run clean

No code changed. The Windows run of v2 (Python 3.14) passed everything: 13 + 60 + 82 tests, the golden test (25), and the full suite 1206 passed, 31 skipped. PHASE_NOTES.md has the Definition of Done table and HANDOFF.md marks Phase 5 as done, waiting for approval.

**NOT done:** the hands-on look at the Options tab on Windows.

