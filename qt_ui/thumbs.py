"""The thumbnail workers of the Search tab (port of ``App._thumb_worker``).

Four daemon threads take ``(generation, row id, url)`` from a queue, fetch the picture to the disk cache
(``fetch_thumbnail``: once per URL) and report ``bridge.thumb(generation, row id, path)``. They never touch a
widget or a QPixmap: the slot on the GUI thread builds the pixmap. A job from an older generation (the list was
replaced meanwhile) is skipped without fetching.

The threads start with the first thumbnail (not when the tab is built), and ``stop()`` ends them (the tab calls
it when the window closes). ``fetch_thumbnail`` is looked up in this module when a job runs, so tests replace
``qt_ui.thumbs.fetch_thumbnail``.
"""

from __future__ import annotations

import queue
import threading
from typing import Callable

from luckytwitch_engine import fetch_thumbnail
from qt_ui.bridge import Bridge

WORKERS = 4


class ThumbFetcher:
    def __init__(self, bridge: Bridge, generation: Callable[[], int]):
        self.bridge = bridge
        self.generation = generation  # the tab's current generation: older jobs are stale
        self.jobs: queue.Queue = queue.Queue()
        self.threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._stopped = False

    def submit(self, gen: int, iid: str, url: str) -> None:
        with self._lock:
            if self._stopped:
                return
            if not self.threads:
                for _ in range(WORKERS):
                    t = threading.Thread(target=self._work, daemon=True)
                    t.start()
                    self.threads.append(t)
        self.jobs.put((gen, iid, url))

    def stop(self) -> None:
        """End the threads (each one finishes the fetch it is in, then leaves)."""
        with self._lock:
            self._stopped = True
            n = len(self.threads)
        for _ in range(n):
            self.jobs.put(None)

    def _work(self) -> None:
        while True:
            job = self.jobs.get()
            if job is None:
                return
            gen, iid, url = job
            if gen != self.generation():
                continue  # stale: the list was replaced meanwhile
            try:
                path = fetch_thumbnail(url)
                if path:
                    self.bridge.thumb.emit(gen, iid, str(path))
            except RuntimeError:  # the Bridge is gone (the window closed): nothing left to tell
                return
            except Exception:  # noqa: BLE001
                continue
