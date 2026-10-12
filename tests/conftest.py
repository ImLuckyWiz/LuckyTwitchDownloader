"""Make the project root importable (luckytwitch_engine, luckytwitch_downloader, ui) from the tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
