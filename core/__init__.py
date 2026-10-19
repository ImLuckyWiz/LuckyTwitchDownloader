"""UI-free helpers for the PySide6 app (no tkinter, no Qt imports in here).

Phase 1 copies these from luckytwitch_downloader.py (they cannot be imported from there: that module imports
tkinter, and the old tests monkeypatch those names on it). Main is frozen, so the copies do not drift. The
duplication is removed at cutover (see docs/migration/HANDOFF.md, Warnings).

Test seam: every function reads its file path from the module ``core.paths`` when it is called, so a test only has
to monkeypatch ``core.paths.SETTINGS_PATH`` (and friends), exactly like the old tests do on the main module.
"""
