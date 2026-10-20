"""Try the Qt Queue & log tab before the Plan tab exists (Phase 3). Not part of the app.

    python tools/queue_demo.py --fake                  # the real window with four fake jobs (nothing is downloaded)
    python tools/queue_demo.py --real <VOD URL or ID>  # ONE real job: the first 30 s of that VOD (needs network)
    python tools/queue_demo.py --real <VOD> --cut "0:10:00 - 0:10:30" --out D:\\clips
    python tools/queue_demo.py --check                 # runs the fake queue without showing anything, exit 0 or 1

Press «Start queue». The fake jobs show a job that works, one with no known progress, one that fails and a long one
to cancel. The demo keeps its own settings and heartbeat files in the temp folder, so your real ones are not touched.
In ``--real`` mode the tools (yt-dlp, ffmpeg) are prepared first, exactly like the app does at start-up.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QObject, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core import paths  # noqa: E402
from qt_ui import dialogs, queue_runner  # noqa: E402
from qt_ui.main_window import MainWindow  # noqa: E402
from qt_ui.theme import apply_theme, set_app_icon  # noqa: E402

FAKE_JOBS = (  # (name, seconds, how it ends)
    ("Works", 3.0, "ok"), ("No progress known", 2.0, "unknown"), ("Breaks half way", 1.5, "fail"),
    ("Long one (try «Cancel current»)", 20.0, "ok"),
)


def fake_run_job(job, ctx):
    name, seconds, how = job
    ctx.stage(0.0, 1.0, name)
    ctx.log(f"Starting {name}")
    steps = max(1, int(seconds * 10))
    for i in range(steps):
        ctx.check_cancel()
        if how == "unknown":
            ctx.report(None)
        else:
            ctx.report((i + 1) / steps, f"step {i + 1}/{steps}")
        if how == "fail" and i == steps // 2:
            raise RuntimeError("ffmpeg exited with code 1 (this is a fake error)")
        time.sleep(0.1 if seconds > 0.5 else 0)
    ctx.log(f"✔ {name}.mp4")
    return [f"{name}.mp4"]


class RealJob(QObject):
    """Prepares the tools, reads the VOD, then queues one real job (all slots run on the GUI thread)."""

    def __init__(self, win: MainWindow, url: str, cut: str, out: str):
        super().__init__(win)
        self.win, self.url, self.cut, self.out = win, url, cut, out
        win.bridge.info_ok.connect(self.on_info)
        win.bridge.error.connect(lambda msg: dialogs.error(win, "Error", msg))

    def start(self) -> None:
        bridge = self.win.bridge
        self.win.tools_busy = True

        def work():
            from luckytwitch_engine import Ctx, ensure_tools, get_source_info

            ctx = Ctx(log=lambda m: bridge.log.emit(m), progress=lambda f, t: bridge.progress.emit(f, t))
            try:
                ensure_tools(ctx)
                bridge.log.emit("Reading the VOD…")
                info = get_source_info(self.url)
                bridge.info_ok.emit(info, [], False, "")
            except Exception as e:  # noqa: BLE001
                bridge.error.emit(str(e))
            finally:
                bridge.tools_done.emit("")

        self.win.bridge.tools_done.connect(lambda _msg: setattr(self.win, "tools_busy", False))
        threading.Thread(target=work, daemon=True).start()
        self.win.set_status("Preparing the tools and reading the VOD…")

    def on_info(self, info, _clips, _loaded, _warn) -> None:
        from luckytwitch_engine import Job, JobOptions, make_plan

        plan = make_plan(self.cut, info.duration, "auto", 0.6)
        job = Job(info, JobOptions(cut_text=self.cut, out_dir=self.out))
        strat = {"full": "full VOD + split", "sections": "only the parts"}[plan.strategy]
        self.win.tab_queue.enqueue(job, f"{info.uploader} · {info.title}"[:70], len(plan.parts), strat)
        self.win.set_status("Queued. Press «Start queue».")


def build(fake: bool) -> MainWindow:
    tmp = Path(tempfile.gettempdir())
    paths.SETTINGS_PATH, paths.BEAT_PATH = tmp / "lt_queue_demo_settings.json", tmp / "lt_queue_demo.beat"
    win = MainWindow(settings={})  # no settings: nothing is saved on close
    win.tabs.setCurrentWidget(win.tab_queue)
    if fake:
        queue_runner.run_job = fake_run_job
        for name, seconds, how in FAKE_JOBS:
            win.tab_queue.enqueue((name, seconds, how), name, 3, "full VOD + split")
    return win


def check() -> int:
    """Run the fake queue (short) without a window on screen; 0 when the rows end as expected."""
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    win = build(fake=True)
    win.tab_queue.model.items[3].job = ("Long one", 0.3, "ok")
    for i, (name, _s, how) in enumerate(FAKE_JOBS[:3]):  # keep the demo's jobs, only make them quick
        win.tab_queue.model.items[i].job = (name, 0.3, how)
    done = []
    win.bridge.queue_done.connect(lambda: (done.append(1), app.quit()))
    QTimer.singleShot(15000, app.quit)
    win.tab_queue.start_queue()
    app.exec()
    words = [it.status for it in win.tab_queue.items]
    ok = bool(done) and words == ["done", "done", "failed", "done"] and win.status_label.text() == "Queue finished."
    print(("queue demo ok: " if ok else "queue demo FAILED: ") + ", ".join(words))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fake", action="store_true")
    mode.add_argument("--real", metavar="VOD")
    mode.add_argument("--check", action="store_true")
    ap.add_argument("--cut", default="0:00:00 - 0:00:30")
    ap.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "lt_queue_demo_out"))
    args = ap.parse_args(argv)
    if args.check:
        return check()
    app = QApplication(sys.argv[:1])
    apply_theme(app)
    set_app_icon(app)
    win = build(fake=args.fake)
    win.tab_queue.output_dir = lambda: args.out
    win.show()
    if args.real:
        real = RealJob(win, args.real, args.cut, args.out)
        QTimer.singleShot(200, real.start)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
