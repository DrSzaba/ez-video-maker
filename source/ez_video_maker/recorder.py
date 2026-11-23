"""
EZ Video Maker - microphone recording (voiceover) through FFmpeg.
Windows uses DirectShow; Linux/mac fall back to PulseAudio / AVFoundation.
"""

import os
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk, messagebox

from . import ffmpeg_engine as ff
from .theme import (FONT, CARD, TEXT, TEXT_MUTED, BLUE, RED, BigButton,
                    RoundButton, GhostButton)


def list_microphones():
    ffmpeg = ff.find_ffmpeg()
    if not ffmpeg:
        return []
    if ff.IS_WIN:
        try:
            r = subprocess.run([ffmpeg, "-hide_banner", "-list_devices",
                                "true", "-f", "dshow", "-i", "dummy"],
                               capture_output=True, text=True, timeout=20,
                               encoding="utf-8", errors="replace",
                               **ff.POPEN_FLAGS)
            mics = []
            for ln in r.stderr.splitlines():
                if "(audio)" in ln and '"' in ln:
                    name = ln.split('"')[1]
                    if name not in mics:
                        mics.append(name)
            return mics
        except Exception:
            return []
    if sys.platform == "darwin":
        return ["Default microphone"]
    return ["Default microphone"]


def record_args(mic_name, out_path):
    ffmpeg = ff.find_ffmpeg()
    base = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if ff.IS_WIN:
        base += ["-f", "dshow", "-i", f"audio={mic_name}"]
    elif sys.platform == "darwin":
        base += ["-f", "avfoundation", "-i", ":0"]
    else:
        base += ["-f", "pulse", "-i", "default"]
    base += ["-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", out_path]
    return base


def recordings_dir():
    d = os.path.join(os.path.expanduser("~"), "Videos")
    if not os.path.isdir(d):
        d = os.path.expanduser("~")
    d = os.path.join(d, "EZ Video Maker Recordings")
    os.makedirs(d, exist_ok=True)
    return d


def join_segments(segments, out_path):
    """Join the recorded pieces (pause/resume) into one WAV file."""
    segments = [p for p in segments if os.path.isfile(p) and
                os.path.getsize(p) > 1000]
    if not segments:
        return None
    if len(segments) == 1:
        import shutil
        shutil.copyfile(segments[0], out_path)
        return out_path
    listfile = out_path + ".txt"
    with open(listfile, "w", encoding="utf-8") as fh:
        for p in segments:
            fh.write("file '" + p.replace("\\", "/").replace("'", r"'\''")
                     + "'\n")
    r = subprocess.run([ff.find_ffmpeg(), "-hide_banner", "-loglevel", "error",
                        "-y", "-f", "concat", "-safe", "0", "-i", listfile,
                        "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le",
                        out_path], capture_output=True, **ff.POPEN_FLAGS)
    try:
        os.remove(listfile)
    except OSError:
        pass
    return out_path if r.returncode == 0 and os.path.isfile(out_path) \
        else None


class RecordDialog(tk.Toplevel):
    """Record a voiceover with one big red button: 3-2-1 countdown,
    pause / resume as often as you like, then Stop and use it.
    Microphone only.  When done, calls on_done(path)."""

    def __init__(self, parent, on_done):
        super().__init__(parent)
        self.title("Record your voice")
        self.configure(bg=CARD)
        self.resizable(False, False)
        self.on_done = on_done
        self.proc = None
        self.segments = []
        self.state = "idle"        # idle / countdown / recording / paused
        self.recorded = 0.0        # seconds in finished pieces
        self.t0 = None
        self.tmp = tempfile.mkdtemp(prefix="ezvm_rec_")
        mics = list_microphones()
        tk.Label(self, text="🎙  Record your voice", bg=CARD, fg=TEXT,
                 font=(FONT, 15, "bold")).pack(pady=(16, 4), padx=24)
        if not mics:
            tk.Label(self, text="No microphone was found.\nPlug one in and "
                                "try again, or use 'Voice file'.",
                     bg=CARD, fg=TEXT_MUTED, font=(FONT, 11),
                     justify="center").pack(pady=10, padx=24)
            BigButton(self, "OK", command=self.destroy, color=BLUE,
                      font_size=11, pady=8).pack(pady=(4, 16))
            self.grab_set()
            return
        tk.Label(self, text="Microphone:", bg=CARD, fg=TEXT,
                 font=(FONT, 11)).pack()
        self.mic_var = tk.StringVar(value=mics[0])
        ttk.Combobox(self, textvariable=self.mic_var, values=mics,
                     state="readonly", width=44).pack(pady=(2, 8), padx=24)
        self.status = tk.Label(self, text="Press the big red button. "
                                          "You get a 3-2-1 countdown.",
                               bg=CARD, fg=TEXT_MUTED, font=(FONT, 11))
        self.status.pack(pady=4)
        self.timer = tk.Label(self, text="0:00", bg=CARD, fg=TEXT,
                              font=(FONT, 30, "bold"))
        self.timer.pack()
        self.big = RoundButton(self, text="●\nRECORD", command=self.big_press,
                             bg=RED, fg="white", activebackground="#922B21",
                             activeforeground="white", relief="flat", bd=0,
                             font=(FONT, 16, "bold"), width=9, height=3,
                             cursor="hand2", radius=28, pady=10)
        self.big.pack(pady=10)
        row = tk.Frame(self, bg=CARD)
        row.pack(pady=(0, 6))
        self.stop_btn = BigButton(row, "■  Stop and use it",
                                  command=self.finish, color=BLUE,
                                  font_size=12, pady=8)
        self.stop_btn.config(state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        GhostButton(self, "Cancel", command=self.cancel,
                    font_size=10).pack(pady=(0, 12))
        tk.Label(self, text="Microphone only - never your camera or screen.",
                 bg=CARD, fg=TEXT_MUTED, font=(FONT, 9, "italic")
                 ).pack(pady=(0, 10))
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.grab_set()

    # ---------------- the big button ----------------
    def big_press(self):
        if self.state in ("idle", "paused"):
            self._countdown(3)
        elif self.state == "recording":
            self.pause()

    def _countdown(self, n):
        self.state = "countdown"
        self.big.config(state="disabled")
        if n > 0:
            self.timer.config(text=str(n), fg=RED)
            self.status.config(text="Get ready…", fg=RED)
            self.after(1000, lambda: self._countdown(n - 1))
        else:
            self.big.config(state="normal")
            self._start_piece()

    def _start_piece(self):
        out = os.path.join(self.tmp, f"piece{len(self.segments):03d}.wav")
        try:
            self.proc = subprocess.Popen(
                record_args(self.mic_var.get(), out), stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                **ff.POPEN_FLAGS)
        except Exception as e:
            self.state = "idle" if not self.segments else "paused"
            messagebox.showerror("Recording problem",
                                 f"Could not start recording:\n{e}",
                                 parent=self)
            return
        self.segments.append(out)
        self.t0 = time.time()
        self.state = "recording"
        self.status.config(text="● Recording… speak now!", fg=RED)
        self.big.config(text="❚❚\nPAUSE", bg="#B9770E",
                        activebackground="#9A6408")
        self.stop_btn.config(state="normal")
        self._tick()

    def pause(self):
        self._stop_proc()
        if self.t0:
            self.recorded += time.time() - self.t0
        self.t0 = None
        self.state = "paused"
        self.status.config(text="Paused. Press RESUME to keep going, or "
                                "Stop and use it.", fg=TEXT_MUTED)
        self.big.config(text="●\nRESUME", bg=RED,
                        activebackground="#922B21")
        self._show_time()

    def _show_time(self):
        s = int(self.recorded + (time.time() - self.t0 if self.t0 else 0))
        self.timer.config(text=f"{s // 60}:{s % 60:02d}", fg=TEXT)

    def _tick(self):
        if self.state == "recording" and self.proc and \
                self.proc.poll() is None:
            self._show_time()
            self.after(250, self._tick)

    def _stop_proc(self):
        p = self.proc
        if p and p.poll() is None:
            try:
                p.stdin.write(b"q")
                p.stdin.flush()
                p.wait(timeout=5)
            except Exception:
                p.kill()
        self.proc = None

    def finish(self):
        if self.state == "recording":
            self.pause()
        name = time.strftime("Voice %Y-%m-%d %H-%M-%S.wav")
        out = join_segments(self.segments, os.path.join(recordings_dir(),
                                                         name))
        if out and os.path.getsize(out) > 2000:
            self.destroy()
            self.on_done(out)
        else:
            self.status.config(text="Nothing was recorded. Try again.",
                               fg=TEXT_MUTED)
            self.state = "idle"
            self.segments = []
            self.recorded = 0.0
            self.big.config(text="●\nRECORD", bg=RED)
            self.stop_btn.config(state="disabled")

    def cancel(self):
        self._stop_proc()
        self.destroy()
