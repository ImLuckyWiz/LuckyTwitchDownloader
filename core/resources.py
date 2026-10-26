"""Where bundled data files live (copied from ui/common.py)."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    """A bundled data file: next to the sources, or inside the frozen bundle."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
    elif getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent.parent

    candidate = base.joinpath(*parts)
    if not candidate.exists() and getattr(sys, "frozen", False):
        # On macOS .app bundles, data files might be placed in Contents/Resources
        res_candidate = base.parent.joinpath("Resources", *parts)
        if res_candidate.exists():
            return res_candidate
    return candidate
