# Migration log

Every place where the PySide6 app deliberately differs from the tkinter app (v1.16.0) goes here, one entry each, newest at the bottom. Nothing is improved silently. Phase 9 (redesign beyond parity) changes are listed here too.

Entry format:

```
## <number>. <short title>  (Phase N)
**tkinter:** what the old app does.
**Qt:** what the new app does instead.
**Why:** the reason, and whether the user approved it.
```

No entries for Phase 0 (it changed no behaviour).

## 1. The data folder is created at start-up, not at import  (Phase 1)
**tkinter:** `luckytwitch_downloader.py` creates the data folder as a side effect of being imported.
**Qt:** importing `core.paths` has no side effect; `luckytwitch_qt.main()` calls `core.paths.ensure_data_dir()` right after creating the QApplication.
**Why:** importing a module (and so importing it in a test) should not create folders. No visible effect for the user: the folder exists before anything reads or writes it. Decided by the agent, not yet reviewed by the user.

## 2. Widget kit: signals and method names instead of callbacks and tk variables  (Phase 2)
**tkinter:** `Toggle(parent, variable, command)`, `SideNav(parent, items, command)`, `Collapsible(..., on_change)`, `EmptyState.show()/hide()`, `ScrollFrame.refit()`, `info_icon()` function, `wrap_to()`.
**Qt:** `Toggle` is a checkable button (`isChecked`/`setChecked`; `clicked` = the old `command`, `toggled` also fires for changes from code); `SideNav.selected(key)` and `Collapsible.toggled(bool)` are signals; `EmptyState.show_message()/hide_message()` (not `show`/`hide`, which are Qt's own); no `refit()` (Qt re-lays out by itself; `ScrollFrame.scroll_to_top()` added for the Options tab); `InfoIcon` is a class; `wrap_to` is not needed (word-wrapped labels, `WrapLabel` caps the height at the label's maximum width). `SideNav.step(key, delta)` is the old `_step`.
**Why:** that is how Qt widgets are used; the behaviour is the same. The agent decided it (PLAN.md section 6 says wrap_to is not needed); not yet reviewed by the user.

## 3. Tooltip also goes away when its widget is hidden or closed  (Phase 2)
**tkinter:** the tooltip hid on leave, button press and destroy.
**Qt:** also when the widget is hidden or closed, because the pop-up is a window of its own and would stay behind otherwise. It is drawn by our own label (not `QToolTip`) so it wraps at 380 px like before.
**Why:** a separate pop-up window needs it; no visible difference in normal use. Decided by the agent.

## 4. The queue is a model and a view; row ids are `I001`, `I002`, ...  (Phase 3)
**tkinter:** a `ttk.Treeview` holds the rows (Tk makes the row ids); `App.items` is a parallel list of dicts.
**Qt:** `QueueModel` (a `QAbstractTableModel`, decision D5) owns the items (`QueueItem`: job, row id, number, label, parts, strategy, plain status word, shown status text, files) and the table only shows it. Row ids are `I001`, `I002`, ... and a number is never used twice, so a status that arrives for a row that was removed is ignored. The «#» column is set when the row is added and is not renumbered, as before.
**Why:** that is how a Qt table is built; nothing changes for the user. Decided by the agent.

## 5. Busy progress bar looks different  (Phase 3)
**tkinter:** the indeterminate bar is a `ttk.Progressbar` started with `start(12)` (a block that sweeps across).
**Qt:** `QProgressBar.setRange(0, 0)` (Fusion's busy indicator, a purple block that sweeps back and forth; checked offscreen: the frames change).
**Why:** the native way in Qt. Same meaning (progress unknown), slightly different motion. Decided by the agent; check how it looks on Windows.

## 6. Closing never saves an empty settings dictionary  (Phase 3)
**tkinter:** `on_close` always writes all the settings variables.
**Qt:** `MainWindow.closeEvent` writes `self.settings` only when it is not empty. The entry point always loads the settings, so in the real app it is never empty; this only protects the saved file when a window is made without settings (tests, the demo script).
**Why:** a window with no settings would otherwise overwrite the user's file with `{}`. Until the Options tab exists (Phase 5) the window cannot change a setting, so closing writes back what was loaded (keys that are not in `DEFAULTS` are dropped, as the tkinter app does). Decided by the agent.

## 7. `Card` gives spare height to its body  (Phase 3)
**tkinter:** a card's body expanded when the page was taller than its content.
**Qt:** `Card` now adds its body with stretch 1 and its title bar with the `Maximum` height policy, so the queue and log cards share the spare height of the tab. Cards with fixed content look the same (the 92 widget tests and the gallery check still pass).
**Why:** needed for the two cards of the Queue & log tab to grow with the window. This touches a Phase 2 file (`qt_ui/widgets.py`); decided by the agent.


## 8. Emoji and other characters outside the Basic Multilingual Plane are shown  (Phase 4)
**tkinter:** `bmp()` dropped every character above U+FFFF (emoji and the like) from streamer names, VOD titles and status text, because some Windows Tk builds crash on them.
**Qt:** the text is shown as it is; Qt draws such characters (with the system emoji font) and does not crash on them. The Queue tab's labels (Phase 3) already did the same without an entry here.
**Why:** `bmp()` was a workaround for a Tk problem, not a wanted behaviour. Decided by the agent; NOT checked on Windows with a real emoji title (user check).

## 9. Thumbnails need no Pillow; the cache is capped  (Phase 4)
**tkinter:** with Pillow missing the log said «Pillow is not installed: thumbnails are disabled in the Search tab (pip install pillow).»; every thumbnail was kept for the life of the list; the 4 worker threads started with the app.
**Qt:** the thumbnails are decoded and scaled with Qt (`QImage` / `QPixmap`, on the GUI thread, stretched to 128x72 like the old `resize`), so the message is gone. The cache keeps at most 300 pixmaps (the least recently used goes first); a row whose pixmap was dropped is made again from its file when it is painted. The 4 worker threads start with the first thumbnail and end when the window closes. A thumbnail that cannot be read leaves the row without one, as before.
**Why:** Pillow stays in the project for the timeline frames (Phase 7), but the Search tab does not need it; the cap and the lazy start are the plan's wording (PLAN.md Phase 4). Decided by the agent.

## 10. Escape closes the Twitch API dialog  (Phase 4)
**tkinter:** the dialog closed with its «Close» button or the window's X only.
**Qt:** Escape closes it too (every `QDialog` does). Closing in any way cancels a sign-in that is waiting, like before.
**Why:** standard Qt behaviour; changing it would take extra code for no gain. Not asked for; the user can veto it.

## 11. The Twitch API dialog is window-modal  (Phase 4)
**tkinter:** `grab_set()` took all mouse and keyboard input of the application.
**Qt:** `open()` makes it modal for the main window only. There is one other window, so nothing visible changes. Like the tkinter version, `ask_credentials()` returns at once and does not wait for the dialog.
**Why:** how a modal `QDialog` is opened without blocking. Decided by the agent.

## 12. «Use this VOD» did not load the VOD in Phases 4–5 (resolved in Phase 6)
**tkinter:** puts the link in the entry, selects the Plan tab and runs «Get info».
**Qt:** in Phases 4 and 5 `MainWindow.on_get_info` was still the Phase 1 stub; Phase 6 implemented `on_get_info()`, so «Use this VOD» now loads the VOD on the Plan tab just like tkinter.
**Why:** the Get info flow belonged to Phase 6 (PLAN.md). Resolved.

## 13. Number fields only take whole numbers inside their range  (Phase 5)
**tkinter:** the `Spinbox` fields were plain text boxes: anything could be typed (`abc`, `7.5`, `999999`), it was stored as typed and only read tolerantly when used (`App.num`).
**Qt:** the numeric fields are `QSpinBox`es (`qt_ui.widgets.SpinBox`): whole numbers within the old `from_`/`to` range. A saved value the box cannot show (like `"7.5"`) stays in the settings dictionary untouched until the person changes that box, so an old settings file is never rewritten behind their back. `core.options.num` still reads any text tolerantly (and also survives `TypeError` and `OverflowError`), so `build_options()` gives the same result as tkinter for every settings file.
**Why:** the standard Qt control for a bounded integer. Not asked for; the user can veto it.

## 14. The mouse wheel does nothing on a drop-down or number field until it has the keyboard focus  (Phase 5)
**tkinter:** the wheel over a combobox could change its value while scrolling the page.
**Qt:** `ComboBox` and `SpinBox` ignore the wheel unless they have the focus, so scrolling the Options page never changes a setting by accident.
**Why:** a long scrolling page full of such controls. Decided by the agent; the user can veto it.

## 15. Closing the window also cancels a chat overlay that is being drawn  (Phase 5)
**tkinter:** `on_close` only cancelled the tools setup and the queue; a saved-chat overlay thread was left to die with the process (it could leave TwitchDownloaderCLI or ffmpeg running).
**Qt:** `closeEvent` cancels it too.
**Why:** no orphan processes. Decided by the agent; the user can veto it.

## 16. The timeline strip was a placeholder widget in Phase 6 (resolved in Phase 7)
**tkinter:** `PlanTabMixin` embeds the interactive `Timeline` canvas widget (`ui/timeline.py`).
**Qt:** Phase 6 used `TimelinePlaceholder` while building the rest of the Plan tab; Phase 7 replaced it with the full custom-painted `Timeline` widget (`qt_ui/timeline.py`).
**Why:** PLAN.md split the Plan tab (Phase 6) from the custom-painted Timeline widget (Phase 7). Resolved.

## 17. macOS URL launch events and bringing the window to the front use Qt APIs  (Phase 6)
**tkinter:** registered `::tk::mac::OpenDocument` via `root.createcommand`, and raised the window with `deiconify()` + `lift()` + temporary `-topmost True`.
**Qt:** `LuckyApplication(QApplication)` intercepts `QEvent.Type.FileOpen` (`QFileOpenEvent.url().toString()`) and emits `link_opened` to `MainWindow.open_link`; `MainWindow.bring_to_front()` clears `Qt.WindowState.WindowMinimized` and calls `show()`, `raise_()` and `activateWindow()`.
**Why:** the native Qt equivalents of those Tk window-system hooks. Decided by the agent.

## 18. The Timeline strip is painted with `QPainter` on a `QWidget` and uses an integer `QScrollBar`  (Phase 7)
**tkinter:** `Timeline` drew canvas items (`create_rectangle`, `create_line`, `create_text`, `create_image`, `create_polygon`) on a `tk.Canvas`, converted PIL frames with `ImageTk.PhotoImage`, and drove a fractional `ttk.Scrollbar` (`set(lo, hi)` in `0.0..1.0`).
**Qt:** `Timeline` (`qt_ui/timeline.py`, decision D2) paints the ruler, game bars, muted stretches, storyboard thumbnails, parts, cut/edge handles and hover overlay in `TimelineCanvas.paintEvent` with `QPainter`, converts PIL frames to `QPixmap` via `QImage` (`Format_RGBA8888`), and drives a horizontal `QScrollBar` scaled to `0..10000` with `pageStep` proportional to `vp.span / vp.duration`.
**Why:** decision D2 of PLAN.md; same geometry, colours, snapping and mouse/keyboard interactions. Decided by the user (D2) and the agent.

## 19. Packaging builds `luckytwitch_qt.py` and isolates pre-release installs from stable installs  (Phase 8)
**tkinter:** `build_windows.bat` and `build_mac.sh` packaged `luckytwitch_downloader.py`, and every build used the same Windows `AppId`, install folder (`LuckyTwitch`), macOS bundle ID (`com.luckytwitch.app`), taskbar ID (`LuckyTwitch.Downloader`), and data folder (`user_data_dir()`).
**Qt:** `build_windows.bat` and `build_mac.sh` now package `luckytwitch_qt.py`, exclude unused `PySide6.Qt*` modules and `tkinter`, and write the build version into `build/version.txt` (bundled at the root of the frozen app). When the build version contains a hyphen (a pre-release such as `v0.8.0-beta.1`), `installer.iss`, `build_mac.sh`, `core/paths.py`, and `qt_ui/theme.py` use a separate Windows `AppId`, install folder (`LuckyTwitch-Beta`), app name (`LuckyTwitch (Beta)`), macOS bundle ID (`com.luckytwitch.app.beta`), taskbar ID (`LuckyTwitch.Downloader.Beta`), and data folder (`LuckyTwitch-beta`). When the build version has no hyphen (stable release such as `v2.0.0`), the standard `LuckyTwitch` identity and data folder are used so upgrading from 1.x preserves the user's Twitch login, settings, recent channels, and downloaded tools.
**Why:** requested by the user in Phase 8 so pre-releases can be installed side-by-side without touching a stable 1.x install, while the `v2.0.0` cutover upgrades 1.x seamlessly in place. Approved by the user.

## 20. WCAG AA contrast repair on text tokens  (Phase 9a)
**tkinter:** `MUTED` was `#9a9da4` (4.06:1 on `BG3`, failing WCAG AA 4.5:1 text threshold); accent-colored text on `BG2` was `#9146ff` (2.97:1).
**Qt:** `MUTED` is raised to `#a3a6ad` (4.52:1 on `BG3`, 5.66:1 on `BG2`), and `ACCENT_TEXT` `#b380ff` (4.89:1 on `BG2`) is introduced for light accent text on dark surfaces. `BORDER_STRONG` (`#484b52`, 1.58:1 on `BG2`) provides visible container boundaries. Tested by `tests/test_qt_contrast.py`.
**Why:** accessibility fix from PHASE_9_PLAN.md (A4). Approved by the user.

## 21. Design tokens in QSS, rounded surfaces, keyboard focus rings, and motion controller  (Phase 9a v2)
**tkinter:** sharp square corners (`border-radius: 0`), `focusthickness=0` (no keyboard focus ring on buttons/tables), and instant `Collapsible` show/hide.
**Qt:** `qt_ui/theme.py` injects `DESIGN_TOKENS` (`qt_ui/tokens.py`) for rounded cards (`8 px`), buttons (`6 px`), inputs/chips (`4 px`), `FIELD_BORDER` input borders, `ACCENT_TEXT` on group titles/login code, `ACCENT_DIM` with a `3 px` left accent bar on selected table/list rows, and `1 px solid ACCENT_HOVER` keyboard focus rings on buttons, rail items, and tables. `qt_ui/motion.py` adds a central `Motion` controller (respecting Windows `SPI_GETCLIENTAREAANIMATION` and disabled in `tests/conftest.py`), height/width animators (`Collapsible` and `NavRail`), and `ButtonHoverAnimator` (120 ms `OutCubic` colour fade spike).
**Why:** Phase 9a design system foundation (`PHASE_9_PLAN.md` A1–A6, D13). Approved by the user.

## 22. Application shell: Left Navigation Rail, Command Bar, Loaded-VOD Strip, Toasts, Activity Pill, Shortcuts, UI State, and Plan Onboarding  (Phase 9b v1)
**tkinter:** horizontal top tab bar (`Search`, `Plan`, `Options`, `Queue & log`), plain VOD entry row, plain one-line `info_label`, 18 px progress bar above a status label, modal `messagebox.showinfo` popups for routine confirmations, no global keyboard shortcuts (`Ctrl+L`, `Ctrl+1..4`, `Ctrl+,`, `F1`), no window geometry/tab memory, and no onboarding card on an empty Plan tab.
**Qt:** `qt_ui/shell.py`, `qt_ui/toast.py`, `qt_ui/notify.py`, `qt_ui/main_window.py`, and `qt_ui/tabs/plan.py` introduce:
- **Left Navigation Rail + `PageStack` shim (B1):** 56 px collapsed / 176 px expandable rail (`Search`, `Plan` with loaded-VOD dot, `Queue & log` with item count badge at top; `Options` and expand/collapse toggle at bottom; `# ICON NEEDED: <name>` seams for Claude's `qt_ui/icons.py`), paired with `PageStack` exposing the full `QTabWidget` API so all 28 `win.tabs` uses keep working.
- **Command Bar & Account Status (B2, B4):** rounded command bar with inline `Paste` / `✕` clear action button, drag-and-drop URL/ID loading, clipboard Twitch VOD detection toast, and live `●` / `○` Twitch API sign-in indicator.
- **Loaded-VOD Strip (B3):** 48 px bar under the command bar (hidden when no VOD is loaded) showing a 16:9 thumbnail (populated from the first storyboard frame when available), bold VOD title, metadata summary, `Open on Twitch`, and `Clear` button; clicking the strip jumps to the `Plan` page.
- **Non-modal Toasts & System Notification (B5, B6):** `ToastHost` / `ToastCard` stacked at the bottom-right (auto-dismiss in 4 s, pauses on hover, optional action button like `Go to Queue` or `Open folder`), plus `notify.system_notify` when the queue finishes in the background.
- **Compact Status Bar & Activity Pill (B7):** 3 px progress bar along the top edge of the status bar, status label on the left, and clickable `Job n/m · pct%` activity pill on the right that jumps to `Queue & log`.
- **Keyboard Layer & UI State (B8, B9):** `Ctrl+L` (focus VOD bar), `Ctrl+1..4` (switch pages), `Ctrl+,` (Options), `Ctrl+Enter` / `Ctrl+Shift+Enter` (queue from Plan), `F1` (`ShortcutsDialog`), and window geometry/rail/tab persistence in `luckytwitch_ui.json`.
- **Plan Empty-State Onboarding Card (B10):** 3-step teaching banner with `Search streamers` and `Paste from clipboard` buttons above the timeline when no VOD is loaded; hides automatically once a VOD is loaded.
**Why:** Phase 9b shell redesign (`PHASE_9_PLAN.md` B1–B10, D8–D13). Approved by the user.


