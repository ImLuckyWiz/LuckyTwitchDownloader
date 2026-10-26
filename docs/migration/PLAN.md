# LuckyTwitch Downloader: tkinter to PySide6 migration plan

For the agent(s) doing the work. Based on a read of luckytwitch_downloader.py, the ui/ package, REDESIGN_PROGRESS.md, the GUI tests and the CI/build files (see section 8 for what was not covered). Sizes and counts are from v1.16.0.

**Working mode.** The agent has no access to the Git repository. The user uploads a zip of the repository at the start of each session; the agent works on a copy and delivers a zip with only the new and changed files, plus the git commands for the user to run. HANDOFF.md (same folder) is the living status file and section 4 of it has the exact delivery format. Where this plan says the agent tags or opens a pull request, the user does it with the commands the agent provides.

## 1. Rules for the agent (read first)

- **One phase per session.** At the end of a phase: stop, report against that phase's Definition of Done (DoD), list any divergences, and wait for the user's explicit go-ahead. Never start the next phase on your own, and never batch phases. A phase may be delivered in versions (`-v1`, `-v2`, ...) before it is finished: see HANDOFF.md section 3 and section 4, "Versions of a phase".
- **Parity first, redesign second.** Phases 0-8 reproduce today's behaviour in Qt. Layout or information-architecture changes happen only in Phase 9. Build widgets in the new styling from the start (cheap in Qt), but keep screens laid out as they are now.
- **The tkinter app stays shippable until Phase 8.** All new code goes in new packages. Old files change only where a phase explicitly says so. Main is frozen: the 1.x app gets no updates until the PySide6 version is complete.
- **Do not touch** luckytwitch_engine.py, weblink.py, premiere-plugin/ or premiere-plugin-cep/. None of them import tkinter. If you find a bug there, report it, do not fix it.
- **No silent improvements.** Anything that deliberately differs from the tkinter behaviour gets an entry in MIGRATION_LOG.md.
- **Read before porting.** For each screen, read its tkinter source and its tests/test_gui_*.py file first, and write the list of behaviours to preserve into PARITY.md. Tick them off as they are ported. The test names are a good index of behaviours.
- **Qt thread rule.** Widgets, QPixmap and dialogs only on the GUI thread. Worker threads talk to the UI through signals. QImage may be used in threads.
- **Settings JSON keys stay identical**, so existing users' saved settings still load.
- **Never claim something works without running it.** Say what you ran and what you could not run (the real GUI, Windows or macOS behaviour, a missing display or package). Checks you cannot run become commands for the user, with the output to paste back.
- **Delivery zips never contain** a `.git` folder (it would overwrite the user's Git history), `__pycache__`, `.pytest_cache`, build output or other generated files. If the uploaded zip contains a `.git` folder, do not read or modify it.
- **Checkpoint:** the user tags `migration-phase-N` at the end of every approved phase. The agent provides the commands.

## 2. Goal and scope

Move the GUI from tkinter/ttk to PySide6 with the same features, then (Phase 9, optional) upgrade the look and layout. The engine (luckytwitch_engine.py, about 145 KB) is already UI-free and stays as it is. Roughly 3,400 lines of UI code plus about 2,600 lines of GUI tests must be rewritten.

## 3. What exists today (inventory)

### 3.1 Files

- luckytwitch_downloader.py (1,645 lines): the App class, the main window, Search and Queue tabs, Twitch sign-in dialog, link handling, queue worker, main().
- ui/widgets.py (560): Toggle, Tooltip, info_icon, Card, SettingRow, ScrollFrame, ScrollPage, SideNav, Collapsible, TokenChips, EmptyState, wrap_to.
- ui/timeline.py (726): Viewport (pure logic), Timeline (canvas widget), helpers nice_step, game_colour, zone_at.
- ui/options_tab.py (441): OptionsTabMixin. ui/plan_tab.py (302): PlanTabMixin. ui/theme.py (251): ttk styles and dark_titlebar. ui/common.py (72): palette, fonts, icon.
- luckytwitch_engine.py: jobs, cutting, chat, chapters, Twitch client, tools. No tkinter.
- weblink.py: luckytwitch:// link parsing and the file-inbox hand-off. No tkinter.

### 3.2 Window structure

Window 1020x910, minimum 900x560. Top bar: VOD URL/ID entry, Get info (accent button), Twitch API button. Below it an info line. Then four tabs: **Search**, **Plan**, **Options**, **Queue & log**. Bottom, always visible: progress bar and status line.

- Search: streamer search box, sign-in banner (shown while not signed in), Results list (live marker), Recent streamers list with Clear recent, VOD kind combo, VOD table (thumbnail, title, date, length, views), Load more, Use this VOD (double-click or Enter also works).
- Plan: Timeline card, Cut points text box with live preview, Clips to chapters card (switch, filters, clips table), fixed footer with the Add to queue buttons.
- Options: left sidebar with seven sections (Output, Cuts, Chapters, Premiere Pro, Chat, Clips, Tools), one visible at a time. Rows are name + hint + control. Advanced areas collapsed by default (their values still apply). Template fields have clickable {token} chips and a live example line.
- Queue & log: queue table (#, Video, Parts, Strategy, Status; rows coloured by status), summary line, buttons (Start queue, Cancel current, Remove selected, Clear finished, Open folder), colour-coded log with Copy and Clear.
- Twitch API dialog (modal): device-code sign-in (code shown, browser opened, cancel, sign out) plus an advanced own-app Client ID/Secret form.

### 3.3 State and settings

- self.vars is a dict of name to tk.Variable (BooleanVar or StringVar, chosen from the type of the default). Every setting lives there; save_settings() dumps all of them to SETTINGS_PATH; build_options() and build_filter() read them to build JobOptions and ClipFilter. The Options tab and Plan tab bind widgets to these variables directly. This binding style has no Qt equivalent and is the main design change (see decision D3).
- Paths: DATA_DIR is the per-user data folder when frozen (packaged) and APP_DIR otherwise. CONFIG_PATH, SETTINGS_PATH, RECENT_PATH, LINKS_DIR and BEAT_PATH hang off it. The tests monkeypatch these as attributes of the main module.
- Search state: sv_gen is a generation counter so results of older requests are ignored; recent streamers are capped at MAX_RECENT = 12.

### 3.4 Threading and messages

Workers are plain threads (job worker, 4 thumbnail workers, tools setup, Get info, search, VOD list, timeline frames, saved-chat render, Twitch login). They post tagged tuples to self.q; poll_queue() runs every 100 ms via root.after and dispatches on these kinds: info_ok, error, log, search_ok, search_err, videos_ok, videos_err, thumb, frames, progress, job, item, tools_info, tools_done, saved_chat_done, queue_done. The login dialog has its own queue and a 250 ms pump (kinds: code, ok, error, cancelled). Cancellation uses a Ctx object with cancel().

### 3.5 Custom widgets (all hand-built in tkinter)

Toggle (animated canvas switch), Card, SettingRow, Collapsible, SideNav (keyboard Up/Down), TokenChips (insert at cursor or replace selection), EmptyState (overlay message on top of a list, optional button), Tooltip and info icon, ScrollFrame and ScrollPage (manual scroll-region and mouse-wheel handling), wrap_to (re-wrap labels on resize). Most of these exist natively or are much simpler in Qt.

### 3.6 Timeline

Hand-drawn on a tk.Canvas: ruler, game segments, part ranges, clip marks, muted stretches, thumbnail strip from the VOD storyboard (PIL images), hover preview overlay. Interaction: drag edges with snapping, double-click and right-click to add/remove cuts, wheel zoom anchored at the cursor, drag to pan, horizontal scrollbar, undo history, throttled redraw. Viewport, nice_step, game_colour and zone_at are pure logic and can be reused as they are. This is the riskiest component.

### 3.7 Platform glue

- luckytwitch:// links: another launch drops a file in LINKS_DIR (polled every 500 ms) and a heartbeat file BEAT_PATH is touched about every 2 s; on macOS the system calls the app via ::tk::mac::LaunchURL. open_link() fills the Plan tab and loads the VOD, waits while the app is busy (up to 180 retries), and never queues anything by itself. main() calls weblink.hand_off() before creating the window.
- bring_to_front() uses the topmost trick. dark_titlebar() uses ctypes and DWM on Windows. SetProcessDpiAwareness via ctypes. set_app_icon() also sets a Windows taskbar identity.
- Palette (ui/common.py): BG #1e1f22, BG2 #2b2d31, BG3 #3a3c42, FG #e6e6e6, MUTED #9a9da4, ACCENT #9146ff (hover #a46bff, press #7b35e6, dim #3a2a66), OK, ERR, WARN, BORDER, HOVER. Fonts: Segoe UI/Consolas on Windows, Helvetica Neue/Menlo on macOS, DejaVu on Linux.

### 3.8 Tests

Nine GUI test files, 197 tests (timeline 53, options 37, plan 27, queue 19, search 18, weblink 14, theme/icon 13, plan redesign 10, final pass 6). They need a real Tk and display (xvfb on headless), build the whole App in a fixture and monkeypatch module-level names and messagebox functions. Non-GUI tests (engine, naming, chapters, HLS, weblink, plugin JSON) are unaffected by this migration. REDESIGN_PROGRESS.md records two timeline tests that failed before any redesign work (clip mark expected at 600 but clip_start() returns 600.4); re-check their current status in Phase 0.

### 3.9 Build and CI

PyInstaller through build_windows.bat and build_mac.sh, an Inno Setup installer (installer.iss), and .github/workflows/build.yml (Windows and macOS matrix on Python 3.12, plus separate jobs for the Premiere plugins and the release notes). requirements.txt: requests, pillow, pyinstaller. A progress-eta.patch file sits in the repo root; check whether it is still relevant.

## 4. Concept mapping

| tkinter today | Qt equivalent |
| --- | --- |
| tk.Tk, ttk.Notebook | QMainWindow, QTabWidget |
| pack/grid/place (about 170 calls) | QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, stretch factors |
| tk.StringVar/BooleanVar bound to widgets | no equivalent: a settings binder plus widget signals (textChanged, toggled) |
| root.after(100, poll_queue) and queue.Queue | Bridge(QObject) with one signal per message kind (queued connections) |
| ttk.Treeview (6 uses) | QTableView/QListView with a model and a delegate for thumbnails |
| tk.Text with tags (log, preview, cut points) | QPlainTextEdit/QTextEdit with QTextCharFormat |
| tk.Canvas (Toggle, Timeline) | QWidget.paintEvent with QPainter; QPropertyAnimation for the switch |
| ScrollFrame, ScrollPage | QScrollArea (wheel handled natively) |
| messagebox, filedialog | QMessageBox, QFileDialog behind a small dialogs service (so tests can replace it) |
| Toplevel with grab_set | modal QDialog |
| ttk styles in theme.py | QSS generated from the palette tokens, Fusion base style |
| ImageTk.PhotoImage | QPixmap on the GUI thread, QImage in workers |
| bind and Configure events | QShortcut, keyPressEvent, eventFilter, resizeEvent |
| clipboard_clear/append | QGuiApplication.clipboard() |
| attributes -topmost | raise_() and activateWindow() (Windows may need an extra workaround) |
| ::tk::mac::LaunchURL | QFileOpenEvent in a QApplication subclass |
| ctypes SetProcessDpiAwareness | remove (Qt 6 is DPI-aware) |
| dark_titlebar (DWM ctypes) | keep as a fallback; check Qt's color-scheme API first |

## 5. Target architecture and decisions to confirm

New packages next to the old ones:

- qt_ui/ with theme.py, widgets/, tabs/ (search.py, plan.py, options.py, queue.py), timeline/, dialogs.py, bridge.py, main_window.py.
- core/ for UI-free helpers needed by the Qt app. These are currently inside luckytwitch_downloader.py, which imports tkinter, so they cannot be imported from there: settings and recent load/save, _read_config, credentials and token helpers, make_client, status_word, status_label, log_kind, queue_summary, build_options/build_filter logic. **Copy them in Phase 1, do not move them**, because the existing tests monkeypatch those names on the main module. The duplication is removed at cutover.
- luckytwitch_qt.py as the new entry point. The tkinter entry point stays until cutover.

Decisions (recommended answer first; the user confirms before Phase 1):

- **D1 Versions.** Pin Python 3.12 (as CI does) and a current stable PySide6 6.x. Verify a PySide6 wheel exists for whatever Python is used.
- **D2 Timeline.** Custom QWidget with QPainter (recommended: the current code already draws by coordinates and Viewport is reusable) versus QGraphicsView.
- **D3 Worker-to-UI bridge and settings.** A Bridge(QObject) with typed signals replacing the string-tagged tuples, and a SettingsBinder that maps each existing settings key to a widget, replacing self.vars.
- **D4 Styling.** QSS from the palette tokens, Fusion base style.
- **D5 Lists.** QAbstractTableModel plus QTableView for VODs and the queue; QListView for the channel lists.
- **D6 Rollout.** Ship Qt alongside tkinter for at least one release before deleting tkinter.
- **D7 Redesign scope** for Phase 9 is decided by the user (references or mockups), not by the agent.

## 6. Phases

Sizes are relative: S, M, L, XL.

### Phase 0: Baseline and decisions (S). No changes to the app's code.

- Run the full pytest suite on the current code and record the result. Non-GUI tests can run anywhere; the GUI tests need tkinter and a display (on Linux: xvfb-run -a python -m pytest). If the agent's environment has no tkinter, the GUI baseline becomes a check for the user: the agent gives the command and says what output to paste back. Decide for the two known failing timeline tests: fix, or xfail with a reason (wait for the user's OK before changing any test).
- Screenshot every tab, Options section and dialog of the tkinter app at 1020x910 and at the minimum size 900x560, into docs/migration/baseline/. If the agent cannot run the GUI, it lists exactly which screenshots the user must take and the file names to use.
- Create PARITY.md (one section per screen, behaviours taken from source and test names), SETTINGS_KEYS.md (every key in DEFAULTS with its type), MIGRATION_LOG.md (empty, with a short header).
- Set up the environment: requirements-qt.txt (PySide6, pytest-qt) as a new file, a tiny hello-window script that proves PySide6 runs (QT_QPA_PLATFORM=offscreen when there is no display).
- Check whether progress-eta.patch is still relevant and re-measure the file sizes in HANDOFF.md section 6.
- **DoD:** baseline test report, screenshots (or the exact list the user must take), the three docs, requirements-qt.txt and the hello-window running, user confirmation of D1-D6.

### Phase 1: Skeleton and plumbing (M)

- qt_ui/ and luckytwitch_qt.py. Theme module with the palette tokens, generated QSS, per-platform fonts, app icon from assets/.
- Main window: title, size 1020x910, minimum 900x560, icon, top bar (entry, Get info, Twitch API; handlers are stubs), info line, four empty tabs with the same names, bottom progress bar and status line.
- core/ with copies of the settings, recent, config, status and log helpers.
- Bridge with one signal per message kind listed in 3.4.
- **DoD:** window opens with the theme (offscreen is acceptable for the agent; the user checks it on Windows); a pytest-qt smoke test; a settings round-trip test that loads a real settings file written by the tkinter app; a test that emits a Bridge signal from a worker thread and receives it on the GUI thread.

### Phase 2: Widget kit (M)

- Port Toggle (animated switch, keyboard and mouse), Card, SettingRow (title, hint, info tooltip, control on the right, divider), Collapsible, SideNav (Up/Down keys), TokenChips (insert at cursor, replace a selection), EmptyState (overlay on a list or table with title, text and optional button), info icon with tooltip, scroll page with fixed footer. wrap_to is not needed (word-wrapped labels).
- A gallery script showing every widget in every state.
- Sources: ui/widgets.py, tests/test_gui_theme_and_icon.py.
- **DoD:** each widget has pytest-qt tests for its behaviours; gallery reviewed by the user.

### Phase 3: Queue and log tab, the first vertical slice (M)

- Queue table with the five columns, rows coloured by status word, summary line, empty state, the five buttons. Log with colour-coded lines, autoscroll, Copy log, Clear log.
- Progress bar and status line (determinate and indeterminate modes, the Job n/m prefix). The worker thread that runs run_job per queue item with Ctx cancel. Closing the window while a job runs asks for confirmation, cancels, saves settings and removes BEAT_PATH.
- Sources: build_queue_tab, refresh_queue_summary, set_item_status, start_queue, cancel_current, remove_selected, clear_finished, set_progress, poll_queue, on_close; tests/test_gui_queue_tab.py (19 tests).
- Tests use a fake run_job, no network.
- **DoD:** every queue behaviour in PARITY.md has a Qt test; an end-to-end test with a fake job updates rows and progress; one manual run of a real short job by the user.

### Phase 4: Search tab and Twitch sign-in (L)

- Search entry and button, sign-in banner (update_search_state), Results list with live marker, Recent streamers with Clear recent, VOD kind combo that reloads, VOD table with thumbnails, Load more with cursor pagination, the generation counter that discards stale results, empty-state messages.
- Thumbnails: 4 worker threads fetch to disk, the GUI thread builds QPixmaps into a size-capped cache, a delegate paints them. Pillow stays in the project because timeline frames are PIL images.
- Twitch API dialog: device-code login in a thread with a cancel event, code display, open page again, sign out; own-app form validated through TwitchClient.refresh_token; thread results come back by signals; closing cancels.
- Sources: build_search_tab, on_search*, load_channel, on_videos_*, _thumb_worker, on_thumb, ask_credentials; tests/test_gui_search_tab.py (18).
- **DoD:** behaviours ticked in PARITY.md; stale-result test; a login-flow test with a fake device-code API.

### Phase 5: Options tab (M-L)

- Sidebar with the seven sections, one visible at a time, scroll reset on switch, Advanced areas collapsed by default.
- SettingsBinder bound to every existing key. build_options() and build_filter() ported, including tolerant number parsing with defaults.
- Template fields with token chips and live examples computed by the engine's own naming functions (part_stem, stream_dir, _SafeDict), using the loaded VOD or a sample; a half-typed template must never raise; Stream folder name is disabled while Organize in subfolders is off.
- Chat section including the overlay render options and Render saved chat; Tools section (status, update check on startup, update now, open tools folder) with the tools setup thread.
- Sources: ui/options_tab.py and the settings parts of the main file; tests/test_gui_options_tab.py (37).
- **DoD:** a golden test that, for several settings fixtures, checks the Qt build_options() equals the JobOptions the tkinter App builds from the same settings (this is the strongest parity check in the project; if the agent cannot run the tkinter side, it writes the test and the user runs it); plus the behaviours in PARITY.md.

### Phase 6: Plan tab without the timeline, Get info and links (L)

- Cut points editor (monospace) with the live preview and its ok/err/muted colouring; Clips to chapters card (switch, filter fields, clips table, open clip, split at clip, refresh); fixed footer with the Add to queue buttons. Leave a placeholder where the timeline goes.
- Get info flow: thread, busy animation on the status line, populate source and clips, start timeline frame loading.
- Links: unchanged weblink.py; poll LINKS_DIR and the heartbeat; macOS QFileOpenEvent instead of LaunchURL; bring-to-front; open_link with its busy-wait, never auto-queueing; main() hands off before creating the window; remove the ctypes DPI call.
- Sources: ui/plan_tab.py, the Get info and link sections of the main file; tests/test_gui_plan_tab.py (27), test_gui_plan_redesign.py (10), test_gui_weblink.py (14), test_gui_final_pass.py (6, tab order via setTabOrder).
- **DoD:** behaviours ticked; a link hand-off test between two processes; manual link test from a browser on Windows and macOS by the user.

### Phase 7: Timeline (XL). Five sub-steps, each in its own session and approved separately.

- **7a Pure logic.** Copy Viewport, nice_step, game_colour, zone_at, snapping and undo history into a module with no UI imports; reuse the existing assertions that need no Tk.
- **7b Static paint.** Ruler, game segments, part ranges and clip marks in a QWidget with QPainter; the toolbar (minus, plus, Fit, Undo, Show muted switch and muted info), the hint line, the horizontal scrollbar. Account for devicePixelRatio.
- **7c Thumbnail strip.** Storyboard frames with the none/loading/ready/failed states, dimmed variants, hover preview image. PIL to QImage conversion.
- **7d Interaction.** Press and drag edges with snapping, double-click and right-click, wheel zoom anchored at the cursor, drag to pan, keyboard, on_edit callback, undo. Throttle redraws like the current invalidate/redraw job.
- **7e Hover overlay and muted ranges**, then polish and focus handling.
- Sources: ui/timeline.py; tests/test_gui_timeline.py (53 tests that drive handlers with fake events; map them to QTest mouse events).
- **DoD per sub-step:** matching tests green and the behaviours ticked; at the end a side-by-side check against the baseline screenshots and a manual session on a long real VOD by the user.

### Phase 8: Packaging, CI and cutover (M)

- PyInstaller for PySide6: collect the Qt plugins, exclude unused Qt modules (WebEngine, QML, Multimedia and so on) to control size. Update build_windows.bat, installer.iss and build_mac.sh (check how the luckytwitch:// scheme is registered on macOS today and keep it working). Give the Qt build its own app id, install folder and data folder so it cannot overwrite a stable install.
- CI: update build.yml, add pytest with QT_QPA_PLATFORM=offscreen, keep the tkinter tests until removal.
- Measure installer size and startup time against the tkinter build. Clean-machine smoke test: install, launch, open a link from the browser, run one real job, uninstall.
- Cutover: the Qt entry becomes the default; tkinter is removed in a later release as a separate task, at which point the duplicated helpers in core/ become the single copy.
- **DoD:** installers built by CI on both platforms, the smoke test passed, size and startup numbers reported, RELEASE_NOTES.md updated.

### Phase 9: Redesign beyond parity (optional, user-led)

Only after parity sign-off, and only from references or mockups the user provides. This is where layout and tab structure may change. Nothing here is a requirement of the migration.

## 7. Cross-cutting risks

- **Timeline** is the largest risk (Phase 7), hence the sub-steps.
- **Bundle size.** PySide6 builds are typically much larger than the tkinter build; budget this in Phase 8 and decide an acceptable limit with the user.
- **Threading.** Any widget or QPixmap touched from a worker thread will crash or misbehave intermittently. Review every worker for this.
- **Test seams.** The current tests monkeypatch module-level names and messagebox functions. The Qt code needs equivalent seams (a dialogs service, path constants injected through core/), or the tests become awkward.
- **Focus and tab order.** test_gui_final_pass.py checks tab traversal; Qt needs explicit setTabOrder in custom layouts.
- **Platform glue.** macOS URL events, Windows bring-to-front, taskbar identity (AppUserModelID) and the dark title bar each need a manual check on the real OS.
- **Licensing.** PySide6 is LGPL. Check the obligations for a bundled, distributed app before release; this is not legal advice.

## 8. Not covered by this analysis

- The engine internals, weblink.py beyond its public functions, and both Premiere plugins were not read in depth.
- ui/options_tab.py and most test bodies were read only partially; PARITY.md in Phase 0 is where the full behaviour list gets built.
- The build scripts and installer.iss were not read line by line.
- Nothing was run: PySide6 was not available in the analysis environment, and the app was not launched. All sizes are rough relative estimates, not time commitments.

## 9. Session prompt

Superseded by the message the user pastes at the start of each session; the delivery format is in HANDOFF.md section 4.
