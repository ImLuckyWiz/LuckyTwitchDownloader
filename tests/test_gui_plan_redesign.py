"""Plan tab after the redesign: cards, the chapters switch, the bar that stays visible, wrapping hints.

Needs Tk and a display like the other GUI tests (xvfb-run -a python -m pytest); skipped when there is none.
"""

import pytest

tk = pytest.importorskip("tkinter")

from tkinter import ttk  # noqa: E402

import luckytwitch_engine as eng  # noqa: E402
from test_gui_plan_tab import SOURCE, gui  # noqa: E402,F401  (the fixture that opens the real window)
from ui.widgets import Card, ScrollPage, Toggle, wrap_to  # noqa: E402


def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)


def test_the_plan_tab_is_a_scroll_page_with_a_footer(gui):
    page = gui.app.tab_plan
    assert isinstance(page, ScrollPage)
    assert page.body is page.scroll.body
    texts = {w.cget("text") for w in walk(page.footer) if w.winfo_class() == "TButton"}
    assert texts == {"Add to queue", "Add & start"}


def test_the_footer_stays_visible_when_the_page_scrolls(gui):
    gui.root.geometry("1000x500")  # short window: the content does not fit
    gui.app.notebook.select(gui.app.tab_plan)
    gui.root.update()
    page = gui.app.tab_plan
    assert page.body.winfo_reqheight() > page.canvas.winfo_height()  # so it really scrolls
    page.canvas.yview_moveto(1.0)
    gui.root.update()
    btn = next(w for w in walk(page.footer) if w.winfo_class() == "TButton")
    # (the test window is withdrawn, so compare positions instead of asking if it is viewable)
    assert page.footer.winfo_y() >= page.scroll.winfo_y() + page.scroll.winfo_height()  # under the scrolling part
    assert page.footer.winfo_y() + btn.winfo_y() + btn.winfo_height() <= page.winfo_height()  # inside the page


def test_the_three_sections_are_cards(gui):
    cards = [w for w in gui.app.tab_plan.body.winfo_children() if isinstance(w, Card)]
    assert len(cards) == 3
    assert not [w for w in walk(gui.app.tab_plan) if w.winfo_class() == "TLabelframe"]


def test_the_chapters_switch_drives_the_clips_table(gui):
    gui.load_vod()
    gui.load_clips()
    # (the timeline has a switch of its own, «Show muted»: pick the one that belongs to the chapters setting)
    toggle = next(w for w in walk(gui.app.tab_plan.body)
                  if isinstance(w, Toggle) and str(w.variable) == str(gui.app.vars["chapters"]))
    assert "[chapters are OFF]" in gui.app.clips_lbl.get()
    toggle._click()  # the user flips it: the table is refreshed through the switch's command
    assert gui.app.vars["chapters"].get() is True
    assert "[chapters are OFF]" not in gui.app.clips_lbl.get()


def test_the_footer_summary_follows_the_cut_points(gui):
    gui.load_vod()
    gui.set_cuts("0:00 - 30:00 - 1:30:00 - end")
    gui.app.update_preview()
    assert gui.app.plan_summary.get() == "3 parts · 2:00:00 in total"
    gui.set_cuts("0:00 - 30:00 ; 1:00:00 - end")
    gui.app.update_preview()
    assert gui.app.plan_summary.get() == "2 parts · 1:30:00 in total"
    gui.set_cuts("0:00 - 0:00")
    gui.app.update_preview()
    assert gui.preview()[1] == "err"
    assert gui.app.plan_summary.get() == "Fix the cut points to add this VOD"
    gui.set_cuts("")
    gui.app.update_preview()
    assert gui.app.plan_summary.get() == ""


def test_the_summary_is_red_only_while_the_cuts_are_wrong(gui):
    from ui.common import ERR, MUTED

    gui.set_cuts("nonsense")
    gui.app.update_preview()
    assert str(gui.app.plan_summary_lbl.cget("foreground")) == ERR
    gui.set_cuts("0:00 - 30:00")
    gui.load_vod()
    gui.app.update_preview()
    assert str(gui.app.plan_summary_lbl.cget("foreground")) == MUTED


def test_table_headings_line_up_with_their_columns(gui):
    tree = gui.app.tree
    for col in tree["columns"]:
        assert tree.heading(col, "anchor") == tree.column(col, "anchor")


def test_the_chapter_column_is_wide_enough_for_its_title(gui):
    import tkinter.font as tkfont

    tree = gui.app.tree
    font = tkfont.Font(font=ttk.Style().lookup("Treeview.Heading", "font") or "TkDefaultFont")
    assert int(tree.column("chap", "width")) >= font.measure(tree.heading("chap", "text")) + 16


def test_hints_wrap_to_the_width_of_their_card():
    root = tk.Tk()
    try:
        frame = ttk.Frame(root, padding=0)
        frame.pack(fill="both", expand=True)
        lbl = ttk.Label(frame, text="word " * 200)
        lbl.pack(anchor="w")
        wrap_to(lbl, frame, margin=20)
        root.geometry("500x300")
        root.update()
        assert int(lbl.cget("wraplength")) == frame.winfo_width() - 20
        root.geometry("300x300")
        root.update()
        assert int(lbl.cget("wraplength")) == frame.winfo_width() - 20
        assert lbl.winfo_width() <= frame.winfo_width()
    finally:
        root.destroy()


def test_nothing_on_the_plan_tab_is_wider_than_the_page(gui):
    gui.root.geometry("900x700")
    gui.load_vod()
    gui.set_cuts("0:00:00 - 0:30:00 - end")
    gui.app.notebook.select(gui.app.tab_plan)
    gui.app.update_preview()
    for _ in range(5):
        gui.root.update()
    page = gui.app.tab_plan
    limit = page.canvas.winfo_rootx() + page.canvas.winfo_width()
    for w in walk(page.body):
        if w.winfo_viewable() and w.winfo_class() in ("Frame", "TFrame", "Text", "Treeview", "TLabel"):
            assert w.winfo_rootx() + w.winfo_width() <= limit + 1, (str(w), w.winfo_class())
