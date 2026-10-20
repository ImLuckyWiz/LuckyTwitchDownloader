"""Make the project root importable (luckytwitch_engine, luckytwitch_downloader, ui) from the tests.

The Qt tests run on Qt's offscreen platform (no display, same result on every machine); set QT_QPA_PLATFORM
yourself to run them on a real one.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _data_folder_in_tmp(request, tmp_path, monkeypatch):
    """The Qt window saves its settings and removes the heartbeat file when it closes (Phase 3): keep that away from
    the real data folder (the app folder when run from source). Only for the Qt test files (test_qt_*.py): the
    tests of ``core`` itself check the real paths. Tests that want their own paths patch them again."""
    if not request.module.__name__.rsplit(".", 1)[-1].startswith("test_qt_"):
        return
    try:
        from core import paths
    except ImportError:  # pragma: no cover
        return
    for name, leaf in (("SETTINGS_PATH", "luckytwitch_settings.json"), ("RECENT_PATH", "luckytwitch_recent.json"),
                       ("CONFIG_PATH", "config.json"), ("LINKS_DIR", "links"), ("BEAT_PATH", "running.beat")):
        monkeypatch.setattr(paths, name, tmp_path / "data" / leaf)
    (tmp_path / "data").mkdir(exist_ok=True)
