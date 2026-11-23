"""
EZ Video Maker - turn WhatsApp voice notes and audio into MP3 or WAV.

WhatsApp saves voice notes as .opus / .ogg (and sometimes .m4a, .aac,
.amr or .mp4).  Many programs and websites can't open those, so this
makes a normal MP3 (small, plays everywhere) or WAV (full quality, for
music programs) - and can drop it straight into the video.
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import ffmpeg_engine as ff
from .theme import (FONT, CARD, TEXT, TEXT_MUTED, BLUE_DARK, ORANGE, GREEN,
                    BigButton, GhostButton)

WHATSAPP_GREEN = "#25D366"
WA_EXTS = (".opus", ".ogg", ".oga", ".m4a", ".aac", ".amr", ".mp4", ".3gp",
           ".webm", ".caf", ".mp3", ".wav")
FORMATS = [("MP3", "MP3  -  small, plays everywhere (best for most people)"),
           ("WAV", "WAV  -  full quality, for music programs"),
           ("BOTH", "Both MP3 and WAV")]


def output_folder():
    base = os.path.join(os.path.expanduser("~"), "Music")
    if not os.path.isdir(base):
        base = os.path.expanduser("~")
    d = os.path.join(base, "EZ Video Maker Output", "WhatsApp")
    os.makedirs(d, exist_ok=True)
    return d


def pick_files(parent):
    pats = " ".join("*" + e for e in WA_EXTS)
    return list(filedialog.askopenfilenames(
        title="Choose WhatsApp voice notes or audio", parent=parent,
        filetypes=[("WhatsApp audio", pats), ("All files", "*.*")]))


def convert_one(src, fmt, folder):
    """Convert one file. Returns (ok, out_path_or_error)."""
    name = os.path.splitext(os.path.basename(src))[0]
    dst = ff.unique_path(os.path.join(folder, f"{name}.{fmt.lower()}"))
    args = ff.build_convert_args(src, dst, fmt, quality="High Quality")
    ok, msg = ff.run_ffmpeg(args, duration=ff.probe_duration(src))
    if ok and os.path.isfile(dst) and os.path.getsize(dst) > 0:
        return True, dst
    try:
        if os.path.exists(dst):
            os.remove(dst)
    except OSError:
        pass
    return False, msg or "Could not convert this file."


class WhatsAppDialog(tk.Toplevel):
    """Pick MP3 / WAV, convert, optionally add to the video.

    on_add(paths, kind) is called on the Tk thread with the finished files
    the person wants in their video (kind is "music" or "voice")."""

    def __init__(self, parent, paths, on_add=None):
        super().__init__(parent)
        self.title("WhatsApp audio to MP3 / WAV")
        self.configure(bg=CARD)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        self.paths = paths
        self.on_add = on_add
        self.folder = output_folder()
        self.q = queue.Queue()
        self.busy = False
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())

        tk.Label(self, text="📱  WhatsApp audio  →  MP3 / WAV", bg=CARD,
                 fg=BLUE_DARK, font=(FONT, 14, "bold")).pack(
            padx=24, pady=(16, 2), anchor="w")
        n = len(paths)
        tk.Label(self, text=(f"{n} file{'s' if n != 1 else ''} chosen: " +
                             ", ".join(os.path.basename(p) for p in paths[:3]) +
                             (" …" if n > 3 else "")),
                 bg=CARD, fg=TEXT_MUTED, font=(FONT, 9), wraplength=460,
                 justify="left").pack(padx=24, anchor="w")

        box = tk.Frame(self, bg=CARD)
        box.pack(padx=24, pady=(12, 4), fill="x")
        tk.Label(box, text="Make it:", bg=CARD, fg=TEXT,
                 font=(FONT, 11, "bold")).pack(anchor="w")
        self.fmt = tk.StringVar(value="MP3")
        for key, txt in FORMATS:
            ttk.Radiobutton(box, text=txt, value=key, variable=self.fmt,
                            style="Card.TRadiobutton").pack(anchor="w",
                                                            pady=1)

        box2 = tk.Frame(self, bg=CARD)
        box2.pack(padx=24, pady=(10, 4), fill="x")
        tk.Label(box2, text="Then:", bg=CARD, fg=TEXT,
                 font=(FONT, 11, "bold")).pack(anchor="w")
        self.add = tk.StringVar(value="music" if on_add else "none")
        opts = [("none", "Just save it (I'll use it somewhere else)")]
        if on_add:
            opts = [("music", "Add it to my video as music"),
                    ("voice", "Add it to my video as a voice track")] + opts
        for key, txt in opts:
            ttk.Radiobutton(box2, text=txt, value=key, variable=self.add,
                            style="Card.TRadiobutton").pack(anchor="w",
                                                            pady=1)

        tk.Label(self, text="Saved in:  " + self.folder, bg=CARD,
                 fg=TEXT_MUTED, font=(FONT, 8), wraplength=460,
                 justify="left").pack(padx=24, pady=(8, 0), anchor="w")
        self.status = tk.Label(self, text="", bg=CARD, fg=BLUE_DARK,
                               font=(FONT, 10, "bold"))
        self.status.pack(padx=24, pady=(6, 0), anchor="w")

        row = tk.Frame(self, bg=CARD)
        row.pack(pady=(10, 16))
        self.go_btn = BigButton(row, "Convert", command=self.start,
                                color=ORANGE, font_size=12, pady=8)
        self.go_btn.pack(side="left", padx=8)
        GhostButton(row, "Close", command=self.close).pack(side="left",
                                                           padx=8)

    def show(self):
        self.update_idletasks()
        p = self.master.winfo_toplevel()
        x = p.winfo_rootx() + (p.winfo_width() - self.winfo_width()) // 2
        y = p.winfo_rooty() + (p.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.grab_set()

    # ---------------------------------------------------------- work
    def start(self):
        if self.busy:
            return
        self.busy = True
        try:
            self.go_btn.config(state="disabled")
        except tk.TclError:
            pass
        fmt = self.fmt.get()
        fmts = ["MP3", "WAV"] if fmt == "BOTH" else [fmt]
        jobs = [(p, f) for p in self.paths for f in fmts]
        self.status.config(text=f"Converting… 0 of {len(jobs)}")
        threading.Thread(target=self._work, args=(jobs,), daemon=True).start()
        self.after(150, self._poll)

    def _work(self, jobs):
        done, failed = [], []
        for i, (src, fmt) in enumerate(jobs, 1):
            ok, res = convert_one(src, fmt, self.folder)
            (done if ok else failed).append((src, fmt, res))
            self.q.put(("progress", i, len(jobs)))
        self.q.put(("finished", done, failed))

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "progress":
                    self.status.config(
                        text=f"Converting… {msg[1]} of {msg[2]}")
                else:
                    self._finished(msg[1], msg[2])
                    return
        except queue.Empty:
            pass
        try:
            self.after(150, self._poll)
        except tk.TclError:
            pass

    def _finished(self, done, failed):
        self.busy = False
        kind = self.add.get()
        if kind in ("music", "voice") and self.on_add and done:
            # one file per source: prefer the MP3 when both were made
            chosen = {}
            for src, fmt, out in done:
                if src not in chosen or fmt == "MP3":
                    chosen[src] = out
            self.on_add([chosen[s] for s in self.paths if s in chosen], kind)
        text = f"Done! {len(done)} file{'s' if len(done) != 1 else ''} made."
        if failed:
            text += f"  {len(failed)} could not be converted."
        self.status.config(text=text, fg=GREEN if not failed else ORANGE)
        try:
            self.go_btn.config(state="normal")
        except tk.TclError:
            pass
        if failed:
            details = "\n\n".join(f"{os.path.basename(s)} ({f}):\n{e[-300:]}"
                                  for s, f, e in failed[:3])
            messagebox.showwarning("Some files didn't convert", details,
                                   parent=self)
        if done:
            ff.open_folder(self.folder)

    def close(self):
        if self.busy and not messagebox.askyesno(
                "Still converting", "Converting is still running. Close "
                "anyway? (It finishes in the background.)", parent=self):
            return
        self.destroy()
