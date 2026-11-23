"""
EZ Video Maker - friendly dialogs: trim, split, crop, text, custom size.
Each one shows a picture so people can SEE what they are choosing.
"""

import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from . import media
from .model import TEXT_STYLES, TEXT_SIZES, TEXT_COLORS
from .preview import fmt_time
from .theme import (FONT, CARD, BG, TEXT, TEXT_MUTED, BLUE, BLUE_DARK, ORANGE,
                    BigButton, GhostButton, hscale, label)


class _Dialog(tk.Toplevel):
    def __init__(self, parent, title, width=720):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=CARD)
        self.resizable(False, False)
        self.result = None
        self.transient(parent.winfo_toplevel())
        self._dialog_width = width
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda e: self.cancel())

    def _buttons(self, ok_text="OK"):
        row = tk.Frame(self, bg=CARD)
        row.pack(pady=(6, 14))
        BigButton(row, ok_text, command=self.ok, color=ORANGE, font_size=12,
                  pady=8).pack(side="left", padx=8)
        GhostButton(row, "Cancel", command=self.cancel).pack(side="left",
                                                             padx=8)

    def show(self):
        self.update_idletasks()
        p = self.master.winfo_toplevel()
        x = p.winfo_rootx() + (p.winfo_width() - self.winfo_width()) // 2
        y = p.winfo_rooty() + (p.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()
        self.wait_window()
        return self.result

    def ok(self):
        self.result = True
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


class _FrameBox(tk.Label):
    """Shows a frame of a clip at a time."""

    def __init__(self, parent, path, w=300, h=180):
        super().__init__(parent, bg="#0A0E14", width=w, height=h)
        self.pack_propagate(False)
        self.path, self.w, self.h = path, w, h
        self._photo = None
        self._pending = None

    def show(self, t):
        img = media.grab_frame(self.path, t, self.w) \
            if not media.is_image(self.path) else media.load_photo(
                self.path, self.w)
        if img is None:
            self.config(image="", text="no picture", fg=TEXT_MUTED)
            return
        img = media.fit_into(img, self.w, self.h)
        self._photo = ImageTk.PhotoImage(img)
        self.config(image=self._photo, text="")

    def show_later(self, t, delay=120):
        if self._pending:
            self.after_cancel(self._pending)
        self._pending = self.after(delay, lambda: self.show(t))


class TrimDialog(_Dialog):
    """Pick where a clip starts and ends, with pictures of both."""

    def __init__(self, parent, clip):
        super().__init__(parent, "Trim clip - choose start and end")
        self.clip = clip
        total = clip.source_duration or clip.out_point
        tk.Label(self, text=f"✂  Trim: {clip.name}", bg=CARD, fg=BLUE_DARK,
                 font=(FONT, 14, "bold")).pack(pady=(14, 2))
        tk.Label(self, text="Drag the sliders. The pictures show the first "
                            "and last moment that will be kept.",
                 bg=CARD, fg=TEXT_MUTED, font=(FONT, 10)).pack()
        pics = tk.Frame(self, bg=CARD)
        pics.pack(pady=8, padx=16)
        left = tk.Frame(pics, bg=CARD)
        left.pack(side="left", padx=10)
        right = tk.Frame(pics, bg=CARD)
        right.pack(side="left", padx=10)
        label(left, "START here", bold=True).pack()
        self.f1 = _FrameBox(left, clip.path)
        self.f1.pack()
        label(right, "END here", bold=True).pack()
        self.f2 = _FrameBox(right, clip.path)
        self.f2.pack()
        self.s_var = tk.DoubleVar(value=clip.in_point)
        self.e_var = tk.DoubleVar(value=clip.out_point)
        self.s_lbl = label(left, "", muted=True)
        self.s_lbl.pack()
        self.e_lbl = label(right, "", muted=True)
        self.e_lbl.pack()
        hscale(left, 0, max(0.1, total), self.s_var, length=300,
               resolution=0.05, command=self._changed).pack()
        hscale(right, 0, max(0.1, total), self.e_var, length=300,
               resolution=0.05, command=self._changed).pack()
        self.len_lbl = tk.Label(self, text="", bg=CARD, fg=TEXT,
                                font=(FONT, 12, "bold"))
        self.len_lbl.pack(pady=(4, 0))
        quick = tk.Frame(self, bg=CARD)
        quick.pack()
        GhostButton(quick, "Reset (keep whole clip)", font_size=10,
                    command=self._reset).pack(side="left", padx=4)
        self._buttons("Use this trim")
        self._changed()
        self.f1.show(clip.in_point)
        self.f2.show(clip.out_point)

    def _reset(self):
        self.s_var.set(0)
        self.e_var.set(self.clip.source_duration or self.clip.out_point)
        self._changed()

    def _changed(self, _=None):
        s, e = self.s_var.get(), self.e_var.get()
        if e < s + 0.2:
            e = s + 0.2
            self.e_var.set(e)
        self.s_lbl.config(text=f"starts at {s:.2f} s")
        self.e_lbl.config(text=f"ends at {e:.2f} s")
        self.len_lbl.config(text=f"Kept: {e - s:.2f} seconds")
        self.f1.show_later(s)
        self.f2.show_later(e)

    def ok(self):
        self.result = (round(self.s_var.get(), 3), round(self.e_var.get(), 3))
        self.destroy()


class SplitDialog(_Dialog):
    """Pick the moment to cut a clip in two."""

    def __init__(self, parent, clip):
        super().__init__(parent, "Split clip in two")
        self.clip = clip
        tk.Label(self, text=f"✂  Split: {clip.name}", bg=CARD, fg=BLUE_DARK,
                 font=(FONT, 14, "bold")).pack(pady=(14, 2))
        tk.Label(self, text="Slide to the moment where the clip should be "
                            "cut into two pieces.",
                 bg=CARD, fg=TEXT_MUTED, font=(FONT, 10)).pack()
        self.fb = _FrameBox(self, clip.path, 480, 270)
        self.fb.pack(pady=8)
        self.var = tk.DoubleVar(value=clip.duration / 2)
        self.lbl = label(self, "")
        self.lbl.pack()
        hscale(self, 0, clip.duration, self.var, length=480, resolution=0.05,
               command=self._changed).pack()
        self._buttons("Split here")
        self._changed()

    def _src_time(self):
        return self.clip.in_point + self.var.get() * self.clip.speed

    def _changed(self, _=None):
        t = self.var.get()
        self.lbl.config(text=f"Cut at {t:.2f} s into the clip  "
                             f"(pieces: {t:.1f} s + {self.clip.duration - t:.1f} s)")
        self.fb.show_later(self._src_time())

    def ok(self):
        self.result = round(self.var.get(), 3)
        self.destroy()


class CropDialog(_Dialog):
    def __init__(self, parent, clip):
        super().__init__(parent, "Crop - cut the edges")
        self.clip = clip
        tk.Label(self, text="⬚  Crop the edges", bg=CARD, fg=BLUE_DARK,
                 font=(FONT, 14, "bold")).pack(pady=(14, 2))
        tk.Label(self, text="How much to cut off each edge (percent).",
                 bg=CARD, fg=TEXT_MUTED, font=(FONT, 10)).pack()
        self.fb = _FrameBox(self, clip.path, 420, 240)
        self.fb.pack(pady=8)
        self.fb.show(clip.in_point)
        grid = tk.Frame(self, bg=CARD)
        grid.pack()
        self.vars = {}
        cur = clip.crop or (0, 0, 0, 0)
        for i, (name, key) in enumerate([("Left", 0), ("Top", 1),
                                         ("Right", 2), ("Bottom", 3)]):
            label(grid, name).grid(row=i // 2, column=(i % 2) * 2, padx=6,
                                   sticky="e")
            v = tk.DoubleVar(value=cur[key])
            self.vars[key] = v
            hscale(grid, 0, 45, v, length=200).grid(row=i // 2,
                                                    column=(i % 2) * 2 + 1)
        GhostButton(self, "No crop", font_size=10,
                    command=lambda: [v.set(0) for v in self.vars.values()]
                    ).pack(pady=(6, 0))
        self._buttons("Use this crop")

    def ok(self):
        vals = tuple(round(self.vars[k].get(), 1) for k in range(4))
        self.result = vals if any(vals) else ()
        self.destroy()


class TextDialog(_Dialog):
    """Add or edit words on the screen."""

    def __init__(self, parent, item=None, default_style=TEXT_STYLES[0],
                 default_start=0.0, total=10.0):
        super().__init__(parent, "Words on screen")
        self.item = item
        tk.Label(self, text="🔤  Words on the screen", bg=CARD, fg=BLUE_DARK,
                 font=(FONT, 14, "bold")).pack(pady=(14, 6))
        body = tk.Frame(self, bg=CARD)
        body.pack(padx=20)
        label(body, "Type your words:").grid(row=0, column=0, sticky="nw",
                                            pady=4)
        self.txt = tk.Text(body, width=44, height=4, font=(FONT, 12),
                           relief="solid", bd=1, wrap="word")
        self.txt.grid(row=0, column=1, columnspan=3, pady=4, sticky="w")
        if item:
            self.txt.insert("1.0", item.text)
        label(body, "Where:").grid(row=1, column=0, sticky="w", pady=4)
        self.style = tk.StringVar(value=item.style if item else default_style)
        ttk.Combobox(body, textvariable=self.style, values=TEXT_STYLES,
                     state="readonly", width=24).grid(row=1, column=1,
                                                      sticky="w", pady=4)
        label(body, "Size:").grid(row=1, column=2, sticky="e", padx=(12, 4))
        self.size = tk.StringVar(value=item.size if item else (
            "Large" if default_style.startswith("Title") else "Medium"))
        ttk.Combobox(body, textvariable=self.size, values=TEXT_SIZES,
                     state="readonly", width=9).grid(row=1, column=3,
                                                     sticky="w")
        label(body, "Color:").grid(row=2, column=0, sticky="w", pady=4)
        self.color = tk.StringVar(value=item.color if item else "White")
        ttk.Combobox(body, textvariable=self.color,
                     values=list(TEXT_COLORS.keys()), state="readonly",
                     width=24).grid(row=2, column=1, sticky="w", pady=4)
        self.outline = tk.BooleanVar(value=item.outline if item else True)
        self.box = tk.BooleanVar(value=item.box if item else False)
        ttk.Checkbutton(body, text="Dark outline", variable=self.outline,
                        style="Card.TCheckbutton").grid(row=2, column=2,
                                                        columnspan=2,
                                                        sticky="w")
        ttk.Checkbutton(body, text="Dark box behind", variable=self.box,
                        style="Card.TCheckbutton").grid(row=3, column=2,
                                                        columnspan=2,
                                                        sticky="w")
        label(body, "Show from (seconds):").grid(row=3, column=0, sticky="w",
                                                pady=4)
        self.start = tk.DoubleVar(value=item.start if item else default_start)
        tk.Spinbox(body, textvariable=self.start, from_=0, to=max(0, total),
                   increment=0.5, width=8, font=(FONT, 11)
                   ).grid(row=3, column=1, sticky="w")
        label(body, "For how long (seconds):").grid(row=4, column=0,
                                                   sticky="w", pady=4)
        self.dur = tk.DoubleVar(value=item.duration if item else 4.0)
        tk.Spinbox(body, textvariable=self.dur, from_=0.5, to=600,
                   increment=0.5, width=8, font=(FONT, 11)
                   ).grid(row=4, column=1, sticky="w")
        tk.Label(body, text=f"(your video is {fmt_time(total)} long)",
                 bg=CARD, fg=TEXT_MUTED, font=(FONT, 9)).grid(
            row=4, column=2, columnspan=2, sticky="w")
        self._buttons("Use these words")
        self.txt.focus_set()

    def ok(self):
        text = self.txt.get("1.0", "end").strip()
        if not text:
            self.cancel()
            return
        try:
            start = max(0.0, float(self.start.get()))
            dur = max(0.5, float(self.dur.get()))
        except (tk.TclError, ValueError):
            start, dur = 0.0, 4.0
        self.result = dict(text=text, style=self.style.get(),
                           size=self.size.get(), color=self.color.get(),
                           outline=self.outline.get(), box=self.box.get(),
                           start=start, duration=dur)
        self.destroy()


class SizeDialog(_Dialog):
    def __init__(self, parent, w=1920, h=1080):
        super().__init__(parent, "Custom video size")
        tk.Label(self, text="Custom size (pixels)", bg=CARD, fg=BLUE_DARK,
                 font=(FONT, 14, "bold")).pack(pady=(14, 6))
        row = tk.Frame(self, bg=CARD)
        row.pack(padx=20)
        label(row, "Width:").grid(row=0, column=0, padx=4)
        self.w = tk.IntVar(value=w)
        tk.Spinbox(row, textvariable=self.w, from_=64, to=7680, increment=2,
                   width=8, font=(FONT, 12)).grid(row=0, column=1)
        label(row, "Height:").grid(row=0, column=2, padx=4)
        self.h = tk.IntVar(value=h)
        tk.Spinbox(row, textvariable=self.h, from_=64, to=7680, increment=2,
                   width=8, font=(FONT, 12)).grid(row=0, column=3)
        self._buttons("Use this size")

    def ok(self):
        try:
            w, h = int(self.w.get()), int(self.h.get())
        except (tk.TclError, ValueError):
            self.cancel()
            return
        self.result = (max(64, w - w % 2), max(64, h - h % 2))
        self.destroy()


class AudioDialog(_Dialog):
    """Settings for a music / voice / sound-effect item."""

    def __init__(self, parent, item, total):
        super().__init__(parent, "Sound settings")
        self.item = item
        kind = {"music": "🎵 Music", "voice": "🎙 Voice",
                "sfx": "🔊 Sound effect"}.get(item.kind, "Sound")
        tk.Label(self, text=f"{kind}: {item.name}", bg=CARD, fg=BLUE_DARK,
                 font=(FONT, 13, "bold")).pack(pady=(14, 6), padx=20)
        body = tk.Frame(self, bg=CARD)
        body.pack(padx=20)
        label(body, "Volume (%):").grid(row=0, column=0, sticky="w")
        self.vol = tk.DoubleVar(value=round(min(1.0, item.volume) * 100))
        hscale(body, 0, 100, self.vol, length=260).grid(row=0, column=1,
                                                        sticky="w")
        label(body, "Starts at (seconds):").grid(row=1, column=0, sticky="w",
                                                pady=4)
        self.start = tk.DoubleVar(value=item.start)
        tk.Spinbox(body, textvariable=self.start, from_=0, to=max(0, total),
                   increment=0.5, width=8, font=(FONT, 11)
                   ).grid(row=1, column=1, sticky="w")
        label(body, "Skip the first (seconds):").grid(row=2, column=0,
                                                     sticky="w", pady=4)
        self.trim = tk.DoubleVar(value=item.trim_start)
        tk.Spinbox(body, textvariable=self.trim, from_=0, to=3600,
                   increment=1, width=8, font=(FONT, 11)
                   ).grid(row=2, column=1, sticky="w")
        self.loop = tk.BooleanVar(value=item.loop)
        ttk.Checkbutton(body, text="Repeat until the video ends",
                        variable=self.loop, style="Card.TCheckbutton"
                        ).grid(row=3, column=0, columnspan=2, sticky="w",
                               pady=4)
        label(body, "Fade in (seconds):").grid(row=4, column=0, sticky="w")
        self.fin = tk.DoubleVar(value=item.fade_in)
        hscale(body, 0, 5, self.fin, length=200, resolution=0.5
               ).grid(row=4, column=1, sticky="w")
        label(body, "Fade out (seconds):").grid(row=5, column=0, sticky="w")
        self.fout = tk.DoubleVar(value=item.fade_out)
        hscale(body, 0, 5, self.fout, length=200, resolution=0.5
               ).grid(row=5, column=1, sticky="w")
        self._buttons("Use these settings")

    def ok(self):
        try:
            self.result = dict(volume=self.vol.get() / 100.0,
                               start=max(0.0, float(self.start.get())),
                               trim_start=max(0.0, float(self.trim.get())),
                               loop=self.loop.get(), fade_in=self.fin.get(),
                               fade_out=self.fout.get())
        except (tk.TclError, ValueError):
            self.result = None
        self.destroy()


class PhotoLengthDialog(_Dialog):
    """How long a photo stays on screen: 1 to 300 seconds."""

    QUICK = [3, 5, 10, 15, 30, 60, 120, 300]

    def __init__(self, parent, clip, photo_count=1):
        super().__init__(parent, "Photo time")
        tk.Label(self, text="How long should this photo stay on screen?",
                 bg=CARD, fg=BLUE_DARK, font=(FONT, 13, "bold")
                 ).pack(pady=(14, 6), padx=20)
        cur = max(1.0, min(300.0, round(clip.duration, 1)))
        self.var = tk.DoubleVar(value=cur)
        row = tk.Frame(self, bg=CARD)
        row.pack(pady=(2, 4))
        self.spin = tk.Spinbox(row, textvariable=self.var, from_=1, to=300,
                               increment=1, width=6, font=(FONT, 16, "bold"),
                               justify="center")
        self.spin.pack(side="left")
        tk.Label(row, text=" seconds", bg=CARD, fg=TEXT,
                 font=(FONT, 13)).pack(side="left")
        self.mins = tk.Label(self, text="", bg=CARD, fg=TEXT_MUTED,
                             font=(FONT, 10))
        self.mins.pack()
        hscale(self, 1, 300, self.var, length=420, resolution=1,
               command=lambda v: self._show()).pack(padx=20)
        quick = tk.Frame(self, bg=CARD)
        quick.pack(pady=(6, 2))
        for q in self.QUICK:
            t = f"{q} s" if q < 60 else f"{q // 60} min"
            GhostButton(quick, t, font_size=9,
                        command=lambda v=q: (self.var.set(v), self._show())
                        ).pack(side="left", padx=2)
        self.all_var = tk.BooleanVar(value=False)
        if photo_count > 1:
            ttk.Checkbutton(self, text=f"Use this time for all {photo_count} "
                                       f"photos", variable=self.all_var,
                            style="Card.TCheckbutton").pack(pady=(8, 0))
        tk.Label(self, text="Tip: want the photos to end with your song? "
                            "Use  🎵 Fit to music  instead.",
                 bg=CARD, fg=TEXT_MUTED, font=(FONT, 9, "italic")
                 ).pack(pady=(6, 0), padx=20)
        self.var.trace_add("write", lambda *a: self._show())
        self._show()
        self._buttons("OK")

    def _value(self):
        try:
            v = float(self.var.get())
        except (tk.TclError, ValueError):
            return None
        return max(1.0, min(300.0, v))

    def _show(self):
        v = self._value()
        if v is None:
            self.mins.config(text="Type a number from 1 to 300")
        elif v >= 60:
            m, sec = divmod(int(round(v)), 60)
            self.mins.config(text=f"= {m} min {sec:02d} s")
        else:
            self.mins.config(text="(1 second to 5 minutes)")

    def ok(self):
        v = self._value()
        if v is None:
            return
        self.result = (v, self.all_var.get())
        self.destroy()
