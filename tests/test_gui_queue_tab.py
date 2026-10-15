"""Queue tab after the redesign: coloured rows with an icon, the one-line summary, the empty-state message, the
coloured log (with Copy / Clear), and that the queue still runs on the same plain status words.

Needs Tk and a display like the other GUI tests (xvfb-run -a python -m pytest); skipped when there is none.
Nothing is downloaded: ``run_job`` is replaced.
"""

import time

import pytest

tk = pytest.importorskip("tkinter")

import luckytwitch_downloader as dl  # noqa: E402
from test_gui_plan_tab import gui  # noqa: E402,F401  (the fixture that opens the real window)
from ui import common  # noqa: E402


def add(gui, n=1, label="Streamer · Stream"):
    """Queue n stand-in jobs (the job object is never run unless a test patches run_job)."""
    for i in range(n):
        gui.app.enqueue(object(), f"{label} {i + 1}", 3, "full VOD + split")
    return [it["iid"] for it in gui.app.items]


def row(gui, iid):
    return gui.app.qtree.set(iid, "status"), gui.app.qtree.item(iid, "tags")


def log_lines(gui):
    """[(text, tags of the message part)] for every log line."""
    t = gui.app.log_text
    out = []
    for i in range(1, int(t.index("end-1c").split(".")[0]) + 1):
        msg_index = f"{i}.end-2c"  # a character inside the message, after the time stamp
        text = t.get(f"{i}.0", f"{i}.end")
        if text:
            out.append((text, t.tag_names(msg_index)))
    return out


# ------------------------------------------------------------------ the pure helpers
@pytest.mark.parametrize("status, word", [
    ("queued", "queued"), ("running…", "running"), ("done (3 files)", "done"), ("failed", "failed"),
    ("cancelled", "cancelled"), ("", ""), ("waiting: x", "waiting"),
])
def test_status_word_is_the_first_word(status, word):
    assert dl.status_word(status) == word


def test_status_label_puts_an_icon_in_front_of_known_statuses():
    assert dl.status_label("queued") == "○ queued"
    assert dl.status_label("running…") == "▶ running…"
    assert dl.status_label("done (3 files)") == "✓ done (3 files)"
    assert dl.status_label("failed") == "✕ failed"
    assert dl.status_label("cancelled") == "■ cancelled"
    assert dl.status_label("something new") == "something new"  # unknown words are shown as they are


def test_every_status_has_an_icon_and_a_colour():
    assert set(dl.STATUS_ICONS) == set(dl.STATUS_COLOURS) == {"queued", "running", "done", "failed", "cancelled"}
    assert set(dl.FINISHED) == {"done", "failed", "cancelled"}


@pytest.mark.parametrize("msg, kind", [
    ("ERROR: ffmpeg exited with code 1", "err"),
    ("Warning: ffprobe was not found next to ffmpeg", "warn"),
    ("Could not use the segment download (HTTP 403)", "warn"),
    ("Cancelled.", "warn"),
    ("Chat for part 2 failed (the video is still being recorded)", "warn"),
    ("Chat download skipped: it only works for Twitch VODs", "warn"),
    ("Server busy (usher.ttvnw.net), retrying", "warn"),
    ("✔ Big Stream part 1.mp4", "ok"),
    ("yt-dlp 2026.10.01 installed.", "ok"),
    ("yt-dlp is up to date (2026.10.01).", "ok"),
    ("Queued: Streamer · Stream (3 parts, full VOD + split)", "muted"),
    ("yt-dlp: 10% of 4.2GiB at 12MiB/s", "plain"),
    ("Starting job 1/5", "plain"),
    ("", "plain"),
])
def test_log_lines_are_classified(msg, kind):
    assert dl.log_kind(msg) == kind


def test_queue_summary_counts_in_a_fixed_order():
    assert dl.queue_summary([]) == ""
    assert dl.queue_summary(["queued", "queued"]) == "2 queued"
    assert dl.queue_summary(["done", "failed", "queued", "running", "cancelled", "done"]) == \
        "1 running  ·  1 queued  ·  2 done  ·  1 failed  ·  1 cancelled"
    assert dl.queue_summary(["done (3 files)", "running…"]) == "1 running  ·  1 done"  # full strings work as well


# ------------------------------------------------------------------ the list
def test_the_empty_queue_says_what_to_do_and_the_button_goes_to_the_plan_tab(gui):
    app = gui.app
    assert app.queue_empty.shown
    labels = [w.cget("text") for w in app.queue_empty._inner.winfo_children() if w.winfo_class() == "Label"]
    assert labels[0] == "Nothing in the queue yet"
    button = next(w for w in app.queue_empty._inner.winfo_children() if w.winfo_class() == "TButton")
    app.notebook.select(app.tab_queue)
    button.invoke()
    assert app.notebook.select() == str(app.tab_plan)
    assert app.queue_summary_var.get() == ""


def test_a_queued_job_is_listed_with_its_icon_colour_and_count(gui):
    app = gui.app
    (iid,) = add(gui)
    assert not app.queue_empty.shown
    assert row(gui, iid) == ("○ queued", ("queued",))
    assert app.items[0]["status"] == "queued"  # the stored status stays the plain word
    assert app.queue_summary_var.get() == "1 queued"
    assert list(app.qtree.item(iid, "values"))[:4] == ["1", "Streamer · Stream 1", "3", "full VOD + split"]  # Tk hands values back as text


@pytest.mark.parametrize("status, word, shown", [
    ("running…", "running", "▶ running…"),
    ("done (3 files)", "done", "✓ done (3 files)"),
    ("failed", "failed", "✕ failed"),
    ("cancelled", "cancelled", "■ cancelled"),
])
def test_a_job_changes_colour_and_icon_with_its_status(gui, status, word, shown):
    app = gui.app
    (iid,) = add(gui)
    app.set_item_status(iid, status)
    assert row(gui, iid) == (shown, (word,))
    assert app.items[0]["status"] == word
    assert app.queue_summary_var.get() == f"1 {word}"


def test_the_row_colours_match_the_palette(gui):
    tree = gui.app.qtree
    for word, colour in dl.STATUS_COLOURS.items():
        assert str(tree.tag_configure(word, "foreground")) == colour
    assert dl.STATUS_COLOURS["done"] == common.OK and dl.STATUS_COLOURS["failed"] == common.ERR


def test_the_summary_follows_every_change_of_the_queue(gui):
    app = gui.app
    a, b, c = add(gui, 3)
    app.set_item_status(a, "done (1 files)")
    app.set_item_status(b, "failed")
    assert app.queue_summary_var.get() == "1 queued  ·  1 done  ·  1 failed"
    app.clear_finished()
    assert [it["iid"] for it in app.items] == [c]
    assert app.queue_summary_var.get() == "1 queued"
    app.qtree.selection_set(c)
    app.remove_selected()
    assert not app.items and app.queue_empty.shown and app.queue_summary_var.get() == ""


def test_a_running_job_cannot_be_removed(gui):
    app = gui.app
    (iid,) = add(gui)
    app.set_item_status(iid, "running…")
    app.qtree.selection_set(iid)
    app.remove_selected()
    assert len(app.items) == 1 and gui.boxes and gui.boxes[0][1] == "Running"


def test_headings_line_up_with_their_columns(gui):
    tree = gui.app.qtree
    for col in tree["columns"]:
        assert tree.heading(col, "anchor") == tree.column(col, "anchor")


def test_the_queue_still_runs_on_the_plain_status_words(gui, monkeypatch):
    app = gui.app
    deadline = time.time() + 5
    while app.tools_busy and time.time() < deadline:  # the stubbed tool setup reports back through the queue
        app.poll_queue()
        gui.root.update()
        time.sleep(0.02)
    monkeypatch.setattr(dl, "run_job", lambda job, ctx: ["a.mp4", "b.mp4"])
    a, b = add(gui, 2)
    app.set_item_status(b, "done (1 files)")  # already finished: must not run again
    app.start_queue()
    deadline = time.time() + 5
    while app.worker.is_alive() and time.time() < deadline:
        app.poll_queue()
        gui.root.update()
        time.sleep(0.02)
    for _ in range(5):
        app.poll_queue()
    assert row(gui, a) == ("✓ done (2 files)", ("done",))
    assert row(gui, b) == ("✓ done (1 files)", ("done",))
    assert app.queue_summary_var.get() == "2 done"
    assert str(app.start_btn.cget("state")) == "normal" and str(app.cancel_btn.cget("state")) == "disabled"


def test_a_failing_job_is_marked_failed_and_logged_in_red(gui, monkeypatch):
    app = gui.app
    deadline = time.time() + 5
    while app.tools_busy and time.time() < deadline:
        app.poll_queue()
        gui.root.update()
        time.sleep(0.02)

    def boom(job, ctx):
        raise RuntimeError("ffmpeg exited with code 1")

    monkeypatch.setattr(dl, "run_job", boom)
    (iid,) = add(gui)
    app.start_queue()
    deadline = time.time() + 5
    while app.worker.is_alive() and time.time() < deadline:
        app.poll_queue()
        time.sleep(0.02)
    for _ in range(5):
        app.poll_queue()
    assert row(gui, iid) == ("✕ failed", ("failed",))
    text, tags = log_lines(gui)[-1]
    assert text.endswith("ERROR: ffmpeg exited with code 1") and "err" in tags


# ------------------------------------------------------------------ the log
def test_log_lines_get_a_muted_time_stamp_and_a_colour_by_kind(gui):
    app = gui.app
    app.log("Starting job 1/1")
    app.log("ERROR: it broke")
    app.log("Cancelled.")
    app.log("✔ part 1.mp4")
    lines = log_lines(gui)[-4:]
    assert [("err" in t, "warn" in t, "ok" in t) for _, t in lines] == [
        (False, False, False), (True, False, False), (False, True, False), (False, False, True)]
    assert app.log_text.get("1.0", "1.1") == "["
    assert "stamp" in app.log_text.tag_names("1.2")  # the «[hh:mm:ss]» part is muted


def test_the_log_is_read_only_and_follows_the_newest_line(gui):
    app = gui.app
    for i in range(80):
        app.log(f"line {i}")
    assert str(app.log_text.cget("state")) == "disabled"
    gui.root.update()
    assert app.log_text.yview()[1] == pytest.approx(1.0)


def test_clear_log_empties_it(gui):
    app = gui.app
    app.log("something")
    app.clear_log()
    assert app.log_text.get("1.0", "end").strip() == ""
    assert str(app.log_text.cget("state")) == "disabled"
    app.log("after")  # and it keeps working
    assert "after" in app.log_text.get("1.0", "end")


def test_copy_log_puts_the_text_on_the_clipboard(gui):
    app = gui.app
    app.log("first")
    app.log("ERROR: second")
    app.copy_log()
    clip = gui.root.clipboard_get()
    assert clip.splitlines()[-2].endswith("first") and clip.splitlines()[-1].endswith("ERROR: second")
    assert not clip.endswith("\n")


def test_the_two_sections_are_cards(gui):
    from ui.widgets import Card

    cards = [w for w in gui.app.tab_queue.body.winfo_children() if isinstance(w, Card)]
    assert len(cards) == 2
    assert not [w for w in gui.app.tab_queue.body.winfo_children() if w.winfo_class() == "TLabelframe"]
