"""The worker thread that runs the queue (port of ``App.start_queue`` and ``cancel_current``).

``QueueRunner.start(items)`` runs ``run_job`` for each item, one after the other, on ONE daemon thread. Nothing
here touches a widget: the thread reports through the Bridge (``job``, ``item``, ``log``, ``progress``,
``queue_done``) and the slots run on the GUI thread. ``run_job`` is looked up in this module when a job starts, so
tests replace ``qt_ui.queue_runner.run_job`` with a fake (nothing is downloaded).

Like the tkinter app: a cancelled job ends the run (the items after it stay «queued»); a failing job is marked
«failed», logged as «ERROR: ...», and the run goes on with the next one.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject

from luckytwitch_engine import Cancelled, Ctx, run_job
from qt_ui.bridge import Bridge
from qt_ui.queue_model import QueueItem


class QueueRunner(QObject):
    def __init__(self, bridge: Bridge, parent: QObject | None = None):
        super().__init__(parent)
        self.bridge = bridge
        self.ctx: Ctx | None = None  # the context of the job that runs now (the cancel button uses it)
        self.worker: threading.Thread | None = None

    def is_running(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def start(self, items: list[QueueItem]) -> None:
        """Run ``items`` (the ones that were queued when the button was pressed). Returns at once."""
        if self.is_running():
            return
        bridge, todo = self.bridge, list(items)

        def work():
            for n, it in enumerate(todo, 1):
                ctx = Ctx(log=lambda m: bridge.log.emit(m), progress=lambda f, t: bridge.progress.emit(f, t))
                self.ctx = ctx
                bridge.job.emit(n, len(todo))
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
