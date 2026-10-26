"""The worker thread that runs the queue (port of ``App.start_queue`` and ``cancel_current``).

``QueueRunner.start(items, model=...)`` runs ``run_job`` for each waiting item, one after the other, on ONE daemon
thread. Nothing here touches a widget: the thread reports through the Bridge (``job``, ``item``, ``log``,
``progress``, ``queue_done``) and the slots run on the GUI thread. ``run_job`` is looked up in this module when a
job starts, so tests replace ``qt_ui.queue_runner.run_job`` with a fake (nothing is downloaded).

Phase 9c (F4): when ``model`` is supplied, the worker pulls the next ``queued`` item in the model's current row
order before starting each job (holding ``model._lock`` and tracking ``seen`` row ids so instant test fakes that
complete before the GUI thread processes ``bridge.item`` never run the same item twice). Reordering waiting rows
while a job is running therefore takes effect immediately for the remaining jobs.
"""

from __future__ import annotations

import threading
from typing import Sequence

from PySide6.QtCore import QObject

from luckytwitch_engine import Cancelled, Ctx, run_job
from qt_ui.bridge import Bridge
from qt_ui.queue_model import QueueItem, QueueModel


class QueueRunner(QObject):
    def __init__(self, bridge: Bridge, parent: QObject | None = None):
        super().__init__(parent)
        self.bridge = bridge
        self.ctx: Ctx | None = None  # the context of the job that runs now (the cancel button uses it)
        self.worker: threading.Thread | None = None

    def is_running(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def start(self, items: Sequence[QueueItem], model: QueueModel | None = None) -> None:
        """Run ``items`` (or pull dynamically from ``model`` in current row order). Returns at once."""
        if self.is_running():
            return
        bridge = self.bridge
        fallback = list(items)
        seen: set[str] = set()

        def pick_next() -> tuple[QueueItem | None, int]:
            if model is not None:
                with model._lock:
                    candidates = [it for it in model.items if it.status == "queued" and it.iid not in seen]
                    total = len(seen) + len(candidates)
                    if not candidates:
                        return None, total
                    nxt = candidates[0]
                    seen.add(nxt.iid)
                    return nxt, total
            candidates = [it for it in fallback if it.status == "queued" and it.iid not in seen]
            total = len(seen) + len(candidates)
            if not candidates:
                return None, total
            nxt = candidates[0]
            seen.add(nxt.iid)
            return nxt, total

        def work():
            n = 0
            while True:
                it, total = pick_next()
                if it is None:
                    break
                n += 1
                ctx = Ctx(log=lambda m: bridge.log.emit(m), progress=lambda f, t: bridge.progress.emit(f, t))
                self.ctx = ctx
                bridge.job.emit(n, total)
                bridge.item.emit(it.iid, "running…")
                try:
                    results = run_job(it.job, ctx)
                    it.files = [str(p) for p in results]
                    bridge.item.emit(it.iid, f"done ({len(results)} files)")
                except Cancelled:
                    bridge.item.emit(it.iid, "cancelled")
                    bridge.log.emit("Cancelled.")
                    break
                except Exception as e:  # noqa: BLE001
                    bridge.item.emit(it.iid, "failed")
                    bridge.log.emit(f"ERROR: {e}")
            bridge.queue_done.emit()

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def cancel(self) -> bool:
        """Cancel the job that runs now. False when there is none."""
        if self.ctx is None:
            return False
        self.ctx.cancel()
        return True

    def finish(self) -> None:
        """The run is over (called on the GUI thread when ``queue_done`` arrives)."""
        self.ctx = None
