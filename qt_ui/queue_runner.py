"""The worker threads that run the queue (port of ``App.start_queue`` and ``cancel_current``).

``QueueRunner.start(items, model=..., max_concurrent=...)`` runs ``run_job`` for waiting items.
When ``max_concurrent == 1`` (default), items run sequentially on a single worker.
When ``max_concurrent > 1``, up to N workers run in parallel, pulling dynamically from ``model``
in current row order. Nothing here touches a widget directly: worker threads report through the
Bridge (``job``, ``item``, ``log``, ``progress``, ``queue_done``) and the slots run on the GUI thread.
``run_job`` is looked up in this module when a job starts, so tests replace ``qt_ui.queue_runner.run_job``
with a fake (nothing is downloaded).
"""

from __future__ import annotations

import threading
from typing import Sequence

from PySide6.QtCore import QObject

from luckytwitch_engine import Cancelled, Ctx, run_job
from qt_ui.bridge import Bridge
from core.i18n import N_, t
from qt_ui.queue_model import QueueItem, QueueModel


class QueueRunner(QObject):
    def __init__(self, bridge: Bridge, parent: QObject | None = None, max_concurrent: int = 1):
        super().__init__(parent)
        self.bridge = bridge
        self.max_concurrent = max(1, int(max_concurrent))
        self.ctx: Ctx | None = None  # the context of the running job (for cancel button backward compatibility)
        self.active_contexts: dict[str, Ctx] = {}  # iid -> Ctx for currently running jobs
        self.worker: threading.Thread | None = None  # coordinator thread (joined by tests)
        self.workers: list[threading.Thread] = []  # active worker threads
        self._lock = threading.RLock()
        self._cancel_all_event = threading.Event()

    def is_running(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def start(
        self,
        items: Sequence[QueueItem],
        model: QueueModel | None = None,
        max_concurrent: int | None = None,
    ) -> None:
        """Run ``items`` (or pull dynamically from ``model`` in current row order). Returns at once."""
        if self.is_running():
            return
        concurrency = max(1, int(max_concurrent if max_concurrent is not None else self.max_concurrent))
        self._cancel_all_event.clear()
        bridge = self.bridge
        fallback = list(items)
        seen: set[str] = set()
        pick_lock = threading.Lock()
        counter_lock = threading.Lock()
        job_counter = [0]

        def pick_next() -> tuple[QueueItem | None, int]:
            with pick_lock:
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

        def on_item_progress(iid: str, frac: float, text: str) -> None:
            bridge.progress.emit(frac, text)
            if model is not None:
                model.set_progress(iid, frac, text)

        def worker_loop():
            while not self._cancel_all_event.is_set():
                it, total = pick_next()
                if it is None:
                    break
                with counter_lock:
                    job_counter[0] += 1
                    cur_n = job_counter[0]

                ctx = Ctx(
                    log=lambda m, item_label=it.label: bridge.log.emit(
                        f"[{item_label}] {m}" if concurrency > 1 else m
                    ),
                    progress=lambda f, msg, item_id=it.iid: on_item_progress(item_id, f, msg),
                )
                with self._lock:
                    self.active_contexts[it.iid] = ctx
                    self.ctx = ctx

                bridge.job.emit(cur_n, total)
                bridge.item.emit(it.iid, N_("running…"))
                try:
                    results = run_job(it.job, ctx)
                    it.files = [str(p) for p in results]
                    bridge.item.emit(it.iid, N_("done ({} files)").format(len(results)))
                except Cancelled:
                    bridge.item.emit(it.iid, "cancelled")
                    bridge.log.emit(f"Cancelled: {it.label}" if concurrency > 1 else "Cancelled.")
                    if concurrency == 1:
                        # Sequential queue stops on cancel
                        break
                except Exception as e:  # noqa: BLE001
                    bridge.item.emit(it.iid, "failed")
                    bridge.log.emit(t("ERROR: {error}").format(error=e))
                finally:
                    with self._lock:
                        self.active_contexts.pop(it.iid, None)
                        self.ctx = next(iter(self.active_contexts.values()), None)

        def coordinator():
            workers = []
            for _ in range(concurrency):
                th = threading.Thread(target=worker_loop, daemon=True)
                workers.append(th)
                th.start()
            with self._lock:
                self.workers = workers
            for th in workers:
                th.join()
            with self._lock:
                self.workers = []
                self.active_contexts.clear()
                self.ctx = None
            bridge.queue_done.emit()

        self.worker = threading.Thread(target=coordinator, daemon=True)
        self.worker.start()

    def cancel(self, iid: str | None = None) -> bool:
        """Cancel a running job (by iid) or all running jobs. False when there is none."""
        with self._lock:
            if iid is not None:
                ctx = self.active_contexts.get(iid)
                if ctx is not None:
                    ctx.cancel()
                    return True
                return False
            if not self.active_contexts and self.ctx is None:
                return False
            self._cancel_all_event.set()
            if self.ctx is not None:
                self.ctx.cancel()
            for ctx in list(self.active_contexts.values()):
                ctx.cancel()
            return True

    def finish(self) -> None:
        """The run is over (called on the GUI thread when ``queue_done`` arrives)."""
        with self._lock:
            self.ctx = None
            self.active_contexts.clear()
            self.workers = []
