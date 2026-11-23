"""
EZ Video Maker - Convert screen.
Add files -> pick what you want -> Convert.  Batch friendly.
Video mode: FLV/AVI/MOV/... -> MP4 and more, video -> MP3, and
"Change the shape" so a horizontal video becomes a TikTok vertical (or the
other way round).  Audio mode: MP3 <-> WAV and more.
"""

import os
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import ffmpeg_engine as ff
from .theme import (BigButton, GhostButton, card, header_bar, FONT, BG, CARD,
                    BLUE, BLUE_DARK, BLUE_LIGHT, ORANGE, TEXT, TEXT_MUTED,
                    GREEN)

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except Exception:
    HAS_DND = False

SHAPE_CHOICES = ["Keep the same shape",
                 "📱 TikTok / Reels / Shorts - Vertical (9:16)",
                 "🖥 YouTube / DistroKid - Horizontal (16:9)",
                 "⬜ Square (1:1)",
                 "Horizontal 720p", "Horizontal 4K", "Vertical 4K"]
SHAPE_SIZES = {
    SHAPE_CHOICES[1]: (1080, 1920), SHAPE_CHOICES[2]: (1920, 1080),
    SHAPE_CHOICES[3]: (1080, 1080), SHAPE_CHOICES[4]: (1280, 720),
    SHAPE_CHOICES[5]: (3840, 2160), SHAPE_CHOICES[6]: (2160, 3840),
}


class ConverterScreen(tk.Frame):
    def __init__(self, parent, app, mode="video"):
        super().__init__(parent, bg=BG)
        self.app = app
        self.mode = mode
        self.files = []
        self.jobs_queue = []
        self.current_job = None
        self.converting = False
        self.ui_queue = queue.Queue()

        title = "Convert Video" if mode == "video" else "Convert Audio"
        header_bar(self, title, on_back=self._go_home)
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=14)

        # ---- Step 1: files ----
        tk.Label(body, text="1.  Add your files", bg=BG, fg=BLUE_DARK,
                 font=(FONT, 14, "bold")).pack(anchor="w")
        drop = card(body)
        drop.pack(fill="both", expand=True, pady=(6, 12))
        self.listbox = tk.Listbox(drop, font=(FONT, 11), bd=0,
                                  selectbackground=BLUE_LIGHT,
                                  selectforeground=TEXT, activestyle="none",
                                  height=7, selectmode="extended")
        self.listbox.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        hint = ("Drag files here, or click Add Files" if HAS_DND
                else "Click Add Files to choose your files")
        tk.Label(drop, text=hint, bg=CARD, fg=TEXT_MUTED,
                 font=(FONT, 10, "italic")).pack(pady=(0, 6))
        btns = tk.Frame(drop, bg=CARD)
        btns.pack(pady=(0, 10))
        BigButton(btns, "➕  Add Files", command=self.add_files, color=BLUE,
                  font_size=11, pady=8).pack(side="left", padx=6)
        GhostButton(btns, "Remove Selected", command=self.remove_selected
                    ).pack(side="left", padx=6)
        GhostButton(btns, "Clear All", command=self.clear_all
                    ).pack(side="left", padx=6)
        if HAS_DND:
            self.listbox.drop_target_register(DND_FILES)
            self.listbox.dnd_bind("<<Drop>>", self._on_drop)

        # ---- Step 2: what do you want ----
        tk.Label(body, text="2.  Choose what you want", bg=BG, fg=BLUE_DARK,
                 font=(FONT, 14, "bold")).pack(anchor="w")
        opts = card(body)
        opts.pack(fill="x", pady=(6, 12))
        row = tk.Frame(opts, bg=CARD)
        row.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(row, text="Turn my files into:", bg=CARD, fg=TEXT,
                 font=(FONT, 12)).grid(row=0, column=0, sticky="w")
        if mode == "video":
            fmt_values = ff.VIDEO_TARGETS + ["--- sound only ---"] + \
                ff.AUDIO_TARGETS
            default_fmt = "MP4"
        else:
            fmt_values = ff.AUDIO_TARGETS
            default_fmt = "WAV"
        self.fmt_var = tk.StringVar(value=default_fmt)
        self.fmt_box = ttk.Combobox(row, textvariable=self.fmt_var,
                                    values=fmt_values, state="readonly",
                                    width=20, font=(FONT, 12))
        self.fmt_box.grid(row=0, column=1, padx=10)
        self.fmt_box.bind("<<ComboboxSelected>>", self._fmt_changed)
        tk.Label(row, text="Quality:", bg=CARD, fg=TEXT,
                 font=(FONT, 12)).grid(row=0, column=2, padx=(18, 0))
        self.quality_var = tk.StringVar(value="High Quality")
        ttk.Combobox(row, textvariable=self.quality_var,
                     values=list(ff.QUALITY_PRESETS.keys()),
                     state="readonly", width=14, font=(FONT, 12)
                     ).grid(row=0, column=3, padx=10)
        if mode == "video":
            tk.Label(row, text="Video shape:", bg=CARD, fg=TEXT,
                     font=(FONT, 12)).grid(row=1, column=0, sticky="w",
                                           pady=(8, 0))
            self.shape_var = tk.StringVar(value=SHAPE_CHOICES[0])
            ttk.Combobox(row, textvariable=self.shape_var,
                         values=SHAPE_CHOICES, state="readonly", width=40,
                         font=(FONT, 11)).grid(row=1, column=1, columnspan=2,
                                               padx=10, pady=(8, 0),
                                               sticky="w")
            tk.Label(row, text="Wrong-shape clips:", bg=CARD, fg=TEXT,
                     font=(FONT, 11)).grid(row=2, column=0, sticky="w",
                                           pady=(6, 0))
            self.fit_var = tk.StringVar(value=ff.FIT_MODES[1])
            ttk.Combobox(row, textvariable=self.fit_var, values=ff.FIT_MODES,
                         state="readonly", width=32, font=(FONT, 10)
                         ).grid(row=2, column=1, columnspan=2, padx=10,
                                pady=(6, 0), sticky="w")
        out_row = tk.Frame(opts, bg=CARD)
        out_row.pack(fill="x", padx=14, pady=(4, 6))
        tk.Label(out_row, text="Save finished files to:", bg=CARD, fg=TEXT,
                 font=(FONT, 12)).pack(side="left")
        self.out_var = tk.StringVar(value=self._default_out())
        tk.Label(out_row, textvariable=self.out_var, bg=CARD, fg=BLUE,
                 font=(FONT, 10)).pack(side="left", padx=8)
        GhostButton(out_row, "Change Folder", command=self.pick_out
                    ).pack(side="right")
        tk.Label(opts, text="Your original files are never changed or "
                            "deleted.", bg=CARD, fg=GREEN,
                 font=(FONT, 10, "italic")).pack(anchor="w", padx=14,
                                                 pady=(0, 8))

        # ---- Step 3: convert ----
        act = tk.Frame(body, bg=BG)
        act.pack(fill="x", pady=(4, 4))
        tk.Label(act, text="3.", bg=BG, fg=BLUE_DARK,
                 font=(FONT, 14, "bold")).pack(side="left", padx=(0, 8))
        self.convert_btn = BigButton(act, "▶  Convert Now",
                                     command=self.start_convert,
                                     color=ORANGE, font_size=15)
        self.convert_btn.pack(side="left")
        self.cancel_btn = GhostButton(act, "Cancel", command=self.cancel)
        self.status_var = tk.StringVar(value="")
        tk.Label(body, textvariable=self.status_var, bg=BG, fg=TEXT,
                 font=(FONT, 11, "bold")).pack(anchor="w", pady=(8, 2))
        self.bar = ttk.Progressbar(body, style="Orange.Horizontal.TProgressbar",
                                   maximum=100)
        self.bar.pack(fill="x")
        self.eta_var = tk.StringVar(value="")
        tk.Label(body, textvariable=self.eta_var, bg=BG, fg=TEXT_MUTED,
                 font=(FONT, 10)).pack(anchor="w", pady=(4, 0))
        self.after(120, self._poll_ui_queue)

    # ---------- helpers ----------
    def _go_home(self):
        if self.converting:
            if not messagebox.askyesno("Still converting",
                                       "A conversion is running. Stop it and "
                                       "go home?", parent=self):
                return
            self.cancel()
        self.app.show_welcome()

    def _default_out(self):
        sub = "Videos" if self.mode == "video" else "Music"
        base = os.path.join(os.path.expanduser("~"), sub)
        if not os.path.isdir(base):
            base = os.path.expanduser("~")
        return os.path.join(base, "EZ Video Maker Output")

    def pick_out(self):
        d = filedialog.askdirectory(title="Choose a folder for finished files",
                                    parent=self)
        if d:
            self.out_var.set(d)

    def _fmt_changed(self, _=None):
        if self.fmt_var.get().startswith("---"):
            self.fmt_var.set("MP3")

    def add_files(self):
        vids = " ".join("*" + e for e in sorted(ff.VIDEO_EXTS))
        auds = " ".join("*" + e for e in sorted(ff.AUDIO_EXTS))
        if self.mode == "video":
            types = [("Video files", vids), ("All files", "*.*")]
        else:
            types = [("Sound files", auds),
                     ("Videos (to pull the sound out)", vids),
                     ("All files", "*.*")]
        paths = filedialog.askopenfilenames(title="Choose files",
                                            filetypes=types, parent=self)
        self._add_paths(paths)

    def _on_drop(self, event):
        self._add_paths(self.listbox.tk.splitlist(event.data))

    def _add_paths(self, paths):
        added = 0
        for p in paths:
            p = p.strip("{}")
            ext = os.path.splitext(p)[1].lower()
            if not os.path.isfile(p):
                continue
            if ext not in (ff.VIDEO_EXTS | ff.AUDIO_EXTS):
                messagebox.showwarning(
                    "File type not supported",
                    f"Sorry, this file type is not supported:\n"
                    f"{os.path.basename(p)}", parent=self)
                continue
            if p not in self.files:
                self.files.append(p)
                self.listbox.insert("end", "  " + os.path.basename(p))
                added += 1
        if added:
            self.status_var.set(f"{len(self.files)} file(s) ready.")

    def remove_selected(self):
        for i in reversed(list(self.listbox.curselection())):
            self.listbox.delete(i)
            del self.files[i]

    def clear_all(self):
        self.listbox.delete(0, "end")
        self.files.clear()
        self.status_var.set("")

    # ---------- conversion ----------
    def start_convert(self):
        if self.converting:
            return
        if not self.files:
            messagebox.showinfo("No files yet",
                                "Please add at least one file first.",
                                parent=self)
            return
        fmt = self.fmt_var.get()
        if fmt.startswith("---"):
            messagebox.showinfo("Pick a format",
                                "Please choose a format from the list.",
                                parent=self)
            return
        outdir = self.out_var.get()
        try:
            os.makedirs(outdir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Folder problem",
                                 f"Could not use that folder:\n{e}",
                                 parent=self)
            return
        self.jobs_queue = list(self.files)
        self.total_jobs = len(self.jobs_queue)
        self.done_jobs = 0
        self.failed = []
        self.converting = True
        self.convert_btn.config(state="disabled", text="Converting…")
        self.cancel_btn.pack(side="left", padx=12)
        self._next_job()

    def _shape(self):
        if self.mode != "video":
            return None
        return SHAPE_SIZES.get(self.shape_var.get())

    def _next_job(self):
        if not self.jobs_queue:
            self._all_done()
            return
        src = self.jobs_queue.pop(0)
        fmt = self.fmt_var.get()
        base = os.path.splitext(os.path.basename(src))[0]
        shape = self._shape()
        suffix = ""
        if shape:
            w, h = shape
            suffix = " (TikTok vertical)" if h > w else \
                (" (square)" if h == w else " (horizontal)")
        dst = ff.unique_path(os.path.join(self.out_var.get(),
                                          f"{base}{suffix}.{fmt.lower()}"))
        dur = ff.probe_duration(src)
        args = ff.build_convert_args(
            src, dst, fmt, quality=self.quality_var.get(), shape=shape,
            fit_mode=self.fit_var.get() if self.mode == "video" else None)
        n = self.done_jobs + 1
        self.status_var.set(f"Converting file {n} of {self.total_jobs}: "
                            f"{os.path.basename(src)}")
        self.bar["value"] = 0
        self.eta_var.set("Getting started…")
        job = ff.FFmpegJob(
            args, duration=dur,
            on_progress=lambda p, s, eta: self.ui_queue.put(("prog", p, eta)),
            on_done=lambda ok, msg, src=src: self.ui_queue.put(
                ("done", ok, msg, src)))
        self.current_job = job
        job.start()

    def _poll_ui_queue(self):
        try:
            while True:
                item = self.ui_queue.get_nowait()
                if item[0] == "prog":
                    _, pct, eta = item
                    self.bar["value"] = pct
                    if eta is not None:
                        m, s = divmod(int(eta), 60)
                        self.eta_var.set(
                            f"{pct:.0f}% done - about {m} min {s} sec left"
                            if m else f"{pct:.0f}% done - about {s} seconds "
                                      f"left")
                elif item[0] == "done":
                    _, ok, msg, src = item
                    self.done_jobs += 1
                    if not ok and msg != "Cancelled.":
                        self.failed.append((os.path.basename(src), msg))
                    if self.converting and msg != "Cancelled.":
                        self._next_job()
                    elif msg == "Cancelled.":
                        self._all_done(cancelled=True)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(120, self._poll_ui_queue)

    def _all_done(self, cancelled=False):
        self.converting = False
        self.current_job = None
        self.convert_btn.config(state="normal", text="▶  Convert Now")
        self.cancel_btn.pack_forget()
        if cancelled:
            self.status_var.set("Conversion cancelled.")
            self.eta_var.set("")
            return
        ok_count = self.done_jobs - len(self.failed)
        self.bar["value"] = 100
        if not self.failed:
            self.status_var.set(f"✔ All done! {ok_count} file(s) saved.")
            self.eta_var.set(f"Saved to: {self.out_var.get()}")
            if messagebox.askyesno(
                    "Success!",
                    f"All done! {ok_count} file(s) were converted.\n\n"
                    "Open the folder to see them?", parent=self):
                ff.open_folder(self.out_var.get())
        else:
            names = "\n".join(f"- {n}: {m.splitlines()[-1][:90] if m else ''}"
                              for n, m in self.failed)
            self.status_var.set(f"Finished with problems: {ok_count} worked, "
                                f"{len(self.failed)} failed.")
            messagebox.showwarning(
                "Some files had problems",
                f"These files could not be converted:\n{names}\n\n"
                "The rest were saved successfully.", parent=self)

    def cancel(self):
        if self.current_job:
            self.jobs_queue.clear()
            self.current_job.cancel()
