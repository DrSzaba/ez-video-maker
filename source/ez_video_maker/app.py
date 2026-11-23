"""
EZ Video Maker - main window and welcome screen.
"""

import os
import sys
import tkinter as tk
from tkinter import messagebox

from . import APP_NAME, __version__
from . import ffmpeg_engine as ff
from . import ezupdate
from .theme import (setup_style, BigButton, card, FONT, BG, CARD, BLUE,
                    BLUE_DARK, BLUE_LIGHT, ORANGE, ORANGE_DARK, TEXT,
                    TEXT_MUTED, GREEN)

try:
    from tkinterdnd2 import TkinterDnD
    _ROOT_CLASS = TkinterDnD.Tk
except Exception:
    _ROOT_CLASS = tk.Tk


class App:
    def __init__(self):
        self.root = _ROOT_CLASS()
        self.root.title(APP_NAME)
        self.root.geometry("1380x860")
        self.root.minsize(1180, 760)
        try:
            self.root.state("zoomed")
        except Exception:
            pass
        setup_style(self.root)
        self._set_icon()
        self.current = None
        # automatic updates from GitHub (checks in the background, never blocks)
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        self.updater = ezupdate.Updater(APP_NAME, __version__, "DrSzaba/ez-video-maker",
                                        "EZ-Video-Maker-Setup.zip", os.path.join(base, "EZVideoMaker"))
        self.updater.close_app = self._close
        self.update_bar = ezupdate.attach_to_tk(
            self.root, self.updater, self.root,
            {"bg": "#FDEEDD", "fg": BLUE_DARK, "button": ORANGE, "button_fg": "white"},
            FONT, on_close_chain=self._close)
        self.show_welcome()
        # double-clicked a .ezvm project file?
        arg = sys.argv[1] if len(sys.argv) > 1 else ""
        if arg.lower().endswith(".ezvm") and os.path.isfile(arg):
            self.show_editor()
            self.root.after(200, lambda: self.current._open_path(arg))
        self.root.after(300, self._check_engine)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _set_icon(self):
        try:
            ico = os.path.join(ff.assets_dir(), "icon.ico")
            png = os.path.join(ff.assets_dir(), "icon.png")
            if ff.IS_WIN and os.path.isfile(ico):
                self.root.iconbitmap(ico)
            elif os.path.isfile(png):
                self._icon_img = tk.PhotoImage(file=png)
                self.root.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def _check_engine(self):
        if ff.find_ffmpeg() and ff.find_ffprobe():
            return
        # first try to put it back quietly from the backup pack
        if ff.repair_engine():
            self.show_welcome()
            return
        self._engine_dialog()

    def _engine_dialog(self):
        from .theme import BigButton, GhostButton
        win = tk.Toplevel(self.root)
        win.title("Video engine missing")
        win.configure(bg=CARD)
        win.transient(self.root)
        tk.Label(win, text="The video engine (FFmpeg) could not be found",
                 bg=CARD, fg=BLUE_DARK, font=(FONT, 14, "bold")).pack(
            pady=(16, 4), padx=20)
        tk.Label(win, text=(
            "EZ Video Maker installs it in its own folder, so this usually "
            "means an antivirus program (often Windows Security) removed "
            "ffmpeg.exe after it was installed.\n\n"
            "Click Repair to put it back from the built-in backup. If it "
            "disappears again, open Windows Security > Virus & threat "
            "protection > Protection history, choose the ffmpeg item and "
            "click Restore / Allow."),
            bg=CARD, fg=TEXT, font=(FONT, 10), justify="left",
            wraplength=560).pack(padx=20)
        rep = tk.Text(win, height=8, width=80, font=("Consolas", 9),
                      bg="#F3F5F8", relief="flat")
        rep.insert("1.0", ff.engine_report())
        rep.config(state="disabled")
        rep.pack(padx=20, pady=10)
        status = tk.Label(win, text="", bg=CARD, fg=TEXT_MUTED,
                          font=(FONT, 10))
        status.pack()

        def repair():
            ok = ff.repair_engine()
            rep.config(state="normal")
            rep.delete("1.0", "end")
            rep.insert("1.0", ff.engine_report())
            rep.config(state="disabled")
            if ok:
                status.config(text="Repaired! The video engine is back.",
                              fg=GREEN)
                win.after(1500, lambda: (win.destroy(), self.show_welcome()))
            else:
                status.config(text="Could not repair. Please run the "
                                   "EZ Video Maker setup again.", fg="#C0392B")

        row = tk.Frame(win, bg=CARD)
        row.pack(pady=(4, 16))
        BigButton(row, "🔧  Repair now", command=repair, color=ORANGE,
                  font_size=12, pady=8).pack(side="left", padx=6)
        GhostButton(row, "Close", command=win.destroy).pack(side="left",
                                                            padx=6)
        win.grab_set()

    def _swap(self, frame):
        if self.current is not None:
            if hasattr(self.current, "shutdown"):
                try:
                    self.current.shutdown()
                except Exception:
                    pass
            self.current.destroy()
        self.current = frame
        frame.pack(fill="both", expand=True)

    # ---------------- screens ----------------
    def show_welcome(self):
        f = tk.Frame(self.root, bg=BG)
        top = tk.Frame(f, bg=BLUE_DARK)
        top.pack(fill="x")
        try:
            logo = os.path.join(ff.assets_dir(), "logo.png")
            if os.path.isfile(logo):
                self._logo = tk.PhotoImage(file=logo)
                tk.Label(top, image=self._logo, bg=BLUE_DARK).pack(
                    pady=(22, 0))
        except Exception:
            pass
        tk.Label(top, text="EZ VIDEO MAKER", bg=BLUE_DARK, fg="white",
                 font=(FONT, 30, "bold")).pack(pady=(6, 0))
        tk.Label(top, text="Make it.  Convert it.  Share it.  Easy.",
                 bg=BLUE_DARK, fg=ORANGE, font=(FONT, 13, "italic")
                 ).pack(pady=(2, 26))
        upd = tk.Button(top, text=f"Version {__version__}   \u27f3  Updates",
                        command=self.show_about, bg=BLUE_DARK, fg="white",
                        activebackground=BLUE, activeforeground="white",
                        relief="flat", bd=0, font=(FONT, 10, "bold"),
                        cursor="hand2", padx=12, pady=6)
        upd.place(relx=1.0, x=-14, y=12, anchor="ne")

        tk.Label(f, text="What would you like to do?", bg=BG, fg=TEXT,
                 font=(FONT, 17)).pack(pady=(34, 18))
        grid = tk.Frame(f, bg=BG)
        grid.pack(expand=True)
        choices = [
            ("🎬", "Make a Video",
             "Put clips and photos together.\nTikTok vertical or YouTube "
             "horizontal.\nAdd music, your voice, and words.",
             self.show_editor, ORANGE, ORANGE_DARK),
            ("🔄", "Convert Video",
             "FLV, AVI, MOV, WMV… → MP4\nVideo → MP3 sound\n"
             "Change the shape for TikTok",
             lambda: self.show_converter("video"), BLUE, BLUE_DARK),
            ("🎵", "Convert Audio",
             "MP3 → WAV, WAV → MP3,\nM4A, FLAC, OGG and more.\n"
             "Many files at once.",
             lambda: self.show_converter("audio"), BLUE, BLUE_DARK),
        ]
        for i, (emoji, title, sub, cmd, color, hover) in enumerate(choices):
            c = card(grid)
            c.grid(row=0, column=i, padx=18, ipadx=10, ipady=8, sticky="n")
            c.bind("<Enter>", lambda e, w=c, col=color: w.config(
                highlightbackground=col, highlightthickness=2))
            c.bind("<Leave>", lambda e, w=c: w.config(
                highlightbackground="#D5DEE8", highlightthickness=1))
            from . import icons
            img = icons.get(emoji, 72)
            if img is not None:
                tk.Label(c, image=img, bg=CARD).pack(pady=(22, 8))
            else:
                tk.Label(c, text=emoji, bg=CARD, font=(FONT, 44)).pack(
                    pady=(18, 2))
            tk.Label(c, text=sub, bg=CARD, fg=TEXT_MUTED, font=(FONT, 10),
                     justify="center").pack(pady=(0, 12), padx=12)
            BigButton(c, title, command=cmd, color=color, hover=hover,
                      font_size=15, padx=28).pack(pady=(0, 20), padx=20)
        eng = "Video engine: ready" if ff.find_ffmpeg() else \
            "Video engine: MISSING"
        tk.Label(f, text=f"Version {__version__}   ·   Works without "
                         f"internet   ·   Your files stay on your computer"
                         f"   ·   {eng}",
                 bg=BG, fg=TEXT_MUTED, font=(FONT, 9)).pack(side="bottom",
                                                            pady=12)
        self._swap(f)

    def show_about(self):
        return ezupdate.open_about(
            self.root, self.updater,
            {"title": BLUE_DARK, "text": TEXT, "muted": TEXT_MUTED,
             "button": ORANGE, "good": GREEN, "bad": "#C0392B"},
            FONT, extra_lines=("Free video maker and converter for Windows",
                               "by El Szaba  \u00b7  github.com/DrSzaba/ez-video-maker"))

    def show_editor(self):
        from .editor import EditorScreen
        self._swap(EditorScreen(self.root, self))

    def show_converter(self, mode):
        from .converter import ConverterScreen
        self._swap(ConverterScreen(self.root, self, mode=mode))

    def _close(self):
        cur = self.current
        if cur is not None and getattr(cur, "_busy", False):
            if not messagebox.askyesno("Still working",
                                       "A video is still being made. Quit "
                                       "anyway?"):
                return
        if cur is not None and hasattr(cur, "project") and \
                cur.project.dirty and cur.project.clips:
            if messagebox.askyesno("Save first?",
                                   "Save your project before quitting?"):
                cur.save_project()
        if cur is not None and hasattr(cur, "shutdown"):
            try:
                cur.shutdown()
            except Exception:
                pass
        self.root.destroy()
        # an update was downloaded: install it now that the program is closed
        try:
            self.updater.run_pending_setup()
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


def main():
    App().run()
