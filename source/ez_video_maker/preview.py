"""
EZ Video Maker - Preview Monitor.
Shows any video / photo / sound file instantly, plays video with sound
(FFmpeg raw-frame pipe for pictures + bundled ffplay for sound), with
Play / Pause / Stop, a scrub bar, time, volume and full screen.
"""

import os
import queue
import subprocess
import threading
import time
import tkinter as tk

from PIL import Image, ImageTk

from . import ffmpeg_engine as ff
from . import media
from .theme import FONT, ORANGE, BLUE, DARK, DARK2, DARK3, TEXT_MUTED

PLAY_FPS = 15


def fmt_time(t):
    t = max(0, int(t + 0.001))
    if t >= 3600:
        return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"
    return f"{t // 60}:{t % 60:02d}"


class PreviewMonitor(tk.Frame):
    def __init__(self, parent, on_prev=None, on_next=None,
                 on_position=None):
        super().__init__(parent, bg=DARK, bd=1, relief="solid")
        self.on_prev, self.on_next = on_prev, on_next
        self.on_position = on_position    # called with seconds while playing
        self.canvas = tk.Canvas(self, bg=DARK, highlightthickness=0,
                                width=640, height=360)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._resized)
        self.canvas.bind("<Double-Button-1>", lambda e: self.fullscreen())
        self._photo = None
        self._last_img = None
        self._msg_text = "Add videos or photos - they show up here."
        self._draw_message(self._msg_text)

        bar = tk.Frame(self, bg=DARK2)
        bar.pack(fill="x")
        self.pos_var = tk.DoubleVar(value=0)
        self.scrub = tk.Scale(bar, from_=0, to=1000, orient="horizontal",
                              variable=self.pos_var, showvalue=False,
                              bg=DARK2, troughcolor="#22314A",
                              highlightthickness=0, fg="white",
                              activebackground=ORANGE, sliderlength=16,
                              command=self._on_scrub)
        self.scrub.pack(fill="x", padx=8, pady=(4, 0))
        self.scrub.bind("<ButtonPress-1>", lambda e: self._scrub_press())
        self.scrub.bind("<ButtonRelease-1>", lambda e: self._scrub_release())

        row = tk.Frame(bar, bg=DARK2)
        row.pack(fill="x", pady=4)

        def btn(txt, cmd, w=3, size=13):
            return tk.Button(row, text=txt, command=cmd, bg=DARK3,
                             fg="white", activebackground=BLUE,
                             activeforeground="white", relief="flat",
                             font=(FONT, size, "bold"), width=w,
                             cursor="hand2")
        btn("⏮", self._prev).pack(side="left", padx=(8, 2))
        self.play_btn = btn("▶", self.toggle_play, w=5, size=14)
        self.play_btn.pack(side="left", padx=2)
        btn("⏹", self.stop).pack(side="left", padx=2)
        btn("⏭", self._next).pack(side="left", padx=2)
        self.time_lbl = tk.Label(row, text="0:00 / 0:00", bg=DARK2,
                                 fg="white", font=(FONT, 11))
        self.time_lbl.pack(side="left", padx=12)
        self.name_lbl = tk.Label(row, text="", bg=DARK2, fg=TEXT_MUTED,
                                 font=(FONT, 9))
        self.name_lbl.pack(side="left", padx=4)
        btn("⛶", self.fullscreen, w=3).pack(side="right", padx=8)
        self.vol = tk.Scale(row, from_=0, to=100, orient="horizontal",
                            showvalue=False, length=90, bg=DARK2,
                            troughcolor="#22314A", highlightthickness=0,
                            sliderlength=12, activebackground=ORANGE)
        self.vol.set(85)
        self.vol.pack(side="right", padx=4)
        tk.Label(row, text="🔊", bg=DARK2, fg="white",
                 font=(FONT, 11)).pack(side="right")

        self.path = None
        self.offset = 0.0
        self.duration = 0.0
        self.pos = 0.0
        self.playing = False
        self._vproc = None
        self._aproc = None
        self._fs_win = None
        self._fs_canvas = None
        self._fs_photo = None
        self._scrubbing = False
        self._gen = 0
        self._q = queue.Queue()

    # ---------- drawing ----------
    def _resized(self, _=None):
        if self._last_img is not None:
            self._draw_image(self._last_img)
        elif not self.path:
            self._draw_message(self._msg_text)

    def _draw_message(self, text):
        self.canvas.delete("all")
        w = max(2, self.canvas.winfo_width())
        h = max(2, self.canvas.winfo_height())
        self.canvas.create_text(w // 2, h // 2, fill="#5B6B7C",
                                font=(FONT, 13, "italic"), text=text,
                                width=w - 40, justify="center")

    def _draw_image(self, img):
        if img is None:
            self._draw_message("No preview for this file")
            return
        self._last_img = img
        cw = max(2, self.canvas.winfo_width())
        ch = max(2, self.canvas.winfo_height())
        fitted = media.fit_into(img, cw, ch)
        self._photo = ImageTk.PhotoImage(fitted)
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo)
        self._draw_guide(fitted.width, fitted.height, cw, ch)
        if self._fs_canvas is not None:
            try:
                fw = self._fs_canvas.winfo_width()
                fh = self._fs_canvas.winfo_height()
                self._fs_photo = ImageTk.PhotoImage(
                    media.fit_into(img, fw, fh))
                self._fs_canvas.delete("all")
                self._fs_canvas.create_image(fw // 2, fh // 2,
                                             image=self._fs_photo)
            except Exception:
                pass

    # set by the editor: (w, h) of the finished video, or None
    guide_shape = None

    def _draw_guide(self, iw, ih, cw, ch):
        """Safe-area guide: shows where TikTok / Reels put their caption
        and buttons, so words and faces stay clear of them.  Only drawn
        on pictures that already have the finished video's shape."""
        g = self.guide_shape
        if not g or iw < 40 or ih < 40:
            return
        gw, gh = g
        if gh <= gw or abs(iw / ih - gw / gh) > 0.03:
            return
        x0, y0 = (cw - iw) // 2, (ch - ih) // 2
        c = self.canvas
        # zones the app covers: right-hand buttons and bottom caption
        c.create_rectangle(x0 + iw * 0.84, y0 + ih * 0.42, x0 + iw,
                           y0 + ih * 0.84, fill="#000000", stipple="gray25",
                           outline="", tags="guide")
        c.create_rectangle(x0, y0 + ih * 0.80, x0 + iw, y0 + ih,
                           fill="#000000", stipple="gray25", outline="",
                           tags="guide")
        c.create_text(x0 + iw * 0.42, y0 + ih * 0.9, text="caption area",
                      fill="white", font=(FONT, 8, "italic"), tags="guide")
        # safe frame
        c.create_rectangle(x0 + iw * 0.06, y0 + ih * 0.11, x0 + iw * 0.82,
                           y0 + ih * 0.79, outline="#F2811D", width=2,
                           dash=(6, 4), tags="guide")

    def show_image(self, img):
        """Show a PIL image (used by the editor for storyboard frames)."""
        self._draw_image(img)

    # ---------- loading ----------
    def load(self, path, duration=None, autoplay=False, name=None,
             offset=0.0):
        """Show a file. offset/duration limit playback to a part of it
        (used for trimmed clips). pos is always relative to offset."""
        self.stop(redraw=False)
        self.path = path
        self.offset = max(0.0, offset)
        self.name_lbl.config(text=name or os.path.basename(path))
        if media.is_audio(path):
            self.duration = duration or ff.probe_duration(path) or 0.0
            self._draw_image(media.waveform(path, 640, 200))
        elif media.is_image(path):
            self.duration = duration or 5.0
            self._draw_image(media.load_photo(path, 1280))
        else:
            info = ff.probe_info(path)
            full = info.get("duration") or 5.0
            self.duration = duration or max(0.1, full - self.offset)
            self._draw_image(media.grab_frame(path, self.offset, 960))
        self.pos = 0.0
        self._update_time()
        if autoplay:
            self.play()

    def clear(self, text=None):
        self.stop(redraw=False)
        self.path = None
        self.offset = 0.0
        self._last_img = None
        self.duration = 0.0
        self.pos = 0.0
        self.name_lbl.config(text="")
        self._msg_text = text or "Add videos or photos - they show up here."
        self._draw_message(self._msg_text)
        self._update_time()

    # ---------- transport ----------
    def toggle_play(self):
        if self.playing:
            self.pause()
        else:
            self.play()

    def play(self):
        if not self.path or self.playing:
            return
        self.playing = True
        self.play_btn.config(text="⏸")
        self._gen += 1
        gen = self._gen
        start = self.pos if self.pos < self.duration - 0.2 else 0.0
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        vw = max(160, min(960, self.canvas.winfo_width()))
        vh = max(90, min(540, self.canvas.winfo_height()))
        self._play_size = (vw - vw % 2, vh - vh % 2)
        self._volume_now = int(self.vol.get())
        threading.Thread(target=self._video_loop, args=(start, gen),
                         daemon=True).start()
        self.after(30, self._poll)

    def pause(self):
        self.playing = False
        self._gen += 1
        self.play_btn.config(text="▶")
        self._kill_procs()
        self._update_time()

    def stop(self, redraw=True):
        self.playing = False
        self._gen += 1
        self.play_btn.config(text="▶")
        self._kill_procs()
        self.pos = 0.0
        if self.path and redraw and not media.is_audio(self.path):
            self._draw_image(media.grab_frame(self.path, self.offset, 960))
        self._update_time()

    def _prev(self):
        if self.on_prev:
            self.on_prev()

    def _next(self):
        if self.on_next:
            self.on_next()

    def _kill_procs(self):
        for pr in (self._vproc, self._aproc):
            if pr and pr.poll() is None:
                try:
                    pr.kill()
                except Exception:
                    pass
        self._vproc = self._aproc = None
        self._stop_winsound()

    # ---------- sound during playback ----------
    def _has_sound(self):
        if media.is_image(self.path):
            return False
        if media.is_audio(self.path):
            return True
        return bool(ff.probe_info(self.path).get("has_audio"))

    def _prepare_audio(self, start, gen):
        """Runs in the worker thread. Returns a function that starts the
        sound, or None. Windows: decode to a WAV and play it with the
        built-in winsound (no ffplay needed). Elsewhere: ffplay."""
        if not self._has_sound():
            return None
        vol = max(0, min(100, self._volume_now))
        if ff.IS_WIN:
            ffmpeg = ff.find_ffmpeg()
            if not ffmpeg:
                return None
            wav = os.path.join(ff.cache_dir(), f"play_{os.getpid()}.wav")
            length = max(0.5, min(self.duration - start, 1800.0))
            cmd = [ffmpeg, "-hide_banner", "-loglevel", "quiet", "-y"]
            if self.offset + start >= 0.05:
                cmd += ["-ss", f"{self.offset + start:.2f}"]
            cmd += ["-t", f"{length:.2f}", "-i", self.path, "-vn",
                    "-af", f"volume={vol / 100.0:.2f}", "-ac", "2",
                    "-ar", "44100", "-c:a", "pcm_s16le", wav]
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=120,
                               **ff.POPEN_FLAGS)
            except Exception:
                return None
            if self._gen != gen or not os.path.isfile(wav):
                return None

            def go():
                try:
                    import winsound
                    winsound.PlaySound(wav, winsound.SND_FILENAME |
                                       winsound.SND_ASYNC |
                                       winsound.SND_NODEFAULT)
                    self._winsound = True
                except Exception:
                    pass
            return go
        ffplay = ff.find_ffplay()
        if not ffplay:
            return None

        def go():
            try:
                self._aproc = subprocess.Popen(
                    [ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet",
                     "-volume", str(vol),
                     "-ss", f"{self.offset + start:.2f}", "-vn", self.path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL, **ff.POPEN_FLAGS)
            except Exception:
                self._aproc = None
        return go

    def _stop_winsound(self):
        if getattr(self, "_winsound", False):
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
            self._winsound = False

    def _video_loop(self, start, gen):
        """Worker thread: reads frames from ffmpeg and hands them to the
        main thread through a queue (Tk is only touched on the main
        thread)."""
        q = self._q
        is_still = media.is_audio(self.path) or media.is_image(self.path)
        ffmpeg = ff.find_ffmpeg()
        proc = None
        vw, vh = self._play_size
        start_audio = self._prepare_audio(start, gen)
        if self._gen != gen:
            return
        if not is_still and ffmpeg:
            cmd = [ffmpeg, "-hide_banner", "-loglevel", "quiet"]
            if self.offset + start >= 0.05:
                cmd += ["-ss", f"{self.offset + start:.2f}"]
            cmd += ["-i", self.path, "-an",
                    "-vf", f"fps={PLAY_FPS},scale={vw}:{vh}:"
                           f"force_original_aspect_ratio=decrease,"
                           f"pad={vw}:{vh}:(ow-iw)/2:(oh-ih)/2",
                    "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL,
                                        stdin=subprocess.DEVNULL,
                                        bufsize=vw * vh * 3 * 4,
                                        **ff.POPEN_FLAGS)
                self._vproc = proc
            except Exception:
                proc = None
        if start_audio:
            start_audio()
        t0 = time.time()
        frame_i = 0
        need = vw * vh * 3
        while self.playing and self._gen == gen:
            pos = start + (time.time() - t0)
            if pos >= self.duration:
                break
            if proc:
                data = proc.stdout.read(need)
                if not data or len(data) < need:
                    break
                frame_i += 1
                try:
                    img = Image.frombytes("RGB", (vw, vh), data)
                except Exception:
                    break
                q.put(("frame", gen, img, pos))
                target = start + frame_i / PLAY_FPS
                lag = target - (start + (time.time() - t0))
                if lag > 0:
                    time.sleep(min(lag, 0.25))
            else:
                q.put(("tick", gen, None, pos))
                time.sleep(0.1)
        q.put(("done", gen, None, min(start + (time.time() - t0),
                                      self.duration)))

    def _poll(self):
        """Main thread: paint frames the worker produced."""
        gen_alive = self.playing
        try:
            while True:
                kind, gen, img, pos = self._q.get_nowait()
                if gen != self._gen:
                    continue
                if kind == "frame":
                    self.pos = pos
                    self._draw_image(img)
                    self._tick(gen)
                elif kind == "tick":
                    self.pos = pos
                    self._tick(gen)
                elif kind == "done":
                    self.pos = pos
                    self._finished(gen)
                    gen_alive = False
        except queue.Empty:
            pass
        if gen_alive and self.playing and self.winfo_exists():
            self.after(30, self._poll)

    def _tick(self, gen):
        if self._gen != gen:
            return
        self._update_time()
        if self.on_position:
            self.on_position(self.pos)

    def _finished(self, gen):
        if self._gen != gen:
            return
        self.playing = False
        self.play_btn.config(text="▶")
        self._kill_procs()
        self.pos = min(self.pos, self.duration)
        self._update_time()

    # ---------- scrub / time ----------
    def _update_time(self):
        self.time_lbl.config(text=f"{fmt_time(self.pos)} / "
                                  f"{fmt_time(self.duration)}")
        if self.duration > 0 and not self._scrubbing:
            self.pos_var.set(self.pos / self.duration * 1000)

    def _scrub_press(self):
        self._scrubbing = True
        if self.playing:
            self.pause()

    def _scrub_release(self):
        self._scrubbing = False
        self._seek(self.pos_var.get() / 1000.0 * self.duration)

    def _on_scrub(self, val):
        if not self.path or not self._scrubbing:
            return
        self.pos = float(val) / 1000.0 * self.duration
        self.time_lbl.config(text=f"{fmt_time(self.pos)} / "
                                  f"{fmt_time(self.duration)}")

    def _seek(self, t):
        if not self.path:
            return
        self.pos = max(0.0, min(t, self.duration))
        if not media.is_audio(self.path) and not media.is_image(self.path):
            self._draw_image(media.grab_frame(self.path,
                                              self.offset + self.pos, 960))
        self._update_time()
        if self.on_position:
            self.on_position(self.pos)

    def seek(self, t):
        self._seek(t)

    # ---------- fullscreen ----------
    def fullscreen(self):
        if self._fs_win:
            self._close_fs()
            return
        self._fs_win = tk.Toplevel(self)
        self._fs_win.attributes("-fullscreen", True)
        self._fs_win.configure(bg="black")
        self._fs_canvas = tk.Canvas(self._fs_win, bg="black",
                                    highlightthickness=0)
        self._fs_canvas.pack(fill="both", expand=True)
        tk.Label(self._fs_win, text="Press Esc or double-click to leave "
                                    "full screen  ·  Space = play/pause",
                 bg="black", fg="#666").place(relx=0.5, rely=0.97,
                                              anchor="center")
        self._fs_win.bind("<Escape>", lambda e: self._close_fs())
        self._fs_win.bind("<space>", lambda e: self.toggle_play())
        self._fs_canvas.bind("<Double-Button-1>", lambda e: self._close_fs())
        self._fs_win.update_idletasks()
        if self._last_img is not None:
            self._draw_image(self._last_img)

    def _close_fs(self):
        if self._fs_win:
            try:
                self._fs_win.destroy()
            except Exception:
                pass
        self._fs_win = self._fs_canvas = None

    def shutdown(self):
        self.playing = False
        self._gen += 1
        self._kill_procs()
        self._close_fs()
