"""The Bridge: worker threads talk to the GUI thread through signals (pytest-qt, no display needed).

Skipped when PySide6 or pytest-qt is not installed (pip install -r requirements-qt.txt).
"""

import threading

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QObject, QThread  # noqa: E402

from qt_ui.bridge import KINDS, Bridge  # noqa: E402

# PLAN.md section 3.4: the message kinds of poll_queue
PLAN_KINDS = ["info_ok", "error", "log", "search_ok", "search_err", "videos_ok", "videos_err", "thumb", "frames",
              "progress", "job", "item", "tools_info", "tools_done", "saved_chat_done", "queue_done", "update_checked",
              "update_download_done"]


class Receiver(QObject):
    """Lives on the GUI thread; records on which thread each slot ran."""

    def __init__(self):
        super().__init__()
        self.calls: list[tuple[str, tuple, object]] = []

    def on_log(self, msg):
        self.calls.append(("log", (msg,), QThread.currentThread()))

    def on_progress(self, frac, text):
        self.calls.append(("progress", (frac, text), QThread.currentThread()))


def test_the_bridge_has_exactly_one_signal_per_message_kind(qtbot):
    assert list(KINDS) == PLAN_KINDS
    bridge = Bridge()
    assert tuple(Bridge.KINDS) == tuple(KINDS)
    for kind in PLAN_KINDS:
        assert hasattr(bridge, kind), kind
        assert "SignalInstance" in type(getattr(bridge, kind)).__name__, kind


def test_a_signal_emitted_by_a_worker_thread_arrives_on_the_gui_thread(qtbot):
    bridge, rx = Bridge(), Receiver()
    bridge.log.connect(rx.on_log)
    bridge.progress.connect(rx.on_progress)
    gui_thread = QThread.currentThread()
    worker_threads, worker_qthreads = [], []

    def work():
        worker_threads.append(threading.current_thread())
        worker_qthreads.append(QThread.currentThread())
        bridge.log.emit("hello from the worker")
        bridge.progress.emit(0.5, "halfway")

    t = threading.Thread(target=work)
    t.start()
    qtbot.waitUntil(lambda: len(rx.calls) == 2, timeout=3000)
    t.join()
    assert worker_threads[0] is not threading.main_thread()
    assert worker_qthreads[0] != gui_thread  # the comparison below can tell the two threads apart
    assert [(k, a) for k, a, _ in rx.calls] == [("log", ("hello from the worker",)), ("progress", (0.5, "halfway"))]
    assert all(thread == gui_thread for _, _, thread in rx.calls)


def test_bare_functions_and_lambdas_are_delivered_on_the_gui_thread_too(qtbot):
    bridge = Bridge()
    seen = []
    gui_thread = QThread.currentThread()

    def plain(msg):
        seen.append(("function", msg, QThread.currentThread()))

    bridge.log.connect(plain)
    bridge.log.connect(lambda msg: seen.append(("lambda", msg, QThread.currentThread())))
    t = threading.Thread(target=lambda: bridge.log.emit("x"))
    t.start()
    qtbot.waitUntil(lambda: len(seen) == 2, timeout=3000)
    t.join()
    assert {name for name, _, _ in seen} == {"function", "lambda"}
    assert all(thread == gui_thread for _, _, thread in seen)


def test_payloads_keep_their_python_types(qtbot):
    bridge = Bridge()
    got = {}
    bridge.info_ok.connect(lambda *a: got.__setitem__("info_ok", a))
    bridge.videos_ok.connect(lambda *a: got.__setitem__("videos_ok", a))
    bridge.thumb.connect(lambda *a: got.__setitem__("thumb", a))
    bridge.item.connect(lambda *a: got.__setitem__("item", a))
    bridge.job.connect(lambda *a: got.__setitem__("job", a))
    bridge.saved_chat_done.connect(lambda *a: got.__setitem__("saved_chat_done", a))
    bridge.queue_done.connect(lambda: got.__setitem__("queue_done", ()))
    source = object()
    clips = [{"id": "a"}]
    videos = [{"id": "v1", "title": "x"}]

    def work():
        bridge.info_ok.emit(source, clips, True, None)
        bridge.videos_ok.emit(3, videos, None)
        bridge.thumb.emit(3, "v1", "/tmp/t.jpg")
        bridge.item.emit("row1", "done (2 files)")
        bridge.job.emit(1, 2)
        bridge.saved_chat_done.emit("/tmp/out.mov", "")
        bridge.queue_done.emit()

    t = threading.Thread(target=work)
    t.start()
    qtbot.waitUntil(lambda: len(got) == 7, timeout=3000)
    t.join()
    assert got["info_ok"][0] is source and got["info_ok"][1] is clips and got["info_ok"][2] is True and got["info_ok"][3] is None
    assert got["videos_ok"] == (3, videos, None) and got["videos_ok"][1] is videos
    assert got["thumb"] == (3, "v1", "/tmp/t.jpg")
    assert got["item"] == ("row1", "done (2 files)") and got["job"] == (1, 2)
    assert got["saved_chat_done"] == ("/tmp/out.mov", "") and got["queue_done"] == ()


def test_many_messages_from_several_workers_all_arrive_in_order_per_worker(qtbot):
    bridge = Bridge()
    got = []
    bridge.log.connect(lambda m: got.append(m))

    def work(name):
        for i in range(50):
            bridge.log.emit(f"{name}:{i}")

    threads = [threading.Thread(target=work, args=(n,)) for n in "abc"]
    for t in threads:
        t.start()
    qtbot.waitUntil(lambda: len(got) == 150, timeout=5000)
    for t in threads:
        t.join()
    for n in "abc":
        assert [m for m in got if m.startswith(n)] == [f"{n}:{i}" for i in range(50)]
