"""Open a folder in the platform's file manager (copied from luckytwitch_downloader.py; no Qt, no tkinter)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_in_file_manager(path: Path, select: bool = False) -> None:
    """Open a folder in Explorer / Finder / the file manager. With select=True and a file, highlight that file."""
    path = Path(path)
    if sys.platform == "win32":
        if select and path.is_file():
            # Explorer wants  /select,"C:\full path\file.mp4"  as ONE command line. Passing a list lets
            # Python quote the whole "/select,..." argument when the path has spaces, and Explorer then
            # ignores it and opens the Documents folder. So the command line is built by hand.
            subprocess.Popen(f'explorer /select,"{os.path.normpath(str(path))}"')
        else:
            os.startfile(os.path.normpath(str(path if path.is_dir() else path.parent)))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)] if select and path.is_file() else ["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path if path.is_dir() else path.parent)])
