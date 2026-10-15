"""Regression tests for the v1.11.0 final pass: Tab order of the Plan tab, and text that must wrap at the 900 px minimum.

Needs Tk and a display like the other GUI tests (xvfb-run -a python -m pytest); skipped when there is none.
"""

import pytest

tk = pytest.importorskip("tkinter")

from tkinter import ttk  # noqa: E402

from test_gui_plan_tab import gui  # noqa: E402,F401  (the fixture that opens the real window)


def descendants(w):
    for c in w.winfo_children():
        yield c
        yield from descendants(c)


def show(gui, tab, size=None):
    """The fixture keeps the window withdrawn, but Tab only visits widgets that are on screen: map it first."""
    gui.root.deiconify()
    if size:
        gui.root.geometry(size)
    gui.app.notebook.select(tab)
    gui.root.update()


def stops_in(gui, tab):
    """The widgets Tab visits inside ``tab``, in order (the other tabs are not viewable, so they are skipped)."""
    app = gui.app
    show(gui, tab)
    seq, w, seen = [], app.notebook.tk_focusNext(), set()
    while w is not None and str(w) not in seen and len(seq) < 600:
        seen.add(str(w))
        seq.append(w)
        w = w.tk_focusNext()
    return [w for w in seq if str(w).startswith(str(tab))]


def label_of(w):
    try:
        return str(w.cget("text"))
    except tk.TclError:
        return ""


def test_plan_tab_footer_buttons_are_the_last_stops_left_to_right(gui):
    stops = stops_in(gui, gui.app.tab_plan)
    assert len(stops) >= 10
    texts = [label_of(w) for w in stops]
    assert texts[-2:] == ["Add to queue", "Add & start"]
    assert texts.index("Add to queue") > texts.index("Download only selected clip")
    assert str(stops[0].winfo_class()) == "TButton" and label_of(stops[0]) == "−"  # starts with the timeline, not the footer


def test_plan_tab_shift_tab_is_the_exact_reverse(gui):
    stops = stops_in(gui, gui.app.tab_plan)
    assert len(stops) >= 10
    for before, w in zip(stops, stops[1:]):
        assert str(w.tk_focusPrev()) == str(before)


def test_plan_tab_footer_is_still_packed_at_the_bottom(gui):
    """Lifting the bar for the Tab order must not move it: «Add to queue» stays left of «Add & start», under the page."""
    app = gui.app
    show(gui, app.tab_plan)
    btns = {label_of(w): w for w in descendants(app.tab_plan.footer) if isinstance(w, ttk.Button)}
    assert btns["Add to queue"].winfo_x() < btns["Add & start"].winfo_x()
    assert app.tab_plan.footer.winfo_y() >= app.tab_plan.scroll.winfo_y() + app.tab_plan.scroll.winfo_height()


def test_tab_order_of_search_queue_and_options_has_nothing_decorative(gui):
    app = gui.app
    for tab in (app.tab_search, app.tab_queue, app.tab_options):
        stops = stops_in(gui, tab)
        assert stops, tab
        for w in stops:
            assert w.winfo_class() not in ("TLabel", "Label", "TFrame", "Frame", "TSeparator"), (tab, w)


def test_timeline_hint_wraps_to_the_width_of_the_strip(gui):
    app = gui.app
    show(gui, app.tab_plan, "900x560")
    hint = next(w for w in descendants(app.timeline)
                if isinstance(w, ttk.Label) and str(w.cget("textvariable")) == str(app.timeline.hint))
    wrap = int(hint.cget("wraplength"))
    assert 200 <= wrap <= app.timeline.winfo_width()  # it follows the width instead of running off the card


def test_search_type_list_is_never_squeezed_by_a_long_title(gui):
    app = gui.app
    show(gui, app.tab_search, "900x560")
    app.sv_title.set("A very long streamer name · 123 VODs · more available, long enough to want a whole line")
    gui.root.update()
    kind = next(w for w in descendants(app.tab_search)
                if isinstance(w, ttk.Combobox) and str(w.cget("textvariable")) == str(app.sv_type))
    assert kind.winfo_width() >= kind.winfo_reqwidth()  # the drop-down keeps its full width
    title = next(w for w in descendants(app.tab_search)
                 if isinstance(w, ttk.Label) and str(w.cget("textvariable")) == str(app.sv_title))
    assert int(title.cget("wraplength")) > 0  # the title wraps instead
