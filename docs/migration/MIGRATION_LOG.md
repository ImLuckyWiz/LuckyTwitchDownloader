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

