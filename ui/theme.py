"""The look of the app: ttk styles (flat dark theme with the purple accent) and the Windows dark title bar.

``apply_dark_theme(root)`` is the one entry point. Styles other modules can use:

  ``Accent.TButton``  filled purple button (the main action of a screen)
  ``Ghost.TButton``   no background until hovered (small secondary actions)
  ``Muted.TLabel``    grey helper text
  ``Nav.TButton`` / ``NavSel.TButton``  sidebar entries (normal / selected); ``CardGhost.TButton`` the «Advanced» header;
                      ``Chip.TButton`` the small {token} buttons next to template fields
  ``Card.*``          Frame / Label / CardMuted.Label / Checkbutton / Entry / Combobox / Spinbox on a card (BG2)
  ``Title.TLabel`` and ``Heading.TLabel``  bigger text for page and section titles
"""

from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from ui.common import (
    ACCENT, ACCENT_DIM, ACCENT_HOVER, ACCENT_PRESS, BG, BG2, BG3, BORDER, DISABLED, FG, HOVER, MUTED, PRESSED, UI_FONT, WHITE,
)

try:
    from PIL import Image, ImageDraw, ImageTk
except Exception:  # noqa: BLE001  (Pillow is optional: checkboxes then keep Tk's own indicator)
    Image = ImageDraw = ImageTk = None


def dark_titlebar(window):
    if sys.platform != "win32":
        return
    try:
        import ctypes

        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        for attr in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# Anti-aliased checkbox images (drawn big with Pillow, shrunk)
# --------------------------------------------------------------------------- #
def _checkbox_images(root, px: int) -> dict:
    """The check box in its states: off / on, plain / hovered / disabled."""
    ss = 8
    n = px * ss

    def draw(fill, outline, tick):
        im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        pad = ss * 1.2
        box = [pad, pad, n - pad, n - pad]
        d.rounded_rectangle(box, radius=ss * 4.2, fill=fill, outline=outline, width=max(1, round(ss * 1.5)))
        if tick:
            pts = [(n * 0.28, n * 0.53), (n * 0.43, n * 0.68), (n * 0.73, n * 0.34)]
            w = round(n * 0.12)
            d.line(pts, fill=tick, width=w, joint="curve")
            for x, y in (pts[0], pts[-1]):  # round caps
                d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=tick)
        small = im.resize((px, px), Image.LANCZOS)
        gap = round(px * 0.45)  # transparent margin on the right: space between the box and its label
        wide = Image.new("RGBA", (px + gap, px), (0, 0, 0, 0))
        wide.paste(small, (0, 0))
        return ImageTk.PhotoImage(wide, master=root)

    return {
        "off": draw(BG, "#6b6e77", None),
        "off_hover": draw(BG, ACCENT_HOVER, None),
        "off_dis": draw(BG2, BG3, None),
        "on": draw(ACCENT, None, WHITE),
        "on_hover": draw(ACCENT_HOVER, None, WHITE),
        "on_dis": draw(BG3, None, DISABLED),
    }


def apply_dark_theme(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=BG)

    # fonts: one family everywhere, a touch bigger than Tk's default 9
    for name, size in (("TkDefaultFont", 10), ("TkTextFont", 10), ("TkMenuFont", 10), ("TkHeadingFont", 10)):
        try:
            tkfont.nametofont(name).configure(family=UI_FONT, size=size)
        except tk.TclError:
            pass

    style.configure(".", background=BG, foreground=FG, fieldbackground=BG2, bordercolor=BORDER,
                    lightcolor=BG, darkcolor=BG, troughcolor=BG2, focuscolor=BG, font=("TkDefaultFont",))
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure("Title.TLabel", background=BG, foreground=FG, font=(UI_FONT, 15, "bold"))
    style.configure("Heading.TLabel", background=BG, foreground=FG, font=(UI_FONT, 11, "bold"))
    style.configure("TLabelframe", background=BG, bordercolor=BORDER, relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=(UI_FONT, 10, "bold"))
    style.configure("TSeparator", background=BORDER)

    # --- buttons --- #
    style.configure("TButton", background=BG3, foreground=FG, padding=(14, 7), borderwidth=0, relief="flat",
                    bordercolor=BG3, lightcolor=BG3, darkcolor=BG3, focusthickness=0)
    style.map("TButton",
              background=[("disabled", BG2), ("pressed", PRESSED), ("active", HOVER)],
              bordercolor=[("disabled", BG2), ("pressed", PRESSED), ("active", HOVER)],
              lightcolor=[("disabled", BG2), ("pressed", PRESSED), ("active", HOVER)],
              darkcolor=[("disabled", BG2), ("pressed", PRESSED), ("active", HOVER)],
              foreground=[("disabled", DISABLED)])
    style.configure("Accent.TButton", background=ACCENT, foreground=WHITE, font=(UI_FONT, 10, "bold"),
                    bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT, padding=(16, 7))
    style.map("Accent.TButton",
              background=[("disabled", BG3), ("pressed", ACCENT_PRESS), ("active", ACCENT_HOVER)],
              bordercolor=[("disabled", BG3), ("pressed", ACCENT_PRESS), ("active", ACCENT_HOVER)],
              lightcolor=[("disabled", BG3), ("pressed", ACCENT_PRESS), ("active", ACCENT_HOVER)],
              darkcolor=[("disabled", BG3), ("pressed", ACCENT_PRESS), ("active", ACCENT_HOVER)],
              foreground=[("disabled", DISABLED)])
    style.configure("Ghost.TButton", background=BG, foreground=MUTED, bordercolor=BG, lightcolor=BG, darkcolor=BG,
                    padding=(10, 5))
    style.map("Ghost.TButton",
              background=[("disabled", BG), ("pressed", PRESSED), ("active", BG3)],
              bordercolor=[("disabled", BG), ("pressed", PRESSED), ("active", BG3)],
              lightcolor=[("disabled", BG), ("pressed", PRESSED), ("active", BG3)],
              darkcolor=[("disabled", BG), ("pressed", PRESSED), ("active", BG3)],
              foreground=[("disabled", DISABLED), ("active", FG)])

    # --- fields: a hairline that turns purple on focus --- #
    field = dict(fieldbackground=BG2, foreground=FG, insertcolor=FG, bordercolor=BORDER, lightcolor=BORDER,
                 darkcolor=BORDER, padding=(6, 5))
    focus_map = dict(bordercolor=[("focus", ACCENT), ("hover", HOVER)], lightcolor=[("focus", ACCENT)],
                     darkcolor=[("focus", ACCENT)])
    style.configure("TEntry", **field)
    style.map("TEntry", **focus_map, fieldbackground=[("disabled", BG)], foreground=[("disabled", DISABLED)])
    style.configure("TSpinbox", **field, arrowcolor=MUTED, background=BG3, arrowsize=12)
    style.map("TSpinbox", **focus_map, background=[("active", HOVER)], arrowcolor=[("active", FG)])
    style.configure("TCombobox", **field, arrowcolor=MUTED, background=BG3, selectbackground=BG2,
                    selectforeground=FG, arrowsize=14)
    style.map("TCombobox", **focus_map, fieldbackground=[("readonly", BG2)], foreground=[("readonly", FG)],
              background=[("active", HOVER)], arrowcolor=[("active", FG)])
    root.option_add("*TCombobox*Listbox.background", BG2)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", WHITE)
    root.option_add("*TCombobox*Listbox.borderWidth", 0)
    root.option_add("*TCombobox*Listbox.highlightThickness", 0)
    root.option_add("*TCombobox*Listbox.font", (UI_FONT, 10))

    # plain Tk text boxes: hairline border, purple while focused (Tk's default is a white ring)
    root.option_add("*Text.highlightThickness", 1)
    root.option_add("*Text.highlightBackground", BORDER)
    root.option_add("*Text.highlightColor", ACCENT)
    root.option_add("*Text.borderWidth", 0)

    # --- cards: same widgets on the BG2 surface --- #
    style.configure("Card.TFrame", background=BG2)
    style.configure("Card.TLabel", background=BG2, foreground=FG)
    style.configure("CardMuted.TLabel", background=BG2, foreground=MUTED)
    style.configure("CardHeading.TLabel", background=BG2, foreground=FG, font=(UI_FONT, 11, "bold"))
    for kind in ("TEntry", "TSpinbox", "TCombobox"):
        style.configure("Card." + kind, fieldbackground=BG)
    style.map("Card.TEntry", fieldbackground=[("disabled", BG2)])
    style.map("Card.TCombobox", fieldbackground=[("readonly", BG)])
    style.configure("Card.TCheckbutton", background=BG2)
    style.map("Card.TCheckbutton", background=[("active", BG2)])
    style.configure("Card.TButton", background=BG3)

    # sidebar entries, the «Advanced» header and the {token} chips
    def flat_button(name, bg, fg, hover_bg, hover_fg, font, padding, anchor="center"):
        style.configure(name, background=bg, foreground=fg, bordercolor=bg, lightcolor=bg, darkcolor=bg,
                        font=font, padding=padding, anchor=anchor, borderwidth=0, focusthickness=0)
        style.map(name, background=[("pressed", PRESSED), ("active", hover_bg)],
                  bordercolor=[("pressed", PRESSED), ("active", hover_bg)],
                  lightcolor=[("pressed", PRESSED), ("active", hover_bg)],
                  darkcolor=[("pressed", PRESSED), ("active", hover_bg)],
                  foreground=[("active", hover_fg)])

    flat_button("Nav.TButton", BG2, MUTED, BG3, FG, (UI_FONT, 10), (14, 9), "w")
    flat_button("NavSel.TButton", ACCENT_DIM, WHITE, ACCENT_DIM, WHITE, (UI_FONT, 10, "bold"), (14, 9), "w")
    flat_button("CardGhost.TButton", BG2, MUTED, BG3, FG, (UI_FONT, 10, "bold"), (8, 5), "w")
    flat_button("Chip.TButton", BG3, FG, HOVER, WHITE, (UI_FONT, 9), (8, 2))
    style.map("Chip.TButton", foreground=[("disabled", DISABLED), ("active", WHITE)],
              background=[("disabled", BG2), ("pressed", ACCENT_PRESS), ("active", HOVER)])

    # --- check boxes (rounded, purple when on) --- #
    style.configure("TCheckbutton", background=BG, foreground=FG, padding=(2, 3))
    style.map("TCheckbutton", background=[("active", BG)], foreground=[("disabled", DISABLED)])
    if Image is not None:
        try:
            px = max(16, round(18 * root.winfo_fpixels("1i") / 96))
            imgs = _checkbox_images(root, px)
            root._lt_theme_images = imgs  # keep references: Tk drops unreferenced images
            style.element_create(
                "Lt.indicator", "image", str(imgs["off"]),
                ("disabled", "selected", str(imgs["on_dis"])),
                ("disabled", str(imgs["off_dis"])),
                ("selected", "active", str(imgs["on_hover"])),
                ("selected", str(imgs["on"])),
                ("active", str(imgs["off_hover"])),
                sticky="w")
            style.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("Lt.indicator", {"side": "left", "sticky": ""}),
                ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
                    ("Checkbutton.label", {"sticky": "nswe"})]}),
            ]})])
        except tk.TclError:
            style.map("TCheckbutton", indicatorcolor=[("selected", ACCENT), ("!selected", BG2)])
    else:
        style.map("TCheckbutton", indicatorcolor=[("selected", ACCENT), ("!selected", BG2)])

    # --- notebook tabs --- #
    style.configure("TNotebook", background=BG, bordercolor=BORDER, lightcolor=BG, darkcolor=BG,
                    tabmargins=(0, 6, 0, 0), borderwidth=0)
    style.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(20, 8), borderwidth=0,
                    bordercolor=BG, lightcolor=BG, darkcolor=BG, font=(UI_FONT, 10, "bold"))
    style.map("TNotebook.Tab",
              background=[("selected", ACCENT), ("active", BG3)],
              bordercolor=[("selected", ACCENT)], lightcolor=[("selected", ACCENT)],
              darkcolor=[("selected", ACCENT)],
              foreground=[("selected", WHITE), ("active", FG)],
              expand=[("selected", (0, 0, 0, 0))])

    # --- lists and tables --- #
    style.configure("Treeview", background=BG2, fieldbackground=BG2, foreground=FG, rowheight=28, borderwidth=0,
                    relief="flat", bordercolor=BG2, lightcolor=BG2, darkcolor=BG2)
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])  # no outer frame
    style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", WHITE)])
    style.configure("Treeview.Heading", background=BG3, foreground=FG, relief="flat", padding=(8, 7),
                    font=(UI_FONT, 10, "bold"), borderwidth=0, bordercolor=BG3, lightcolor=BG3, darkcolor=BG3)
    style.map("Treeview.Heading", background=[("active", HOVER)])

    # --- slim scrollbars without arrows --- #
    for orient in ("Vertical", "Horizontal"):
        name = f"{orient}.TScrollbar"
        side = "ns" if orient == "Vertical" else "ew"
        style.layout(name, [(f"{orient}.Scrollbar.trough", {"sticky": side, "children": [
            (f"{orient}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        style.configure(name, background=BG3, troughcolor=BG, bordercolor=BG, lightcolor=BG3, darkcolor=BG3,
                        gripcount=0, width=11, arrowsize=11, relief="flat")
        style.map(name, background=[("pressed", PRESSED), ("active", HOVER)],
                  lightcolor=[("pressed", PRESSED), ("active", HOVER)],
                  darkcolor=[("pressed", PRESSED), ("active", HOVER)])

    # --- progress bar --- #
    style.configure("Horizontal.TProgressbar", troughcolor=BG2, background=ACCENT, bordercolor=BG2,
                    lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)

    dark_titlebar(root)
