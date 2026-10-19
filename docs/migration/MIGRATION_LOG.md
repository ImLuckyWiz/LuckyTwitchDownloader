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
