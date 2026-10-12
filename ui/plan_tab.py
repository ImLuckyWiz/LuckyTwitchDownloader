"""
Plan tab: cut points, live preview of the parts, and the clips table.

This is a mixin for ``App`` (luckytwitch_downloader.py): the methods were moved here verbatim from
``App`` so the file stays manageable, and they still use ``self`` as before. They expect the host to
provide: ``tab_plan``, ``var()``, ``vars``, ``build_options()``, ``build_filter()``, ``source``,
``clips`` and ``clips_loaded``. It creates ``cuts``, ``preview``, ``tree`` and ``clips_lbl``.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from luckytwitch_engine import EngineError, fmt_hms, insert_cut_point, make_chapters, make_plan
from ui.common import BG, BG2, ERR, FG, MONO_FONT, MUTED, OK, UI_FONT, bmp


class PlanTabMixin:
    def build_plan_tab(self):
        t = self.tab_plan.body
        t.columnconfigure(0, weight=1)
        t.rowconfigure(1, weight=1)

        # --- cut points --- #
        cutf = ttk.LabelFrame(t, text="Cut points", padding=8)
        cutf.grid(row=0, column=0, sticky="ew")
        cutf.columnconfigure(0, weight=1)
        self.cuts = tk.Text(cutf, height=3, bg=BG2, fg=FG, insertbackground=FG, relief="flat",
                            font=(MONO_FONT, 11), padx=6, pady=4, wrap="word")
        self.cuts.grid(row=0, column=0, sticky="ew")
        self.cuts.bind("<KeyRelease>", self.update_preview)
        ttk.Label(
            cutf,
            text="Boundaries in order, e.g.  0:00:00 - 0:30:00 - 1:30:00 - end   (end = end of the VOD).   "
                 "To skip a section use «;» or a new line:  0:00:00 - 0:30:00 ; 2:00:00 - end",
            style="Muted.TLabel", wraplength=940, justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 4))
        pf = ttk.Frame(cutf)
        pf.grid(row=2, column=0, sticky="ew")
        pf.columnconfigure(0, weight=1)
        self.preview = tk.Text(pf, height=5, bg=BG, fg=MUTED, relief="flat", state="disabled",
                               font=(UI_FONT, 10), wrap="word", cursor="arrow")
        self.preview.grid(row=0, column=0, sticky="ew")
        psb = ttk.Scrollbar(pf, orient="vertical", command=self.preview.yview)
        self.preview.configure(yscrollcommand=psb.set)
        psb.grid(row=0, column=1, sticky="ns")
        self.preview.tag_configure("ok", foreground=OK)
        self.preview.tag_configure("err", foreground=ERR)
        self.preview.tag_configure("muted", foreground=MUTED)

        # --- clips -> chapters --- #
        chf = ttk.LabelFrame(t, text="Clips → chapters (optional)", padding=8)
        chf.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        chf.columnconfigure(0, weight=1)
        chf.rowconfigure(1, weight=1)

        frow = ttk.Frame(chf)
        frow.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Checkbutton(frow, text="Add clips as chapters", variable=self.var("chapters"),
                        command=self.refresh_clips).pack(side="left")

        def num_field(label, name, width=6):
            ttk.Label(frow, text=label).pack(side="left", padx=(14, 4))
            sp = ttk.Spinbox(frow, textvariable=self.var(name), from_=0, to=1_000_000, width=width,
                             command=self.refresh_clips)
            sp.pack(side="left")
            sp.bind("<KeyRelease>", lambda e: self.refresh_clips())

        num_field("Min views", "min_views")
        num_field("Min duration (s)", "min_duration", 5)
        num_field("Top N by views (0 = all)", "top_n", 5)
        num_field("Lead-in (s)", "pad_before", 4)

        cols = ("at", "views", "dur", "title", "creator", "chap")
        self.tree = ttk.Treeview(chf, columns=cols, show="headings", selectmode="extended", height=6)
        for col, text, width, anchor in [
            ("at", "At", 80, "center"), ("views", "Views", 70, "center"), ("dur", "Dur", 60, "center"),
            ("title", "Title", 380, "w"), ("creator", "Creator", 140, "w"), ("chap", "Chapter", 70, "center"),
        ]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor=anchor, stretch=(col == "title"))
        sb = ttk.Scrollbar(chf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")
        self.tree.bind("<Double-1>", self.open_clip)
        self.clips_lbl = tk.StringVar()
        brow = ttk.Frame(chf)
        brow.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(brow, text="Split at selected clip", command=self.split_at_clip).pack(side="left")
        ttk.Button(brow, text="Download only selected clip", command=self.download_clips).pack(side="left", padx=(6, 0))
        ttk.Label(brow, textvariable=self.clips_lbl, style="Muted.TLabel").pack(side="left", padx=10)

        # --- add buttons --- #
        act = ttk.Frame(t)
        act.grid(row=2, column=0, sticky="e", pady=(8, 0))
        ttk.Button(act, text="Add to queue", command=lambda: self.add_to_queue(False)).pack(side="left")
        ttk.Button(act, text="Add & start", command=lambda: self.add_to_queue(True)).pack(side="left", padx=(6, 0))

    def set_preview(self, text: str, kind: str):
        """kind: ok | err | muted"""
        self.preview_kind = kind
        self.preview.config(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text, kind)
        self.preview.config(state="disabled")

    def update_preview(self, *_):
        text = self.cuts.get("1.0", "end").strip()
        if not text:
            self.set_preview("Write the cut points above (press «Get info» first so «end» works).", "muted")
            return
        dur = self.source.duration if self.source else None
        opts = self.build_options()
        try:
            plan = make_plan(text, dur, opts.strategy, opts.full_threshold)
        except EngineError as e:
            self.set_preview(f"⚠ {e}", "err")
            return
        lines = [f"Part {p.index}:  {fmt_hms(p.start)} → {fmt_hms(p.end)}   ({fmt_hms(p.duration)})" for p in plan.parts]
        if plan.duration:
            how = ("download the full VOD once, then split it" if plan.strategy == "full"
                   else "download only these parts")
            lines.append(f"→ {how}   (parts cover {plan.coverage * 100:.0f}% of the VOD)")
        self.set_preview("\n".join(lines), "ok")

    def refresh_clips(self, *_):
        self.tree.delete(*self.tree.get_children())
        flt = self.build_filter()
        chapters = make_chapters(self.clips, flt)
        included = {c.get("id") for ch in chapters for c in ch.clips}
        for i, c in enumerate(self.clips):
            off = c.get("vod_offset")
            mark = "?" if off is None else ("✓" if c.get("id") in included else "—")
            self.tree.insert("", "end", iid=str(i), values=(
                fmt_hms(off), c.get("view_count", 0), f"{round(c.get('duration', 0))}s",
                bmp(c.get("title", "")), bmp(c.get("creator_name", "")), mark))
        if not self.clips:
            msg = "No clips loaded (sign in with the Twitch API… button, optional)." if not self.clips_loaded else "This VOD has no clips."
        else:
            placed = sum(1 for c in self.clips if c.get("vod_offset") is not None)
            msg = f"{len(included)} of {len(self.clips)} clips pass the filter → {len(chapters)} chapters"
            if placed < len(self.clips):
                msg += f"  ({len(self.clips) - placed} can't be placed: no offset)"
            if not (self.vars["chapters"].get() or self.vars["premiere_xml"].get()):
                msg += "  [chapters are OFF]"
        self.clips_lbl.set(msg)

    def open_clip(self, _event):
        sel = self.tree.selection()
        if sel:
            webbrowser.open(self.clips[int(sel[0])].get("url", ""))

    def split_at_clip(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select a clip", "Select a clip in the table first.")
            return
        if len(sel) > 1:
            messagebox.showinfo("Select one clip", "Splitting works with a single clip: select just one.")
            return
        if not self.source:
            messagebox.showinfo("No VOD", "Press «Get info» first.")
            return
        off = self.clips[int(sel[0])].get("vod_offset")
        if off is None:
            messagebox.showinfo("No offset", "That clip has no position in the VOD.")
            return
        t = max(0, off - self.build_filter().pad_before)
        text = self.cuts.get("1.0", "end").strip() or "0:00:00 - end"
        try:
            new = insert_cut_point(text, t, self.source.duration)
        except EngineError as e:
            messagebox.showinfo("Can't split here", str(e))
            return
        self.cuts.delete("1.0", "end")
        self.cuts.insert("1.0", new)
        self.update_preview()
