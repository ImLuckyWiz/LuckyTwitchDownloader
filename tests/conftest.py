"""Make the project root importable (luckytwitch_engine, luckytwitch_downloader, ui) from the tests.

The Qt tests run on Qt's offscreen platform (no display, same result on every machine); set QT_QPA_PLATFORM
yourself to run them on a real one.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
