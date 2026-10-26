"""Constants of the Search tab (copied from luckytwitch_downloader.py, same values).

``tests/test_qt_search_tab.py`` compares them with the originals while the tkinter app still exists.
"""

from __future__ import annotations

# the choices of the «kind of video» drop-down and what the Twitch API calls them
VIDEO_KINDS = {
    "Past broadcasts": "archive",
    "Highlights": "highlight",
    "Uploads": "upload",
}
THUMB_SIZE = (128, 72)
THUMB_GAP = 14  # empty space to the right of each thumbnail, so the title doesn't touch it
