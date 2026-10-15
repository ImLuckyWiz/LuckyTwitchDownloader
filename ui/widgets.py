"""Small reusable widgets for the refined UI: ``Toggle`` (switch), ``Tooltip``, ``Card``, ``SettingRow``,
``SideNav`` (sidebar), ``Collapsible`` (Advanced area), ``TokenChips``, ``ScrollFrame``, ``ScrollPage`` (a scroll page with
a fixed footer bar) and ``EmptyState`` (a message over an empty list).

All of them are plain Tk / ttk with the palette of ``ui.common``; Pillow is used (when present) only to
draw the switch smoothly.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

from ui.common import ACCENT, ACCENT_HOVER, BG, BG2, BG3, BORDER, DISABLED, HOVER, MUTED, UI_FONT, WHITE

try:
    from PIL import Image, ImageDraw, ImageTk
except Exception:  # noqa: BLE001
    Image = ImageDraw = ImageTk = None


def _hex(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def _mix(a: str, b: str, t: float) -> tuple[int, int, int]:
    ra, rb = _hex(a), _hex(b)
    return tuple(round(x + (y - x) * t) for x, y in zip(ra, rb))


# --------------------------------------------------------------------------- #
# Toggle switch
# --------------------------------------------------------------------------- #
class Toggle(tk.Canvas):
    """An on/off switch bound to a BooleanVar/IntVar, like a Checkbutton but easier to read at a glance.

    Click or press Space to flip it. ``command`` runs after every change made by the user.
    ``bg`` must match the surface it sits on (BG or BG2 for cards).
    """

    W, H = 42, 24
    STEPS = 5  # animation frames

    def __init__(self, parent, variable: tk.Variable, command=None, bg: str = BG2, state: str = "normal"):
        scale = max(1.0, parent.winfo_fpixels("1i") / 96)
        self._pw, self._ph = round(self.W * scale), round(self.H * scale)
        super().__init__(parent, width=self._pw, height=self._ph, bg=bg, highlightthickness=0, borderwidth=0,
                         takefocus=1, cursor="hand2")
        self._bg = bg
        self.variable = variable
        self.command = command
        self._state = state
        self._hover = False
        self._pos = 1.0 if self._on() else 0.0  # 0 = off, 1 = on (animated)
        self._anim = None
        self._img_ref = None
        self._item = self.create_image(0, 0, anchor="nw")
        self._trace = variable.trace_add("write", lambda *_: self._sync())
        self.bind("<Button-1>", self._click)
        self.bind("<space>", self._click)
        self.bind("<Return>", self._click)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<FocusIn>", lambda e: self._draw())
        self.bind("<FocusOut>", lambda e: self._draw())
        self.bind("<Destroy>", self._on_destroy)
        self._draw()

    # ---- state ---- #
    def _on(self) -> bool:
        try:
            return bool(self.variable.get())
        except tk.TclError:
            return False

    def configure_state(self, state: str) -> None:
        self._state = state
        self.config(cursor="hand2" if state == "normal" else "arrow")
        self._draw()

    def _set_hover(self, v: bool) -> None:
        self._hover = v
        self._draw()

    def _click(self, _e=None):
        if self._state != "normal":
            return "break"
        self.focus_set()
        self.variable.set(0 if self._on() else 1) if not isinstance(self.variable, tk.BooleanVar) \
            else self.variable.set(not self._on())
        if self.command:
            self.command()
        return "break"

    def _sync(self) -> None:
        self._animate(1.0 if self._on() else 0.0)

    def _on_destroy(self, e) -> None:
        if e.widget is self:
            try:
                self.variable.trace_remove("write", self._trace)
            except Exception:  # noqa: BLE001
                pass
            if self._anim:
                try:
                    self._clock().after_cancel(self._anim)
                except Exception:  # noqa: BLE001
                    pass

    def _clock(self):
        """The window that owns the animation timer. Using the toplevel (not this widget) means destroying the switch
        never has to delete a timer command somebody else already cancelled (Tk's own 'after cancel' does that)."""
        return self.winfo_toplevel()

    def _animate(self, target: float) -> None:
        if self._anim:
            try:
                self._clock().after_cancel(self._anim)
            except Exception:  # noqa: BLE001
                pass
            self._anim = None
        step = 1.0 / self.STEPS

        def tick():
            if abs(self._pos - target) <= step / 2:
                self._pos = target
                self._anim = None
            else:
                self._pos += step if target > self._pos else -step
                self._anim = self._clock().after(14, tick)
            self._draw()

        tick()

    # ---- drawing ---- #
    def _draw(self) -> None:
        self.delete("fallback")
        t = self._pos
        dis = self._state != "normal"
        off_track, on_track = (BG3, "#4a3a78") if dis else (("#4a4d55" if self._hover else BG3), ACCENT_HOVER if self._hover else ACCENT)
        knob = DISABLED if dis else WHITE
        track = _mix(off_track, on_track, t)
        if Image is None:
            self._draw_fallback(track, knob, t)
            return
        ss = 4
        n_w, n_h = self._pw * ss, self._ph * ss
        im = Image.new("RGBA", (n_w, n_h), _hex(self._bg) + (255,))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, n_w - 1, n_h - 1], radius=n_h / 2, fill=track + (255,))
        pad = n_h * 0.17
        r = n_h / 2 - pad
        cx = pad + r + t * (n_w - 2 * (pad + r))
        d.ellipse([cx - r, n_h / 2 - r, cx + r, n_h / 2 + r], fill=_hex(knob) + (255,))
        if self.focus_get() is self and not dis:  # keyboard focus ring
            d.rounded_rectangle([ss, ss, n_w - 1 - ss, n_h - 1 - ss], radius=n_h / 2, outline=_hex(ACCENT_HOVER) + (255,),
                                width=ss)
        photo = ImageTk.PhotoImage(im.resize((self._pw, self._ph), Image.LANCZOS), master=self)
        self._img_ref = photo
        self.itemconfigure(self._item, image=photo)

    def _draw_fallback(self, track, knob, t) -> None:
        col = "#%02x%02x%02x" % track
        h, w = self._ph, self._pw
        self.create_oval(0, 0, h, h, fill=col, outline=col, tags="fallback")
        self.create_oval(w - h, 0, w, h, fill=col, outline=col, tags="fallback")
        self.create_rectangle(h / 2, 0, w - h / 2, h, fill=col, outline=col, tags="fallback")
        r = h / 2 - 4
        cx = 4 + r + t * (w - 8 - 2 * r)
        self.create_oval(cx - r, h / 2 - r, cx + r, h / 2 + r, fill=knob, outline=knob, tags="fallback")


# --------------------------------------------------------------------------- #
# Tooltip
# --------------------------------------------------------------------------- #
class Tooltip:
    """A small dark pop-up with explanatory text, shown after the pointer rests on ``widget``."""

    DELAY = 450

    def __init__(self, widget, text: str, wraplength: int = 380):
        self.widget, self.text, self.wraplength = widget, text, wraplength
        self._tip = None
        self._after = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self._after = self.widget.after(self.DELAY, self._show)

    def _cancel(self):
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except Exception:  # noqa: BLE001
                pass
            self._after = None

    def _show(self):
        self._after = None
        if self._tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            tip = tk.Toplevel(self.widget)
        except tk.TclError:
            return
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        frame = tk.Frame(tip, bg=BG3, highlightthickness=1, highlightbackground=BORDER)
        frame.pack()
        tk.Label(frame, text=self.text, bg=BG3, fg="#e6e6e6", justify="left", wraplength=self.wraplength,
                 font=(UI_FONT, 10), padx=10, pady=7).pack()
        tip.update_idletasks()
        sw = tip.winfo_screenwidth()
        x = min(x, sw - tip.winfo_reqwidth() - 8)
        tip.wm_geometry(f"+{max(0, x)}+{y}")
        self._tip = tip

    def _hide(self, _e=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


def info_icon(parent, text: str, bg: str = BG2) -> tk.Label:
    """A small «i» that shows ``text`` as a tooltip. Pack/grid it yourself."""
    lbl = tk.Label(parent, text="i", bg=bg, fg=MUTED, font=(UI_FONT, 8, "bold"), width=2, cursor="question_arrow",
                   highlightthickness=1, highlightbackground=BORDER, borderwidth=0)
    lbl.bind("<Enter>", lambda e: lbl.config(fg=WHITE, highlightbackground=ACCENT), add="+")
    lbl.bind("<Leave>", lambda e: lbl.config(fg=MUTED, highlightbackground=BORDER), add="+")
    Tooltip(lbl, text)
    return lbl


# --------------------------------------------------------------------------- #
# Card
# --------------------------------------------------------------------------- #
class Card(tk.Frame):
    """A rounded-looking surface (BG2 with a hairline border). Put children in ``.body``."""

    def __init__(self, parent, title: str | None = None, subtitle: str | None = None, padding: int = 16):
        super().__init__(parent, bg=BG2, highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER,
                         borderwidth=0)
        self.columnconfigure(0, weight=1)
        r = 0
        if title:
            head = ttk.Frame(self, style="Card.TFrame", padding=(padding, padding - 2, padding, 0))
            head.grid(row=r, column=0, sticky="ew")
            ttk.Label(head, text=title, style="CardHeading.TLabel").pack(anchor="w")
            if subtitle:
                ttk.Label(head, text=subtitle, style="CardMuted.TLabel", wraplength=640, justify="left").pack(
                    anchor="w", pady=(2, 0))
            r += 1
        self.body = ttk.Frame(self, style="Card.TFrame", padding=(padding, 8, padding, padding - 4))
        self.body.grid(row=r, column=0, sticky="nsew")
        self.body.columnconfigure(0, weight=1)
        self._rows = 0

    def add_row(self, *a, **kw) -> "SettingRow":
        row = SettingRow(self.body, *a, **kw)
        row.grid(row=self._rows, column=0, sticky="ew")  # the row draws its own divider
        self._rows += 1
        return row


# --------------------------------------------------------------------------- #
# Setting row: bold name + muted one-liner on the left, the control on the right
# --------------------------------------------------------------------------- #
class SettingRow(ttk.Frame):
    """``[ Name          ]                   [ control ]``
       ``[ one-line hint ]``   (and an optional ⓘ tooltip with the long explanation)

    Build the control with ``row.control`` as its parent (a Card.TFrame on the right), e.g.
    ``Toggle(row.control, var)``. ``row.below`` is a full-width area under the text for wide controls
    (file name templates and the like); ``row.divider`` can be turned off for the last row of a card.
    """

    def __init__(self, parent, title: str, hint: str = "", info: str = "", divider: bool = True):
        super().__init__(parent, style="Card.TFrame", padding=(0, 10, 0, 10))
        self.columnconfigure(0, weight=1)
        text = ttk.Frame(self, style="Card.TFrame")
        text.grid(row=0, column=0, sticky="w")
        top = ttk.Frame(text, style="Card.TFrame")
        top.pack(anchor="w")
        ttk.Label(top, text=title, style="Card.TLabel", font=(UI_FONT, 10, "bold")).pack(side="left")
        if info:
            info_icon(top, info).pack(side="left", padx=(8, 0))
        self.hint_label = None
        if hint:
            self.hint_label = ttk.Label(text, text=hint, style="CardMuted.TLabel", wraplength=470, justify="left")
            self.hint_label.pack(anchor="w", pady=(2, 0))
        self.control = ttk.Frame(self, style="Card.TFrame")
        self.control.grid(row=0, column=1, sticky="e", padx=(16, 0))
        self.below = ttk.Frame(self, style="Card.TFrame")
        self.below.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.below.columnconfigure(0, weight=1)
        self._divider = None
        if divider:
            self._divider = tk.Frame(self, bg=BORDER, height=1)
            self._divider.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))


# --------------------------------------------------------------------------- #
# Scrollable page
# --------------------------------------------------------------------------- #
class ScrollFrame(ttk.Frame):
    """
    A tab page that scrolls vertically when the window is too short for its content.
    Put the widgets in `.body`. When the window is tall enough `.body` stretches to fill it (so rows
    with a grid weight still grow); otherwise a scrollbar appears and the mouse wheel scrolls.
    """

    def __init__(self, parent, padding: int = 8):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, borderwidth=0, yscrollincrement=20)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas, padding=padding)
        self._win = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._fit)
        self.canvas.bind("<Configure>", self._fit)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):  # Windows/macOS, Linux up/down
            self.canvas.bind_all(seq, self._on_wheel, add="+")

    def refit(self) -> None:
        """Recompute the scroll area now. Call it after showing / hiding things inside ``.body``: the body keeps
        the size it was given, so Tk sends no <Configure> when only its content changes."""
        self.update_idletasks()
        self._fit()

    def _fit(self, _event=None):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw <= 1:
            return  # not laid out yet
        height = max(ch, self.body.winfo_reqheight())
        self.canvas.itemconfigure(self._win, width=cw, height=height)
        self.canvas.configure(scrollregion=(0, 0, cw, height))

    def _on_wheel(self, event):
        try:
            w = self.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):  # Tk quirk with combobox pop-downs
            return
        p = w
        while p is not None and p is not self:
            p = p.master
        if p is None:
            return  # the pointer is not over this page
        if isinstance(w, (ttk.Treeview, tk.Text, tk.Listbox, ttk.Combobox, ttk.Spinbox)):
            return  # these handle the wheel themselves
        if self.body.winfo_reqheight() <= self.canvas.winfo_height():
            return  # everything fits: nothing to scroll
        if getattr(event, "num", None) == 4:
            units = -3
        elif getattr(event, "num", None) == 5:
            units = 3
        else:
            delta = int(event.delta)
            if sys.platform == "darwin":
                units = -delta
            else:
                units = -3 * (delta // 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        self.canvas.yview_scroll(units, "units")


class ScrollPage(ttk.Frame):
    """A ``ScrollFrame`` with a fixed bar underneath that never scrolls away.

    Content goes in ``.body`` (as with ScrollFrame); the always-visible bar is ``.footer``. ``refit()`` works too.
    """

    def __init__(self, parent, padding: int = 8):
        super().__init__(parent)
        self.footer_line = tk.Frame(self, bg=BORDER, height=1)
        self.footer = ttk.Frame(self, padding=(12, 10, 12, 10))
        self.footer.pack(side="bottom", fill="x")
        self.footer_line.pack(side="bottom", fill="x")
        self.scroll = ScrollFrame(self, padding=padding)
        self.scroll.pack(side="top", fill="both", expand=True)
        self.body = self.scroll.body
        self.canvas = self.scroll.canvas
        # Tab follows the stacking order: the bar was created first, so lift it to be the LAST stop (after the page)
        self.footer_line.lift()
        self.footer.lift()

    def refit(self) -> None:
        self.scroll.refit()


def wrap_to(label: ttk.Label, container, margin: int = 0, minimum: int = 200) -> None:
    """Keep ``label`` wrapped to the current width of ``container`` (minus ``margin``), so hint text follows resizes."""

    def fit(event=None):
        w = (event.width if event is not None else container.winfo_width()) - margin
        if w > 1:
            label.configure(wraplength=max(minimum, w))

    container.bind("<Configure>", fit, add="+")


# --------------------------------------------------------------------------- #
# Sidebar navigation (one section visible at a time)
# --------------------------------------------------------------------------- #
class SideNav(ttk.Frame):
    """A vertical list of entries; the selected one is tinted purple. ``command(key)`` runs on every change.

    Entries are real buttons: Tab reaches them, Space/Enter picks one, Up/Down move the selection.
    """

    def __init__(self, parent, items: list[tuple[str, str]], command, width: int = 17):
        super().__init__(parent, style="Card.TFrame", padding=8)
        self.command = command
        self.keys = [k for k, _ in items]
        self.buttons: dict[str, ttk.Button] = {}
        self.current: str | None = None
        for key, label in items:
            b = ttk.Button(self, text=label, style="Nav.TButton", width=width, command=lambda k=key: self.select(k))
            b.pack(fill="x", pady=1)
            b.bind("<Down>", lambda e, k=key: self._step(k, 1))
            b.bind("<Up>", lambda e, k=key: self._step(k, -1))
            self.buttons[key] = b

    def _step(self, key: str, delta: int):
        i = self.keys.index(key) + delta
        if 0 <= i < len(self.keys):
            self.select(self.keys[i])
            self.buttons[self.keys[i]].focus_set()
        return "break"

    def select(self, key: str) -> None:
        if key not in self.buttons:
            return
        self.current = key
        for k, b in self.buttons.items():
            b.configure(style="NavSel.TButton" if k == key else "Nav.TButton")
        self.command(key)


# --------------------------------------------------------------------------- #
# «Advanced» area: collapsed until the header is clicked
# --------------------------------------------------------------------------- #
class Collapsible(ttk.Frame):
    """A header button («▸ Advanced») that shows / hides ``.body``. Rows go in with ``add_row`` like a Card."""

    def __init__(self, parent, title: str = "Advanced", hint: str = "", opened: bool = False, on_change=None):
        super().__init__(parent, style="Card.TFrame")
        self.columnconfigure(0, weight=1)
        self.title, self.hint = title, hint
        self.opened = opened
        self.on_change = on_change  # called after it opens / closes (the page may need to re-fit its scroll area)
        self.header = ttk.Button(self, style="CardGhost.TButton", command=self.toggle)
        self.header.grid(row=0, column=0, sticky="w", pady=(6, 0))
        self.body = ttk.Frame(self, style="Card.TFrame")
        self.body.columnconfigure(0, weight=1)
        self._rows = 0
        self._apply()

    def add_row(self, *a, **kw) -> "SettingRow":
        row = SettingRow(self.body, *a, **kw)
        row.grid(row=self._rows, column=0, sticky="ew")
        self._rows += 1
        return row

    def toggle(self) -> None:
        self.opened = not self.opened
        self._apply()
        if self.on_change:
            self.on_change()

    def _apply(self) -> None:
        arrow = "\u25be" if self.opened else "\u25b8"
        self.header.configure(text=f"{arrow}  {self.title}" + (f"   \u00b7   {self.hint}" if self.hint else ""))
        if self.opened:
            self.body.grid(row=1, column=0, sticky="ew")
        else:
            self.body.grid_remove()


# --------------------------------------------------------------------------- #
# Clickable {token} chips for template fields
# --------------------------------------------------------------------------- #
class TokenChips(ttk.Frame):
    """A row of small buttons; clicking one inserts ``{token}`` at the cursor of ``entry``."""

    def __init__(self, parent, entry: ttk.Entry, tokens: list[str], per_row: int = 6):
        super().__init__(parent, style="Card.TFrame")
        self.entry = entry
        self.chips: list[ttk.Button] = []
        for i, tok in enumerate(tokens):
            b = ttk.Button(self, text="{" + tok + "}", style="Chip.TButton", command=lambda t=tok: self.insert(t))
            b.grid(row=i // per_row, column=i % per_row, sticky="w", padx=(0, 6), pady=(0, 4))
            self.chips.append(b)

    def insert(self, token: str) -> None:
        if str(self.entry.cget("state")) == "disabled":
            return
        try:
            if self.entry.selection_present():  # typing over a selection replaces it, like in any text field
                self.entry.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.entry.insert("insert", "{" + token + "}")
        self.entry.focus_set()

    def set_enabled(self, on: bool) -> None:
        for b in self.chips:
            b.state(["!disabled"] if on else ["disabled"])


# --------------------------------------------------------------------------- #
# Empty state: a friendly message laid over an empty list
# --------------------------------------------------------------------------- #
class EmptyState(tk.Frame):
    """A message centred over a ``Treeview`` (or any list) while it has nothing to show.

    ``show(title, text, button=("Sign in…", command))`` fills and shows it, ``hide()`` removes it. It sits on top of
    the list, below ``top`` pixels (so the column headings stay visible). Use ``compact=True`` for narrow lists.
    """

    def __init__(self, target, top: int = 0, compact: bool = False):
        super().__init__(target.master, bg=BG2, borderwidth=0, highlightthickness=0)
        self._target, self._top = target, top
        self._wrap = 190 if compact else 380
        self._inner = tk.Frame(self, bg=BG2)
        self._inner.place(relx=0.5, rely=0.42, anchor="center")
        self.shown = False

    def show(self, title: str = "", text: str = "", button: tuple[str, object] | None = None) -> None:
        for w in self._inner.winfo_children():
            w.destroy()
        if title:
            tk.Label(self._inner, text=title, bg=BG2, fg="#e6e6e6", font=(UI_FONT, 11, "bold"),
                     wraplength=self._wrap, justify="center").pack()
        if text:
            tk.Label(self._inner, text=text, bg=BG2, fg=MUTED, font=(UI_FONT, 10), wraplength=self._wrap,
                     justify="center").pack(pady=(4 if title else 0, 0))
        if button:
            label, command = button
            ttk.Button(self._inner, text=label, style="Accent.TButton", command=command).pack(pady=(12, 0))
        if not self.shown:
            self.place(in_=self._target, x=0, y=self._top, relwidth=1, relheight=1, height=-self._top)
            self.shown = True
        self.lift()

    def hide(self) -> None:
        if self.shown:
            self.place_forget()
            self.shown = False
