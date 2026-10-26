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

## 12. «Use this VOD» does not load the VOD yet  (Phase 4, until Phase 6)
**tkinter:** puts the link in the entry, selects the Plan tab and runs «Get info».
**Qt:** puts the link in the entry and selects the Plan tab; «Get info» is still the Phase 1 stub (`MainWindow.on_get_info`), so nothing is loaded until Phase 6 builds it. The Search tab sends the link through its `vod_chosen` signal; `MainWindow.use_vod` calls `on_get_info()`, so Phase 6 only has to fill that method.
**Why:** the Get info flow belongs to Phase 6 (PLAN.md). Temporary.
