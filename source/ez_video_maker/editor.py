"""
EZ Video Maker - "Make a Video" screen.
Movie-Maker simple: pick a shape (TikTok vertical / YouTube horizontal),
drop clips on the storyboard, click a clip to see it, use the tools on the
right, press Save My Video.
"""

import copy
import os
import queue
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import ImageTk

from . import ffmpeg_engine as ff
from . import media
from . import icons
from .dialogs import (TrimDialog, SplitDialog, CropDialog, TextDialog,
                      SizeDialog, AudioDialog, PhotoLengthDialog)
from .export import Exporter, ExportCancelled
from .model import (Project, COLOR_STYLES, TRANSITIONS, TEXT_STYLES, SPEEDS,
                    TRANSITION_GROUPS, TRANSITION_MIN, TRANSITION_MAX,
                    MOTIONS, EFFECTS, Clip)
from .preview import PreviewMonitor, fmt_time
from .recorder import RecordDialog
from .whatsapp import (WhatsAppDialog, WHATSAPP_GREEN,
                       pick_files as pick_wa_files)
from .theme import (FONT, BG, PANEL, CARD, LINE, BLUE, BLUE_DARK, BLUE_LIGHT,
                    ORANGE, ORANGE_DARK, ORANGE_LIGHT, TEXT, TEXT_MUTED,
                    GREEN, RED, SILVER, PURPLE, PINK, TEAL, DARK2, DARK3,
                    BigButton, GhostButton, ToggleButton, RoundButton,
                    Equalizer, card, header_bar, label, hscale)
from . import preview as _preview


class _TkWithRoundButtons:
    """tkinter, but with the modern rounded buttons - so the preview
    monitor's play / pause / stop buttons get the new look too."""
    Button = RoundButton

    def __getattr__(self, name):
        return getattr(tk, name)


_preview.tk = _TkWithRoundButtons()

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except Exception:
    HAS_DND = False

CARD_W, CARD_H = 168, 142
THUMB_W, THUMB_H = 158, 89


class Storyboard(tk.Frame):
    """Horizontal strip of clip cards. Click = select, drag = reorder."""

    def __init__(self, parent, project, on_select, on_reorder):
        super().__init__(parent, bg=PANEL)
        self.project = project
        self.on_select = on_select
        self.on_reorder = on_reorder
        self.selected_id = None
        self._photos = {}
        self._drag = None
        self.canvas = tk.Canvas(self, bg=PANEL, height=CARD_H + 24,
                                highlightthickness=0)
        self.canvas.pack(fill="x", side="top")
        self.scroll = tk.Scrollbar(self, orient="horizontal",
                                   command=self.canvas.xview)
        self.scroll.pack(fill="x", side="bottom")
        self.canvas.configure(xscrollcommand=self.scroll.set)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.xview_scroll(
            -1 if e.delta > 0 else 1, "units"))
        self.canvas.bind("<Button-4>", lambda e: self.canvas.xview_scroll(
            -1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.xview_scroll(
            1, "units"))

    def _x_of(self, index):
        return 12 + index * (CARD_W + 14)

    def refresh(self):
        c = self.canvas
        c.delete("all")
        clips = self.project.clips
        if not clips:
            c.create_text(20, CARD_H // 2 + 8, anchor="w", fill=TEXT_MUTED,
                          font=(FONT, 12, "italic"),
                          text="Your storyboard is empty.  Click  Add videos  "
                               "or  Add photos  at the top (or drag files "
                               "here).")
            c.configure(scrollregion=(0, 0, 600, CARD_H + 24))
            return
        y = 8
        for i, clip in enumerate(clips):
            x = self._x_of(i)
            sel = clip.id == self.selected_id
            c.create_rectangle(x, y, x + CARD_W, y + CARD_H,
                               fill=ORANGE_LIGHT if sel else CARD,
                               outline=ORANGE if sel else "#C9D3DE",
                               width=3 if sel else 1, tags=("card", clip.id))
            img = media.thumbnail(clip.path, THUMB_W, THUMB_H,
                                  t=clip.in_point + 0.2 if clip.kind == "video"
                                  else 0)
            ph = ImageTk.PhotoImage(img)
            self._photos[clip.id] = ph
            c.create_image(x + CARD_W // 2, y + 6 + THUMB_H // 2, image=ph,
                           tags=("card", clip.id))
            c.create_text(x + 6, y + THUMB_H + 12, anchor="nw", fill=TEXT,
                          font=(FONT, 9, "bold"), text=f"{i + 1}. " +
                          (clip.name[:18] + "…" if len(clip.name) > 19
                           else clip.name), tags=("card", clip.id))
            c.create_text(x + 6, y + THUMB_H + 28, anchor="nw", fill=TEXT_MUTED,
                          font=(FONT, 8), text=clip.describe()[:26],
                          tags=("card", clip.id))
            if i > 0 and clip.transition != "Cut":
                c.create_oval(x - 13, y + THUMB_H // 2 - 4, x - 1,
                              y + THUMB_H // 2 + 8, fill=BLUE, outline="")
            badge = "📷" if clip.is_photo else "🎬"
            c.create_text(x + CARD_W - 8, y + 8, anchor="ne", text=badge,
                          font=(FONT, 10), tags=("card", clip.id))
        c.configure(scrollregion=(0, 0, self._x_of(len(clips)) + 12,
                                  CARD_H + 24))

    def _index_at(self, x):
        x = self.canvas.canvasx(x)
        for i in range(len(self.project.clips)):
            if self._x_of(i) - 7 <= x < self._x_of(i) + CARD_W + 7:
                return i
        return None

    def _press(self, e):
        i = self._index_at(e.x)
        if i is None:
            return
        clip = self.project.clips[i]
        self.selected_id = clip.id
        self._drag = (i, e.x)
        self.refresh()
        self.on_select(clip)

    def _motion(self, e):
        if self._drag and abs(e.x - self._drag[1]) > 8:
            self.canvas.config(cursor="exchange")

    def _release(self, e):
        self.canvas.config(cursor="")
        if not self._drag:
            return
        i0, x0 = self._drag
        self._drag = None
        if abs(e.x - x0) < 8:
            return
        target = self._index_at(e.x)
        if target is None:
            cx = self.canvas.canvasx(e.x)
            target = 0 if cx < self._x_of(0) else len(self.project.clips) - 1
        if target != i0:
            self.on_reorder(self.project.clips[i0].id, target)

    def select(self, clip_id):
        self.selected_id = clip_id
        self.refresh()
        i, _ = self.project.find_clip(clip_id) if clip_id else (None, None)
        if i is not None:
            total = self._x_of(len(self.project.clips)) + 12
            self.canvas.xview_moveto(max(0, (self._x_of(i) - 40) / total))


SONG_COLORS = ("#2E9E57", "#F2811D", "#8E44AD", "#D35400", "#16A085",
               "#C0392B")


class MusicStrip(tk.Frame):
    """A timeline under the storyboard: the video on top, the songs
    underneath, both drawn to the same scale - so you can see at a glance
    whether the music fits the video."""

    H = 74

    def __init__(self, parent, project, on_pick_song):
        super().__init__(parent, bg=PANEL)
        self.project = project
        self.on_pick_song = on_pick_song
        self.canvas = tk.Canvas(self, bg=CARD, height=self.H,
                                highlightthickness=1,
                                highlightbackground="#D5DEE8")
        self.canvas.pack(fill="x")
        self.canvas.bind("<Configure>", lambda e: self.refresh())
        self.canvas.bind("<ButtonPress-1>", self._click)
        self._song_boxes = []

    def refresh(self):
        c = self.canvas
        c.delete("all")
        self._song_boxes = []
        p = self.project
        W = max(300, c.winfo_width())
        L, R = 96, 62
        songs = [a for a in p.audios if a.kind == "music" and a.duration]
        clips_len = p.clips_duration()
        music_end = p.music_length() or 0.0
        total = max(p.total_duration(), clips_len, music_end, 1.0)
        scale = (W - L - R) / total

        def X(t):
            return L + t * scale
        c.create_text(10, 20, anchor="w", text="🎬 Video", fill=BLUE_DARK,
                      font=(FONT, 10, "bold"))
        c.create_text(10, 52, anchor="w", text="🎵 Music", fill=BLUE_DARK,
                      font=(FONT, 10, "bold"))
        # video row
        if p.clips:
            for i, clip in enumerate(p.clips):
                s0 = p.clip_start(i)
                c.create_rectangle(X(s0), 10, X(s0 + clip.duration), 30,
                                   fill=BLUE if i % 2 == 0 else "#3D86CC",
                                   outline=CARD)
            hold = p.hold_seconds()
            if hold > 0:
                c.create_rectangle(X(clips_len), 10, X(clips_len + hold), 30,
                                   fill="#C9D9EA", outline=CARD)
                if X(clips_len + hold) - X(clips_len) > 230:
                    c.create_text((X(clips_len) + X(clips_len + hold)) / 2, 20,
                                  text="last picture stays on screen until "
                                       "the music ends",
                                  fill=BLUE_DARK, font=(FONT, 8, "italic"))
            c.create_text(W - 8, 20, anchor="e", fill=BLUE_DARK,
                          font=(FONT, 8, "bold"),
                          text=fmt_time(p.total_duration()))
        else:
            c.create_text(L, 20, anchor="w", fill=TEXT_MUTED,
                          font=(FONT, 9, "italic"), text="no clips yet")
        # music row
        if songs:
            for k, a in enumerate(songs):
                length = max(0.1, a.duration - a.trim_start)
                end = a.start + length
                col = SONG_COLORS[k % len(SONG_COLORS)]
                x0, x1 = X(a.start), X(end)
                c.create_rectangle(x0, 42, x1, 62, fill=col, outline=CARD)
                name = os.path.splitext(a.name)[0]
                room = int((x1 - x0) / 7)
                if room > 3:
                    c.create_text(x0 + 6, 52, anchor="w", fill="white",
                                  font=(FONT, 8, "bold"),
                                  text=(name if len(name) <= room
                                        else name[:max(1, room - 1)] + "…"))
                self._song_boxes.append((x0, x1, a.id))
                if a.loop and len(songs) == 1 and end < clips_len - 0.05:
                    c.create_rectangle(x1, 46, X(clips_len), 58, fill=col,
                                       outline=CARD)
            cut = (not p.play_whole_song) and music_end > clips_len + 0.05
            if cut and p.clips:
                c.create_line(X(clips_len), 6, X(clips_len), 68, fill=RED,
                              width=2, dash=(4, 2))
                c.create_text(X(clips_len) - 4, 70, anchor="se", fill=RED,
                              font=(FONT, 8, "bold"),
                              text="music fades out here")
        else:
            c.create_text(L, 52, anchor="w", fill=TEXT_MUTED,
                          font=(FONT, 9, "italic"),
                          text="no music yet - click  Add music  at the top (add "
                               "several songs and they play one after "
                               "another)")

    def _click(self, e):
        for x0, x1, aid in self._song_boxes:
            if x0 <= e.x <= x1 and 38 <= e.y <= 66:
                self.on_pick_song(aid)
                return


class EditorScreen(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self.project = Project()
        self._busy = False
        self._exporter = None
        self._draft_path = None

        header_bar(self, "Make a Video", on_back=self._go_home)
        self._build_ribbon()
        self._build_status_bar()          # packed at the bottom first
        self._build_storyboard()

        mid = tk.Frame(self, bg=BG)
        mid.pack(fill="both", expand=True, padx=8, pady=(6, 0))
        self.monitor = PreviewMonitor(mid, on_prev=lambda: self._step(-1),
                                      on_next=lambda: self._step(1))
        self.monitor.pack(side="left", fill="both", expand=True)
        self._dress_monitor()
        self._build_tools(mid)

        top = self.winfo_toplevel()
        self._binds = [
            ("<Delete>", lambda e: self._if_not_typing(e, self.tool_delete)),
            ("<Control-z>", lambda e: self.tool_undo()),
            ("<Control-y>", lambda e: self.tool_redo()),
            ("<Control-s>", lambda e: self.save_project()),
            ("<space>", lambda e: self._if_not_typing(
                e, self.monitor.toggle_play)),
        ]
        for seq, fn in self._binds:
            top.bind(seq, fn)
        if HAS_DND:
            for w in (self.storyboard.canvas, self.monitor.canvas):
                try:
                    w.drop_target_register(DND_FILES)
                    w.dnd_bind("<<Drop>>", self._on_drop)
                except Exception:
                    pass
        self.refresh_all()

    def _dress_monitor(self):
        """Orange play button and a little equalizer that dances while
        music or a video is playing."""
        m = self.monitor
        try:
            m.play_btn.config(bg=ORANGE, activebackground=ORANGE_DARK,
                              radius=14)
            row = m.time_lbl.master

            def playing():
                return bool(m.playing and m.path and
                            not media.is_image(m.path))
            self.eq = Equalizer(row, playing, bars=18, segs=8, width=150,
                                height=28, bg=DARK2)
            self.eq.pack(side="left", padx=(10, 2), before=m.time_lbl)
            # keep the play / pause bar visible on short screens too
            bar = m.scrub.master
            bar.pack_forget()
            bar.pack(side="bottom", fill="x", before=m.canvas)
        except Exception:
            pass

    @staticmethod
    def _if_not_typing(event, fn):
        w = event.widget
        if isinstance(w, (tk.Entry, tk.Text, tk.Spinbox, ttk.Entry,
                          ttk.Combobox)):
            return
        fn()

    # ================= building =================
    def _build_ribbon(self):
        """Movie-Maker-style ribbon: the everyday actions as big picture
        buttons, in labelled groups, always in the same place."""
        rib = tk.Frame(self, bg=CARD, highlightthickness=1,
                       highlightbackground=LINE)
        rib.pack(fill="x")
        row = tk.Frame(rib, bg=CARD)
        row.pack(fill="x", padx=6, pady=(6, 0))

        def group(caption, side="left"):
            # the right-hand group (Save & share) is packed first, so it
            # always keeps its room on smaller screens
            first = row.winfo_children()[0] if (
                side == "right" and row.winfo_children()) else None
            extra = {"before": first} if first is not None else {}
            g = tk.Frame(row, bg=CARD)
            g.pack(side=side, fill="y", padx=(4, 4), **extra)
            body = tk.Frame(g, bg=CARD)
            body.pack(side="top", fill="both", expand=True)
            tk.Label(g, text=caption, bg=CARD, fg=TEXT_MUTED,
                     font=(FONT, 8)).pack(side="bottom", pady=(2, 4))
            sep = tk.Frame(row, bg=LINE, width=1)
            sep.pack(side=side, fill="y", pady=(4, 8), **extra)
            return body

        def big(parent, emoji, text, cmd, accent=None):
            """A rounded picture tile: brushed silver, or glossy colour
            for the most important buttons."""
            img = icons.get(emoji, 28)
            b = RoundButton(parent, text=text, image=img, compound="top",
                            command=cmd, bg=accent or SILVER,
                            fg="white" if accent else TEXT,
                            font=(FONT, 9, "bold"), padx=5, pady=4,
                            radius=12, justify="center", width=52)
            if img is None:
                b.config(text=emoji + "\n" + text)
            b.pack(side="left", fill="y", padx=1, pady=(0, 1))
            return b

        def small(parent, emoji, text, cmd):
            img = icons.get(emoji, 16)
            b = RoundButton(parent, text=" " + text, image=img,
                            compound="left", command=cmd, bg=SILVER,
                            fg=TEXT, font=(FONT, 9, "bold"), anchor="w",
                            padx=6, pady=2, radius=8, shadow=False,
                            width=88)
            if img is None:
                b.config(text=emoji + " " + text)
            return b

        # --- Project
        g = group("Project")
        col = tk.Frame(g, bg=CARD)
        col.pack(side="left", fill="y")
        for emoji, txt, cmd in [("📄", "New", self.new_project),
                                ("📂", "Open", self.open_project),
                                ("💾", "Save project", self.save_project)]:
            small(col, emoji, txt, cmd).pack(fill="x", pady=1)
        col = tk.Frame(g, bg=CARD)
        col.pack(side="left", fill="y")
        for emoji, txt, cmd in [("↩️", "Undo", self.tool_undo),
                                ("↪️", "Redo", self.tool_redo)]:
            small(col, emoji, txt, cmd).pack(fill="x", pady=1, padx=(3, 0))
        # --- Add
        g = group("Add")
        big(g, "🎬", "Add\nvideos", self.add_videos)
        big(g, "🖼️", "Add\nphotos", self.add_photos)
        big(g, "🎵", "Add\nmusic", lambda: self.add_audio("music"))
        big(g, "🎙️", "Record\nvoice", self.record_voice)
        # --- Words
        g = group("Words on screen")
        for emoji, txt, style in [("🔤", "Title", TEXT_STYLES[0]),
                                  ("💬", "Caption", TEXT_STYLES[1]),
                                  ("📜", "Credits", TEXT_STYLES[2])]:
            big(g, emoji, txt, lambda st=style: self.add_text(st))
        # --- Music
        g = group("Music")
        big(g, "🎼", "Fit to\nmusic", self.fit_to_music, accent=PINK)
        big(g, "🎬", "Fit music\nto video", self.fit_to_video,
            accent=PURPLE)
        big(g, "🎚️", "Music &\nsound", lambda: self._show_tab("Music"))
        big(g, "📱", "WhatsApp\n→ MP3", self.whatsapp_audio,
            accent=WHATSAPP_GREEN)
        # --- Video shape
        g = group("Video shape")
        grid = tk.Frame(g, bg=CARD)
        grid.pack(side="left", fill="y")
        self.shape_btns = {}
        for i, (lbl, key) in enumerate([
                ("📱 TikTok 9:16", ff.SHAPE_VERTICAL),
                ("🖥 YouTube 16:9", ff.SHAPE_HORIZONTAL),
                ("⬜ Square 1:1", ff.SHAPE_SQUARE),
                ("▯ Post 4:5", ff.SHAPE_45)]):
            b = ToggleButton(grid, lbl, font_size=9,
                             command=lambda k=key: self.set_shape(k))
            b.config(padx=6, pady=3, width=12, anchor="w")
            b.grid(row=i % 2, column=i // 2, padx=1, pady=1, sticky="ew")
            self.shape_btns[key] = b
        side = tk.Frame(g, bg=CARD)
        side.pack(side="left", fill="y", padx=(6, 0))
        self.more_btn = small(side, "📐", "More shapes ▾", self._more_shapes)
        self.more_btn.pack(anchor="w")
        self.shape_lbl = tk.Label(side, text="", bg=CARD, fg=TEXT_MUTED,
                                  font=(FONT, 8))
        self.shape_lbl.pack(anchor="w", padx=6)
        self.fit_var = tk.StringVar(value=self.project.fit_mode)
        fb = ttk.Combobox(side, textvariable=self.fit_var, state="readonly",
                          width=24, font=(FONT, 8), values=ff.FIT_MODES)
        fb.pack(anchor="w", padx=4, pady=(2, 0))
        fb.bind("<<ComboboxSelected>>", lambda e: self._set_fit())
        # --- Share (right side)
        g = group("Save & share", side="right")
        big(g, "▶️", "Play whole\nvideo", self.play_whole, accent=BLUE)
        save = tk.Frame(g, bg=CARD)
        save.pack(side="left", fill="y", padx=(4, 0))
        self.save_btn = BigButton(save, "  Save My Video",
                                  command=self.export, color=ORANGE,
                                  font_size=12, pady=6, padx=12)
        img = icons.get("💾", 22)
        if img is not None:
            self.save_btn.config(image=img, compound="left")
        self.save_btn.pack(fill="x")
        q = tk.Frame(save, bg=CARD)
        q.pack(fill="x", pady=(4, 0))
        tk.Label(q, text="Quality:", bg=CARD, fg=TEXT,
                 font=(FONT, 9)).pack(side="left")
        self.quality_var = tk.StringVar(value=self.project.quality)
        qb = ttk.Combobox(q, textvariable=self.quality_var, state="readonly",
                          width=12, values=list(ff.QUALITY_PRESETS.keys()))
        qb.pack(side="left", padx=4)
        qb.bind("<<ComboboxSelected>>", lambda e: setattr(
            self.project, "quality", self.quality_var.get()))
        self.k4_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(save, text="Upscale to 4K (sharp)",
                        variable=self.k4_var, style="Card.TCheckbutton",
                        command=self._set_4k).pack(anchor="w")

    def _show_tab(self, word):
        for tab in self.nb.tabs():
            if word in self.nb.tab(tab, "text"):
                self.nb.select(tab)
                return

    def _build_tools(self, parent):
        right = tk.Frame(parent, bg=BG, width=470)
        right.pack(side="left", fill="y", padx=(8, 0))
        right.pack_propagate(False)
        self.nb = ttk.Notebook(right)
        self.nb.pack(fill="both", expand=True)
        self._build_clip_tab()
        self._build_anim_tab()
        self._build_look_tab()
        self._build_sound_tab()
        self._build_words_tab()

    def _tab(self, name):
        """A tab whose contents scroll if the window is short."""
        f = tk.Frame(self.nb, bg=CARD)
        self.nb.add(f, text=name)
        cv = tk.Canvas(f, bg=CARD, highlightthickness=0)
        sb = ttk.Scrollbar(f, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        holder = tk.Frame(cv, bg=CARD)
        win = cv.create_window(0, 0, window=holder, anchor="nw")
        inner = tk.Frame(holder, bg=CARD)
        inner.pack(fill="both", expand=True, padx=10, pady=8)

        def sync(_=None):
            cv.configure(scrollregion=cv.bbox("all"))
            cv.itemconfigure(win, width=cv.winfo_width())
            need = holder.winfo_reqheight() > cv.winfo_height() + 2
            if need and not sb.winfo_ismapped():
                sb.pack(side="right", fill="y")
            elif not need and sb.winfo_ismapped():
                sb.pack_forget()
        holder.bind("<Configure>", sync)
        cv.bind("<Configure>", sync)

        def wheel(e):
            if sb.winfo_ismapped():
                d = -1 if (getattr(e, "delta", 0) > 0 or e.num == 4) else 1
                cv.yview_scroll(d, "units")
        for w in (cv, holder, inner):
            w.bind("<MouseWheel>", wheel)
            w.bind("<Button-4>", wheel)
            w.bind("<Button-5>", wheel)
        return inner

    def _build_clip_tab(self):
        t = self._tab("✂ Edit")
        self.clip_title = tk.Label(t, text="Click a clip below to edit it",
                                   bg=CARD, fg=BLUE_DARK,
                                   font=(FONT, 11, "bold"), wraplength=390,
                                   justify="left")
        self.clip_title.pack(anchor="w", pady=(0, 6))
        grid = tk.Frame(t, bg=CARD)
        grid.pack(fill="x")
        btns = [("✂ Trim\n(start / end)", self.tool_trim),
                ("✂ Split\nin two", self.tool_split),
                ("⏱ Photo\ntime", self.tool_photo_time),
                ("↻ Rotate\n90°", self.tool_rotate),
                ("⇄ Flip\nsideways", lambda: self.tool_flip("h")),
                ("⬚ Crop\nedges", self.tool_crop),
                ("❐ Duplicate", self.tool_duplicate),
                ("🎵 Fit to\nmusic", self.fit_to_music),
                ("🎬 Fit music\nto video", self.fit_to_video),
                ("✖ Remove", self.tool_delete)]
        for i, (txt, cmd) in enumerate(btns):
            fit = txt.startswith(("🎵 Fit", "🎬 Fit"))
            b = RoundButton(grid, text=txt, command=cmd,
                            bg=(PINK if txt.startswith("🎵") else PURPLE)
                            if fit else SILVER,
                            fg="white" if fit else BLUE_DARK,
                            font=(FONT, 9, "bold"), width=12, height=2,
                            pady=4)
            b.grid(row=i // 3, column=i % 3, padx=2, pady=2, sticky="ew")
        for col in range(3):
            grid.columnconfigure(col, weight=1)
        row = tk.Frame(t, bg=CARD)
        row.pack(fill="x", pady=(10, 2))
        label(row, "Speed:").pack(side="left")
        self.speed_var = tk.StringVar(value="1")
        sp = ttk.Combobox(row, textvariable=self.speed_var, state="readonly",
                          width=8, values=[f"{s:g}" for s in SPEEDS])
        sp.pack(side="left", padx=6)
        sp.bind("<<ComboboxSelected>>", lambda e: self._set_clip(
            speed=float(self.speed_var.get())))
        label(row, "x   (0.5 = slow motion, 2 = fast)", muted=True,
              size=9).pack(side="left")
        row = tk.Frame(t, bg=CARD)
        row.pack(fill="x", pady=2)
        label(row, "Clip sound:").pack(side="left")
        self.vol_var = tk.DoubleVar(value=100)
        self.vol_scale = hscale(row, 0, 100, self.vol_var, length=150)
        self.vol_scale.pack(side="left", padx=6)
        self.vol_scale.bind("<ButtonRelease-1>", lambda e: self._set_clip(
            volume=self.vol_var.get() / 100.0))
        self.mute_var = tk.BooleanVar()
        ttk.Checkbutton(row, text="Mute", variable=self.mute_var,
                        style="Card.TCheckbutton",
                        command=lambda: self._set_clip(
                            muted=self.mute_var.get())).pack(side="left")
        tk.Label(t, text="0 = silent, 100 = full. The Audio Mix on the "
                         "🎵 Music tab sets the level for the whole video.",
                 bg=CARD, fg=TEXT_MUTED, font=(FONT, 9, "italic"),
                 wraplength=390, justify="left").pack(anchor="w")
        tk.Label(t, text="Transitions, pan & zoom and fades are on the "
                         "🎞 Animations tab.  Drag a clip left or right on "
                         "the storyboard to change the order.  Delete key "
                         "removes it.",
                 bg=CARD, fg=TEXT_MUTED, font=(FONT, 9, "italic"),
                 wraplength=390, justify="left").pack(anchor="w",
                                                      pady=(10, 0))

    # ---------------- Animations (Movie Maker style) ----------------
    def _build_anim_tab(self):
        t = self._tab("🎞 Animations")
        self.anim_title = tk.Label(t, text="", bg=CARD, fg=BLUE_DARK,
                                   font=(FONT, 10, "bold"), wraplength=390,
                                   justify="left")
        self.anim_title.pack(anchor="w")
        label(t, "Transition (how this clip comes in):", bold=True).pack(
            anchor="w", pady=(4, 2))
        cats = tk.Frame(t, bg=CARD)
        cats.pack(fill="x")
        self.cat_btns = {}
        self.cur_cat = TRANSITION_GROUPS[0][0]
        for name, _ in TRANSITION_GROUPS:
            b = RoundButton(cats, text=name, relief="flat", bd=0,
                          font=(FONT, 9, "bold"), cursor="hand2", padx=6,
                          pady=3, command=lambda n=name: self._show_cat(n))
            b.pack(side="left", padx=1)
            self.cat_btns[name] = b
        self.trans_grid = tk.Frame(t, bg=CARD)
        self.trans_grid.pack(fill="x", pady=4)
        self.trans_btns = {}
        row = tk.Frame(t, bg=CARD)
        row.pack(fill="x")
        self.none_btn = RoundButton(row, text="✕ No transition (cut)",
                                  relief="flat", bd=0, font=(FONT, 9, "bold"),
                                  cursor="hand2", padx=6, pady=3,
                                  command=lambda: self._pick_transition("Cut"))
        self.none_btn.pack(side="left")
        GhostButton(row, "▶ Preview", font_size=9,
                    command=self.preview_transition).pack(side="right")
        row = tk.Frame(t, bg=CARD)
        row.pack(fill="x", pady=(4, 0))
        label(row, "Length:").pack(side="left")
        self.tlen_var = tk.DoubleVar(value=1.0)
        sc = hscale(row, TRANSITION_MIN, TRANSITION_MAX, self.tlen_var,
                    length=200, resolution=0.25)
        sc.pack(side="left", padx=4)
        sc.bind("<ButtonRelease-1>", lambda e: self._set_clip(
            transition_seconds=float(self.tlen_var.get())))
        label(row, "seconds", muted=True, size=9).pack(side="left")
        GhostButton(t, "Use this transition and length between ALL clips",
                    font_size=9, command=self._trans_to_all).pack(
            anchor="w", pady=(4, 0))
        ttk.Separator(t).pack(fill="x", pady=8)
        label(t, "Pan and zoom (slow camera move):", bold=True).pack(
            anchor="w")
        g = tk.Frame(t, bg=CARD)
        g.pack(fill="x", pady=4)
        self.motion_btns = {}
        icons = {"None": "▣", "Zoom in": "⊕", "Zoom out": "⊖",
                 "Pan left": "⇐", "Pan right": "⇒", "Pan up": "⇑",
                 "Pan down": "⇓", "Cinematic drift": "🎬",
                 "Ken Burns": "✨"}
        for i, m in enumerate(MOTIONS):
            b = RoundButton(g, text=f"{icons.get(m, '')} {m}", relief="flat",
                          bd=0, font=(FONT, 9, "bold"), cursor="hand2",
                          pady=4, command=lambda v=m: self._pick_motion(v))
            b.grid(row=i // 3, column=i % 3, padx=2, pady=2, sticky="ew")
            self.motion_btns[m] = b
        for col in range(3):
            g.columnconfigure(col, weight=1)
        GhostButton(t, "Use this camera move on ALL photos", font_size=9,
                    command=self._motion_to_photos).pack(anchor="w")
        ttk.Separator(t).pack(fill="x", pady=8)
        label(t, "Cinematic fades for this clip:", bold=True).pack(anchor="w")
        row = tk.Frame(t, bg=CARD)
        row.pack(fill="x", pady=2)
        label(row, "Fade in from black:").pack(side="left")
        self.fin_var = tk.DoubleVar()
        s = hscale(row, 0, 3, self.fin_var, length=150, resolution=0.5)
        s.pack(side="left", padx=4)
        s.bind("<ButtonRelease-1>", lambda e: self._set_clip(
            fade_in=self.fin_var.get()))
        row = tk.Frame(t, bg=CARD)
        row.pack(fill="x", pady=2)
        label(row, "Fade out to black: ").pack(side="left")
        self.fout_var = tk.DoubleVar()
        s = hscale(row, 0, 3, self.fout_var, length=150, resolution=0.5)
        s.pack(side="left", padx=4)
        s.bind("<ButtonRelease-1>", lambda e: self._set_clip(
            fade_out=self.fout_var.get()))
        self._show_cat(self.cur_cat)

    def _show_cat(self, name):
        self.cur_cat = name
        for n, b in self.cat_btns.items():
            on = n == name
            b.config(bg=BLUE if on else BLUE_LIGHT,
                     fg="white" if on else BLUE_DARK,
                     activebackground=BLUE_DARK if on else BLUE,
                     activeforeground="white")
        for w in self.trans_grid.winfo_children():
            w.destroy()
        self.trans_btns = {}
        items = dict(TRANSITION_GROUPS)[name]
        for i, (lbl, _) in enumerate(items):
            b = RoundButton(self.trans_grid, text=lbl, relief="flat", bd=0,
                          font=(FONT, 9, "bold"), cursor="hand2", pady=5,
                          command=lambda v=lbl: self._pick_transition(v))
            b.grid(row=i // 3, column=i % 3, padx=2, pady=2, sticky="ew")
            self.trans_btns[lbl] = b
        for col in range(3):
            self.trans_grid.columnconfigure(col, weight=1)
        if hasattr(self, "storyboard"):
            self._refresh_anim(self._selected_clip())

    @staticmethod
    def _paint(btn, on):
        btn.config(bg=ORANGE if on else BLUE_LIGHT,
                   fg="white" if on else BLUE_DARK,
                   activebackground=ORANGE_DARK if on else BLUE,
                   activeforeground="white")

    def _refresh_anim(self, c):
        if not hasattr(self, "trans_btns"):
            return
        cur_t = c.transition if c else None
        for lbl, b in self.trans_btns.items():
            self._paint(b, lbl == cur_t)
        self._paint(self.none_btn, cur_t == "Cut")
        cur_m = c.motion_name if c else None
        for m, b in self.motion_btns.items():
            self._paint(b, m == cur_m)
        if c is None:
            self.anim_title.config(text="Click a clip on the storyboard, "
                                        "then pick its animations here.")
            return
        i, _ = self.project.find_clip(c.id)
        self.anim_title.config(text=f"Clip {i + 1}: {c.name}")
        self.tlen_var.set(c.trans_len())
        self.fin_var.set(c.fade_in)
        self.fout_var.set(c.fade_out)
        if getattr(self, "_anim_clip", None) != c.id:   # a different clip:
            self._anim_clip = c.id                     # open its group
            for name, items in TRANSITION_GROUPS:
                if cur_t in dict(items) and name != self.cur_cat:
                    self.after_idle(lambda n=name: self._show_cat(n))
                    break

    def _pick_transition(self, name):
        c = self._need_clip()
        if not c:
            return
        i, _ = self.project.find_clip(c.id)
        self._set_clip(transition=name,
                       transition_seconds=float(self.tlen_var.get()))
        if i == 0 and name != "Cut":
            self.status_var.set("Transition set. (It shows when another "
                                "clip comes before this one.)")
        elif name != "Cut":
            self.status_var.set(f"Transition: {name}. Press ▶ Preview to "
                                f"see it.")

    def _trans_to_all(self):
        c = self._selected_clip()
        name = c.transition if c else "Crossfade"
        if name == "Cut":
            name = "Crossfade"
        self._set_all(transition=name,
                      transition_seconds=float(self.tlen_var.get()))

    def _pick_motion(self, m):
        c = self._need_clip()
        if c:
            self._set_clip(motion=m, zoom=False)

    def _motion_to_photos(self):
        c = self._selected_clip()
        m = c.motion_name if c else "Ken Burns"
        if m == "None" and c is None:
            return
        ids = [x.id for x in self.project.clips if x.is_photo]
        if not ids:
            messagebox.showinfo("No photos", "There are no photos on the "
                                             "storyboard yet.", parent=self)
            return
        self.project.push_undo()
        for x in self.project.clips:
            if x.is_photo:
                x.motion, x.zoom = m, False
        self.refresh_all()
        self.status_var.set(f"Camera move '{m}' put on {len(ids)} photos.")

    def preview_transition(self):
        """Quick look at the selected clip's transition: the end of the clip
        before it, then the start of this one."""
        c = self._need_clip()
        if not c or self._busy:
            return
        i, _ = self.project.find_clip(c.id)
        if i == 0 or c.transition == "Cut":
            messagebox.showinfo("Preview", "Pick a clip that has a clip "
                                           "before it and a transition.",
                                parent=self)
            return
        prev = self.project.clips[i - 1]
        q = Project()
        for k in ("shape", "custom_size", "fit_mode", "fps", "mix_video",
                  "mix_music", "mix_voice", "keep_clip_sound"):
            setattr(q, k, getattr(self.project, k))
        q.fade_whole = False
        td = c.trans_len()
        a = Clip.from_dict(copy.deepcopy(prev.to_dict()))
        b = Clip.from_dict(copy.deepcopy(c.to_dict()))
        keep = td + 1.5
        if a.is_photo:
            a.in_point, a.out_point = 0.0, keep
        else:
            a.in_point = max(a.in_point, a.out_point - keep * a.speed)
        if b.is_photo:
            b.in_point, b.out_point = 0.0, keep
        else:
            b.out_point = min(b.out_point, b.in_point + keep * b.speed)
        a.fade_out = 0.0
        b.fade_in = 0.0
        q.clips = [a, b]
        out = os.path.join(tempfile.gettempdir(), "ezvm_transition.mp4")
        self._run_export(out, proxy=True, project=q,
                         after=lambda: self.monitor.load(
                             out, name=f"Transition: {c.transition}",
                             autoplay=True))

    def _build_look_tab(self):
        t = self._tab("✨ Effects")
        label(t, "Color style for the selected clip:", bold=True).pack(
            anchor="w")
        self.color_var = tk.StringVar(value="Normal")
        grid = tk.Frame(t, bg=CARD)
        grid.pack(fill="x", pady=(2, 6))
        for i, cs in enumerate(COLOR_STYLES):
            ttk.Radiobutton(grid, text=cs, value=cs, variable=self.color_var,
                            style="Card.TRadiobutton",
                            command=lambda: self._set_clip(
                                color=self.color_var.get())).grid(
                row=i // 2, column=i % 2, sticky="w", padx=4)
        GhostButton(t, "Use this color style on ALL clips", font_size=9,
                    command=lambda: self._set_all(
                        color=self.color_var.get())).pack(anchor="w")
        ttk.Separator(t).pack(fill="x", pady=10)
        label(t, "Visual effect (cinematic looks):", bold=True).pack(
            anchor="w")
        self.effect_var = tk.StringVar(value="None")
        grid = tk.Frame(t, bg=CARD)
        grid.pack(fill="x", pady=(2, 6))
        for i, ef in enumerate(EFFECTS):
            ttk.Radiobutton(grid, text=ef, value=ef, variable=self.effect_var,
                            style="Card.TRadiobutton",
                            command=lambda: self._set_clip(
                                effect=self.effect_var.get())).grid(
                row=i // 2, column=i % 2, sticky="w", padx=4)
        GhostButton(t, "Use this effect on ALL clips", font_size=9,
                    command=lambda: self._set_all(
                        effect=self.effect_var.get())).pack(anchor="w")
        ttk.Separator(t).pack(fill="x", pady=10)
        self.fade_whole_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(t, text="Gentle fade in and out for the whole video",
                        variable=self.fade_whole_var,
                        style="Card.TCheckbutton",
                        command=self._set_fade_whole).pack(anchor="w")

    def _build_sound_tab(self):
        t = self._tab("🎵 Music")
        grid = tk.Frame(t, bg=CARD)
        grid.pack(fill="x")
        for k, (txt, cmd) in enumerate([
                ("🎵 Add music", lambda: self.add_audio("music")),
                ("🎙 Record voice", self.record_voice),
                ("📄 Voice file", lambda: self.add_audio("voice")),
                ("🔊 Sound effect", lambda: self.add_audio("sfx"))]):
            RoundButton(grid, text=txt, command=cmd, bg=SILVER, fg=BLUE_DARK,
                      activebackground=BLUE, activeforeground="white",
                      relief="flat", font=(FONT, 9, "bold"), cursor="hand2",
                      padx=6, pady=5).grid(row=k // 2, column=k % 2,
                                           padx=2, pady=2, sticky="ew")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        RoundButton(grid, text="📱 WhatsApp audio → MP3 / WAV",
                    command=self.whatsapp_audio, bg=WHATSAPP_GREEN,
                    fg="white", activebackground=GREEN,
                    activeforeground="white", font=(FONT, 9, "bold"),
                    cursor="hand2", padx=6, pady=5, radius=14).grid(
            row=2, column=0, columnspan=2, padx=2, pady=2, sticky="ew")
        # ---- Audio Mix (like Movie Maker)
        box = tk.LabelFrame(t, text="  🎚 Audio mix  ", bg=CARD, fg=BLUE_DARK,
                            font=(FONT, 10, "bold"), bd=1, relief="solid",
                            padx=8, pady=4)
        box.pack(fill="x", pady=(8, 4))
        self.mix_vars = {}
        self.mix_lbls = {}
        for key, txt in [("mix_video", "🎬 Video sound"),
                         ("mix_music", "🎵 Music"),
                         ("mix_voice", "🎙 Voice & effects")]:
            row = tk.Frame(box, bg=CARD)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=txt, bg=CARD, fg=TEXT, font=(FONT, 10),
                     width=15, anchor="w").pack(side="left")
            v = tk.IntVar(value=100)
            self.mix_vars[key] = v
            sc = tk.Scale(row, from_=0, to=100, orient="horizontal",
                          variable=v, showvalue=False, bg=CARD,
                          highlightthickness=0, length=190,
                          troughcolor=BLUE_LIGHT, sliderlength=18,
                          command=lambda val, k=key: self._mix_moved(k))
            sc.pack(side="left", padx=4)
            sc.bind("<ButtonRelease-1>", lambda e, k=key: self._set_mix(k))
            lb = tk.Label(row, text="100%", bg=CARD, fg=BLUE_DARK,
                          font=(FONT, 10, "bold"), width=5)
            lb.pack(side="left")
            self.mix_lbls[key] = lb
        row = tk.Frame(box, bg=CARD)
        row.pack(fill="x", pady=(2, 0))
        self.keep_sound_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="Keep the sound in my video clips",
                        variable=self.keep_sound_var,
                        style="Card.TCheckbutton",
                        command=self._set_keep_sound).pack(side="left")
        GhostButton(row, "All to 100%", font_size=8,
                    command=self._reset_mix).pack(side="right")
        # ---- the sounds
        self.audio_list = ttk.Treeview(t, columns=("kind", "start", "vol"),
                                       show="headings", height=4,
                                       selectmode="browse")
        for col, txt, w in [("kind", "Sound", 190), ("start", "Starts at", 70),
                            ("vol", "Volume", 60)]:
            self.audio_list.heading(col, text=txt)
            self.audio_list.column(col, width=w, anchor="w")
        self.audio_list.pack(fill="x", pady=(6, 4))
        self.audio_list.bind("<Double-Button-1>", lambda e: self.edit_audio())
        row = tk.Frame(t, bg=CARD)
        row.pack(fill="x")
        GhostButton(row, "Settings…", font_size=9,
                    command=self.edit_audio).pack(side="left", padx=2)
        GhostButton(row, "Listen", font_size=9,
                    command=self.listen_audio).pack(side="left", padx=2)
        GhostButton(row, "Remove", font_size=9,
                    command=self.remove_audio).pack(side="left", padx=2)
        fits = tk.Frame(t, bg=CARD)
        fits.pack(fill="x", pady=(8, 0))
        BigButton(fits, "🎵  Fit to music", command=self.fit_to_music,
                  color=PINK, font_size=10, pady=9, padx=10).pack(
            side="left", fill="x", expand=True, padx=(0, 3))
        BigButton(fits, "🎬  Fit music to video", command=self.fit_to_video,
                  color=PURPLE, font_size=10, pady=9, padx=10).pack(
            side="left", fill="x", expand=True, padx=(3, 0))
        tk.Label(t, text="Fit to music: the pictures stretch so the video "
                         "lasts as long as the songs.\n"
                         "Fit music to video: the video keeps its length - "
                         "the music fades out when the video ends.",
                 bg=CARD, fg=TEXT_MUTED, font=(FONT, 9), justify="left",
                 wraplength=420).pack(anchor="w", pady=(4, 0))
        self.whole_song_var = tk.BooleanVar(value=True)
        tk.Checkbutton(t, text="Play the music all the way to the end\n"
                               "(the video keeps going until the last song "
                               "finishes)",
                       variable=self.whole_song_var, bg=CARD, fg=TEXT,
                       activebackground=CARD, font=(FONT, 10, "bold"),
                       justify="left", anchor="w",
                       command=self._set_whole_song).pack(anchor="w",
                                                          pady=(8, 0))
        tk.Label(t, text="Add several songs and they play one after "
                         "another. Everything starts at 100%. Slide down "
                         "to make one part quieter (0 = silent).",
                 bg=CARD, fg=TEXT_MUTED, font=(FONT, 9, "italic"),
                 wraplength=420, justify="left").pack(anchor="w", pady=6)

    def _build_words_tab(self):
        t = self._tab("🔤 Words")
        row = tk.Frame(t, bg=CARD)
        row.pack(fill="x")
        for txt, style in [("🔤 Title", TEXT_STYLES[0]),
                           ("💬 Caption", TEXT_STYLES[1]),
                           ("📜 Credits", TEXT_STYLES[2]),
                           ("🏷 Banner", TEXT_STYLES[3])]:
            RoundButton(row, text=txt, bg=SILVER, fg=BLUE_DARK,
                      activebackground=BLUE, activeforeground="white",
                      relief="flat", font=(FONT, 9, "bold"), cursor="hand2",
                      padx=6, pady=6, command=lambda s=style: self.add_text(s)
                      ).pack(side="left", padx=2)
        self.text_list = ttk.Treeview(t, columns=("text", "when"),
                                      show="headings", height=7,
                                      selectmode="browse")
        self.text_list.heading("text", text="Words")
        self.text_list.heading("when", text="When")
        self.text_list.column("text", width=210)
        self.text_list.column("when", width=100)
        self.text_list.pack(fill="x", pady=6)
        self.text_list.bind("<Double-Button-1>", lambda e: self.edit_text())
        row = tk.Frame(t, bg=CARD)
        row.pack(fill="x")
        GhostButton(row, "Edit…", font_size=9,
                    command=self.edit_text).pack(side="left", padx=2)
        GhostButton(row, "Remove", font_size=9,
                    command=self.remove_text).pack(side="left", padx=2)
        tk.Label(t, text="Title = big words in the middle. Caption = words "
                         "along the bottom. Credits scroll up at the end. "
                         "Words appear in the finished video and in "
                         "'Play whole video'.",
                 bg=CARD, fg=TEXT_MUTED, font=(FONT, 9, "italic"),
                 wraplength=390, justify="left").pack(anchor="w", pady=6)

    def _build_storyboard(self):
        wrap = tk.Frame(self, bg=PANEL, highlightthickness=1,
                        highlightbackground=LINE)
        wrap.pack(side="bottom", fill="x", padx=8, pady=(6, 6))
        top = tk.Frame(wrap, bg=PANEL)
        top.pack(fill="x", padx=8, pady=(6, 0))
        tk.Label(top, text="Storyboard", bg=PANEL, fg=BLUE_DARK,
                 font=(FONT, 12, "bold")).pack(side="left")
        tk.Label(top, text="click a clip to edit it  ·  drag to change the "
                           "order", bg=PANEL, fg=TEXT_MUTED,
                 font=(FONT, 9)).pack(side="left", padx=10)
        self.total_lbl = tk.Label(top, text="", bg=PANEL, fg=BLUE_DARK,
                                  font=(FONT, 10, "bold"))
        self.total_lbl.pack(side="left", padx=6)
        for txt, cmd in [("✖ Remove", self.tool_delete),
                         ("Move right ▶", lambda: self.move_selected(1)),
                         ("◀ Move left", lambda: self.move_selected(-1))]:
            GhostButton(top, txt, font_size=9, command=cmd).pack(side="right",
                                                                 padx=2)
        self.music_strip = MusicStrip(wrap, self.project, self._pick_song)
        self.music_strip.pack(fill="x", padx=8, pady=(6, 2))
        self.storyboard = Storyboard(wrap, self.project, self._clip_selected,
                                     self._clip_reordered)
        self.storyboard.pack(fill="x", padx=8, pady=(2, 6))

    def _build_status_bar(self):
        bar = tk.Frame(self, bg=PANEL, highlightthickness=1,
                       highlightbackground=LINE)
        bar.pack(side="bottom", fill="x")
        row = tk.Frame(bar, bg=PANEL)
        row.pack(fill="x", padx=10, pady=4)
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(row, textvariable=self.status_var, bg=PANEL, fg=TEXT,
                 font=(FONT, 10, "bold"), anchor="w").pack(side="left")
        self.cancel_btn = GhostButton(row, "Cancel", font_size=9,
                                      command=self.cancel_job)
        self.proj_lbl = tk.Label(row, text="Untitled project", bg=PANEL,
                                 fg=TEXT_MUTED, font=(FONT, 9, "italic"))
        self.proj_lbl.pack(side="right", padx=(12, 0))
        self.guide_var = tk.BooleanVar(value=True)
        tk.Checkbutton(row, text="Safe-area guide", variable=self.guide_var,
                       bg=PANEL, activebackground=PANEL, fg=TEXT,
                       font=(FONT, 9), command=self._toggle_guide
                       ).pack(side="right", padx=8)
        self.pbar = ttk.Progressbar(row, style="Orange.Horizontal.TProgressbar",
                                    maximum=100, length=260)
        self.pbar.pack(side="right", padx=8)

    def refresh_all(self):
        self.storyboard.project = self.project
        self.storyboard.refresh()
        self.music_strip.project = self.project
        self.music_strip.refresh()
        self.whole_song_var.set(self.project.play_whole_song)
        self._refresh_shape()
        self._refresh_lists()
        self._refresh_clip_panel()
        self.fit_var.set(self.project.fit_mode)
        self.quality_var.set(self.project.quality)
        self.keep_sound_var.set(self.project.keep_clip_sound)
        self.fade_whole_var.set(self.project.fade_whole)
        self.k4_var.set(self.project.upscale_4k)
        self.monitor.guide_shape = (self.project.target_size()
                                    if self.guide_var.get() else None)
        for k, v in self.mix_vars.items():
            v.set(int(round(getattr(self.project, k) * 100)))
            self.mix_lbls[k].config(text=f"{v.get()}%")
        self.proj_lbl.config(text=(os.path.basename(self.project.path)
                                   if self.project.path else
                                   "Untitled project") +
                             (" *" if self.project.dirty else ""))
        n = len(self.project.clips)
        self.total_lbl.config(
            text=f"{n} clip{'s' if n != 1 else ''} · "
                 f"{fmt_time(self.project.total_duration())} long"
            if n else "")

    def _refresh_shape(self):
        for key, b in self.shape_btns.items():
            b.set_selected(key == self.project.shape and
                           not self.project.custom_size)
        w, h = self.project.target_size()
        name = self.project.shape if not self.project.custom_size else "Custom"
        self.shape_lbl.config(text=f"{w} x {h}" +
                              ("" if self.project.shape in self.shape_btns and
                               not self.project.custom_size else
                               f"  ({name})"))

    def _refresh_lists(self):
        for iid in self.audio_list.get_children():
            self.audio_list.delete(iid)
        for a in self.project.audios:
            kind = {"music": "🎵", "voice": "🎙", "sfx": "🔊"}.get(a.kind, "")
            self.audio_list.insert("", "end", iid=a.id,
                                   values=(f"{kind} {a.name}",
                                           fmt_time(a.start),
                                           f"{int(a.volume * 100)}%"))
        for iid in self.text_list.get_children():
            self.text_list.delete(iid)
        for t in self.project.texts:
            short = t.text.replace("\n", " ")
            self.text_list.insert("", "end", iid=t.id,
                                  values=(short[:32], f"{t.start:g}s - "
                                                      f"{t.end:g}s"))

    def _selected_clip(self):
        i, c = self.project.find_clip(self.storyboard.selected_id)
        return c

    def _refresh_clip_panel(self):
        c = self._selected_clip()
        if not c:
            self.clip_title.config(text="Click a clip on the storyboard to "
                                        "edit it.")
            self._refresh_anim(None)
            return
        i, _ = self.project.find_clip(c.id)
        kind = "Photo" if c.is_photo else "Video"
        self.clip_title.config(text=f"{kind} {i + 1}: {c.name}\n"
                                    f"{c.describe()}")
        self.speed_var.set(f"{c.speed:g}")
        self.vol_var.set(round(min(1.0, c.volume) * 100))
        self.mute_var.set(c.muted)
        self.fin_var.set(c.fade_in)
        self.fout_var.set(c.fade_out)
        self.color_var.set(c.color)
        self.effect_var.set(getattr(c, "effect", "None"))
        self._refresh_anim(c)

    def _clip_selected(self, clip):
        self._refresh_clip_panel()
        if clip.is_photo:
            self.monitor.load(clip.path, duration=clip.duration,
                              name=clip.name)
        else:
            self.monitor.load(clip.path, duration=clip.out_point - clip.in_point,
                              offset=clip.in_point, name=clip.name)
        self.status_var.set(f"Selected clip: {clip.name}")

    def _clip_reordered(self, clip_id, new_index):
        if self.project.move_clip(clip_id, new_index):
            self.storyboard.select(clip_id)
            self.refresh_all()
            self.status_var.set("Clip moved.")

    def _step(self, delta):
        clips = self.project.clips
        if not clips:
            return
        i, c = self.project.find_clip(self.storyboard.selected_id)
        i = 0 if i is None else (i + delta) % len(clips)
        self.storyboard.select(clips[i].id)
        self._clip_selected(clips[i])

    def _need_clip(self):
        c = self._selected_clip()
        if not c:
            messagebox.showinfo("Pick a clip",
                                "Click a clip on the storyboard first.",
                                parent=self)
        return c

    def _set_clip(self, **fields):
        c = self._selected_clip()
        if not c:
            return
        if all(getattr(c, k) == v for k, v in fields.items()):
            return
        self.project.set_clip(c.id, **fields)
        self.refresh_all()
        self.status_var.set("Changed. (Ctrl+Z to undo)")

    def _set_all(self, **fields):
        if self.project.set_all_clips(**fields):
            self.refresh_all()
            self.status_var.set("Applied to all clips.")

    def _set_fit(self):
        self.project.fit_mode = self.fit_var.get()
        self.project.dirty = True

    def _set_fade_whole(self):
        self.project.fade_whole = self.fade_whole_var.get()
        self.project.dirty = True

    def _set_whole_song(self):
        self.project.play_whole_song = self.whole_song_var.get()
        self.project.dirty = True
        self.refresh_all()

    def _pick_song(self, audio_id):
        self._show_tab("Music")
        if self.audio_list.exists(audio_id):
            self.audio_list.selection_set(audio_id)
            self.audio_list.see(audio_id)

    def _set_keep_sound(self):
        self.project.keep_clip_sound = self.keep_sound_var.get()
        self.project.dirty = True

    def _mix_moved(self, key):
        v = self.mix_vars[key].get()
        self.mix_lbls[key].config(text=f"{v}%")

    def _set_mix(self, key):
        v = max(0, min(100, int(self.mix_vars[key].get()))) / 100.0
        if abs(getattr(self.project, key) - v) > 0.001:
            self.project.push_undo()
            setattr(self.project, key, v)
            self.status_var.set("Audio mix changed. Press ▶ Play whole video "
                                "to hear it.")
            self.refresh_all()

    def _reset_mix(self):
        self.project.push_undo()
        self.project.mix_video = self.project.mix_music = \
            self.project.mix_voice = 1.0
        self.refresh_all()

    def _toggle_guide(self):
        self.monitor.guide_shape = (self.project.target_size()
                                    if self.guide_var.get() else None)
        self.monitor._resized()

    def _set_4k(self):
        self.project.upscale_4k = self.k4_var.get()
        self.project.dirty = True

    # ================= shape =================
    def set_shape(self, key, custom=None):
        self.project.set_shape(key, custom)
        self.refresh_all()
        w, h = self.project.target_size()
        self.status_var.set(f"Video shape: {w} x {h}")

    def _more_shapes(self):
        m = tk.Menu(self, tearoff=0, font=(FONT, 11))
        for lbl in ff.SHAPES:
            w, h = ff.SHAPES[lbl]
            m.add_command(label=f"{lbl}   ({w}x{h})",
                          command=lambda l=lbl: self.set_shape(l))
        m.add_separator()
        m.add_command(label="Custom size…", command=self._custom_size)
        try:
            m.tk_popup(self.more_btn.winfo_rootx(),
                       self.more_btn.winfo_rooty() + self.more_btn.winfo_height())
        finally:
            m.grab_release()

    def _custom_size(self):
        w, h = self.project.target_size()
        r = SizeDialog(self, w, h).show()
        if r:
            self.set_shape("Custom", r)

    # ================= adding media =================
    def add_videos(self):
        paths = filedialog.askopenfilenames(
            title="Choose videos", parent=self,
            filetypes=[("Videos", " ".join("*" + e for e in
                                            sorted(ff.VIDEO_EXTS))),
                       ("All files", "*.*")])
        self._add_paths(paths)

    def add_photos(self):
        paths = filedialog.askopenfilenames(
            title="Choose photos", parent=self,
            filetypes=[("Pictures", " ".join("*" + e for e in
                                              sorted(ff.IMAGE_EXTS))),
                       ("All files", "*.*")])
        self._add_paths(paths)

    def _on_drop(self, event):
        self._add_paths(self.tk.splitlist(event.data))

    def _add_paths(self, paths):
        last = None
        bad = []
        for p in paths:
            p = p.strip("{}")
            if not os.path.isfile(p):
                continue
            ext = os.path.splitext(p)[1].lower()
            if ext in ff.AUDIO_EXTS:
                self.project.add_audio(p, "music")
                continue
            if ext == ".ezvm":
                self._open_path(p)
                return
            if ext not in ff.VIDEO_EXTS | ff.IMAGE_EXTS:
                bad.append(os.path.basename(p))
                continue
            self.status_var.set(f"Adding {os.path.basename(p)}…")
            self.update_idletasks()
            last = self.project.add_clip(p)
        if last:
            self.storyboard.select(last.id)
            self._clip_selected(last)
        self.refresh_all()
        if bad:
            messagebox.showwarning("File type not supported",
                                   "These files could not be added:\n" +
                                   "\n".join(bad[:8]), parent=self)
        if last:
            self.status_var.set(f"Added {os.path.basename(last.path)}.")

    # ================= clip tools =================
    def tool_undo(self):
        if self.project.undo():
            self.refresh_all()
            self.status_var.set("Undone.")

    def tool_redo(self):
        if self.project.redo():
            self.refresh_all()
            self.status_var.set("Redone.")

    def tool_delete(self):
        c = self._selected_clip()
        if not c:
            return
        i, _ = self.project.find_clip(c.id)
        self.project.remove_clip(c.id)
        clips = self.project.clips
        if clips:
            nxt = clips[min(i, len(clips) - 1)]
            self.storyboard.select(nxt.id)
            self._clip_selected(nxt)
        else:
            self.storyboard.selected_id = None
            self.monitor.clear()
        self.refresh_all()
        self.status_var.set("Clip removed. (Ctrl+Z to undo)")

    def move_selected(self, delta):
        c = self._selected_clip()
        if not c:
            return
        i, _ = self.project.find_clip(c.id)
        self._clip_reordered(c.id, i + delta)

    def tool_trim(self):
        c = self._need_clip()
        if not c:
            return
        if c.is_photo:
            return self.tool_photo_time()
        r = TrimDialog(self, c).show()
        if r:
            self.project.set_trim(c.id, r[0], r[1])
            self.refresh_all()
            self._clip_selected(c)
            self.status_var.set("Trimmed.")

    def tool_split(self):
        c = self._need_clip()
        if not c:
            return
        if c.is_photo:
            messagebox.showinfo("Photos", "Splitting works on video clips. "
                                          "Use Duplicate for photos.",
                                parent=self)
            return
        r = SplitDialog(self, c).show()
        if r is not None:
            right = self.project.split_clip(c.id, r)
            if right:
                self.refresh_all()
                self.status_var.set("Clip split into two.")
            else:
                messagebox.showinfo("Too close to the edge",
                                    "Pick a spot a little further from the "
                                    "start or end.", parent=self)

    def tool_photo_time(self):
        c = self._need_clip()
        if not c:
            return
        if not c.is_photo:
            return self.tool_trim()
        n_photos = sum(1 for x in self.project.clips if x.is_photo)
        r = PhotoLengthDialog(self, c, n_photos).show()
        if r:
            secs, to_all = r
            n = self.project.set_photo_time(
                secs, None if to_all else {c.id})
            self.refresh_all()
            self._clip_selected(c)
            self.status_var.set(
                f"{n} photos now show for {secs:g} seconds." if n > 1 else
                f"Photo now shows for {secs:g} seconds.")

    def fit_to_music(self):
        ok, msg = self.project.fit_to_music()
        if ok:
            self.refresh_all()
            c = self._selected_clip()
            if c:
                self._clip_selected(c)
            self.status_var.set("Fitted to the music. (Ctrl+Z to undo)")
            messagebox.showinfo("Fit to music", msg, parent=self)
        else:
            messagebox.showinfo("Fit to music", msg, parent=self)

    def fit_to_video(self):
        """Fit music to video: the video keeps its length; songs that
        are too long fade out and stop when the video ends."""
        ok, msg = self.project.fit_to_video()
        if ok:
            self.refresh_all()
            c = self._selected_clip()
            if c:
                self._clip_selected(c)
            self.status_var.set("Fitted the music to the video. "
                                "(Ctrl+Z to undo)")
        messagebox.showinfo("Fit music to video", msg, parent=self)

    def tool_rotate(self):
        c = self._need_clip()
        if c:
            self._set_clip(rotate=(c.rotate + 90) % 360)

    def tool_flip(self, which):
        c = self._need_clip()
        if c:
            if which == "h":
                self._set_clip(flip_h=not c.flip_h)
            else:
                self._set_clip(flip_v=not c.flip_v)

    def tool_crop(self):
        c = self._need_clip()
        if not c:
            return
        r = CropDialog(self, c).show()
        if r is not None:
            self._set_clip(crop=r if r else None)

    def tool_duplicate(self):
        c = self._need_clip()
        if c:
            d = self.project.duplicate_clip(c.id)
            self.storyboard.select(d.id)
            self.refresh_all()

    # ================= sound =================
    def add_audio(self, kind):
        titles = {"music": "Choose music", "voice": "Choose a voice recording",
                  "sfx": "Choose a sound effect"}
        p = filedialog.askopenfilename(
            title=titles[kind], parent=self,
            filetypes=[("Sound files", " ".join("*" + e for e in
                                                 sorted(ff.AUDIO_EXTS))),
                       ("Videos (use their sound)", " ".join(
                           "*" + e for e in sorted(ff.VIDEO_EXTS))),
                       ("All files", "*.*")])
        if not p:
            return
        start = None
        if kind != "music":
            start = 0.0
            c = self._selected_clip()
            if c:
                i, _ = self.project.find_clip(c.id)
                start = round(self.project.clip_start(i), 2)
        a = self.project.add_audio(p, kind, start)
        self.refresh_all()
        self.audio_list.selection_set(a.id)
        if kind == "music" and a.start > 0:
            self.status_var.set(f"Added song: {a.name} - it plays after the "
                                f"other music, starting at "
                                f"{fmt_time(a.start)}.")
        else:
            self.status_var.set(f"Added sound: {a.name}")

    def whatsapp_audio(self):
        """WhatsApp voice notes / audio -> MP3 or WAV (and into the video)."""
        paths = pick_wa_files(self)
        if not paths:
            return

        def add(files, kind):
            for f in files:
                start = None
                if kind == "voice":
                    start = 0.0
                    c = self._selected_clip()
                    if c:
                        i, _ = self.project.find_clip(c.id)
                        start = round(self.project.clip_start(i), 2)
                self.project.add_audio(f, kind, start)
            self.refresh_all()
            self.status_var.set(f"Added {len(files)} WhatsApp sound"
                                f"{'s' if len(files) != 1 else ''} to your "
                                f"video.")
        WhatsAppDialog(self, paths, add).show()

    def record_voice(self):
        def done(path):
            start = 0.0
            c = self._selected_clip()
            if c:
                i, _ = self.project.find_clip(c.id)
                start = round(self.project.clip_start(i), 2)
            a = self.project.add_audio(path, "voice", start)
            a.name = "My voice recording"
            self.refresh_all()
            self.status_var.set("Voice recorded and added.")
        RecordDialog(self, done)

    def _selected_audio(self):
        s = self.audio_list.selection()
        return self.project.find_audio(s[0]) if s else None

    def edit_audio(self):
        a = self._selected_audio()
        if not a:
            messagebox.showinfo("Pick a sound", "Click a sound in the list "
                                                "first.", parent=self)
            return
        r = AudioDialog(self, a, self.project.total_duration()).show()
        if r:
            self.project.push_undo()
            for k, v in r.items():
                setattr(a, k, v)
            self.refresh_all()

    def listen_audio(self):
        a = self._selected_audio()
        if a:
            self.monitor.load(a.path, name=a.name, autoplay=True)

    def remove_audio(self):
        a = self._selected_audio()
        if a:
            self.project.remove_audio(a.id)
            self.refresh_all()

    # ================= words =================
    def add_text(self, style):
        start = 0.0
        total = self.project.total_duration()
        c = self._selected_clip()
        if style.startswith("Credits"):
            start = max(0.0, total - 5.0)
        elif c:
            i, _ = self.project.find_clip(c.id)
            start = round(self.project.clip_start(i), 2)
        r = TextDialog(self, None, style, start, total).show()
        if r:
            t = self.project.add_text(r["text"], r["style"], r["start"],
                                      r["duration"])
            t.size, t.color = r["size"], r["color"]
            t.outline, t.box = r["outline"], r["box"]
            self.refresh_all()
            self.status_var.set("Words added.")

    def _selected_text(self):
        s = self.text_list.selection()
        return self.project.find_text(s[0]) if s else None

    def edit_text(self):
        t = self._selected_text()
        if not t:
            messagebox.showinfo("Pick words", "Click a line in the list "
                                              "first.", parent=self)
            return
        r = TextDialog(self, t, total=self.project.total_duration()).show()
        if r:
            self.project.push_undo()
            for k, v in r.items():
                setattr(t, k, v)
            self.refresh_all()

    def remove_text(self):
        t = self._selected_text()
        if t:
            self.project.remove_text(t.id)
            self.refresh_all()

    # ================= project files =================
    def new_project(self):
        if self.project.dirty and not messagebox.askyesno(
                "Start fresh?", "Throw away the current project?",
                parent=self):
            return
        self.project = Project()
        self.storyboard.selected_id = None
        self.monitor.clear()
        self.refresh_all()
        self.status_var.set("New project.")

    def save_project(self):
        path = self.project.path
        if not path:
            path = filedialog.asksaveasfilename(
                title="Save project as…", defaultextension=".ezvm",
                initialfile="My Project.ezvm", parent=self,
                initialdir=self._videos_dir(),
                filetypes=[("EZ Video Maker project", "*.ezvm")])
        if not path:
            return
        try:
            self.project.save(path)
            self.refresh_all()
            self.status_var.set(f"Project saved: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Could not save", str(e), parent=self)

    def open_project(self):
        path = filedialog.askopenfilename(
            title="Open a project", parent=self,
            filetypes=[("EZ Video Maker project", "*.ezvm")])
        if path:
            self._open_path(path)

    def _open_path(self, path):
        try:
            self.project = Project.load(path)
        except Exception as e:
            messagebox.showerror("Could not open",
                                 f"That project could not be opened:\n{e}",
                                 parent=self)
            return
        self.storyboard.selected_id = None
        self.monitor.clear()
        self.refresh_all()
        missing = self.project.missing_files()
        if missing:
            messagebox.showwarning("Missing files",
                                   "These files have moved or were deleted:"
                                   "\n- " + "\n- ".join(missing[:8]),
                                   parent=self)
        if self.project.clips:
            c = self.project.clips[0]
            self.storyboard.select(c.id)
            self._clip_selected(c)
        self.status_var.set(f"Opened: {os.path.basename(path)}")

    @staticmethod
    def _videos_dir():
        d = os.path.join(os.path.expanduser("~"), "Videos")
        return d if os.path.isdir(d) else os.path.expanduser("~")

    # ================= preview & export =================
    def play_whole(self):
        if self._busy:
            return
        if not self.project.clips:
            messagebox.showinfo("Empty storyboard",
                                "Add videos or photos first.", parent=self)
            return
        out = os.path.join(tempfile.gettempdir(), "ezvm_preview.mp4")
        self._run_export(out, proxy=True, after=lambda: self.monitor.load(
            out, name="Whole video (quick preview)", autoplay=True))

    def export(self):
        if self._busy:
            return
        if not self.project.clips:
            messagebox.showinfo("Empty storyboard",
                                "Add videos or photos first.", parent=self)
            return
        problems = self._checklist()
        if problems and not messagebox.askyesno(
                "Quick check before saving",
                "\n\n".join("• " + p for p in problems) +
                "\n\nSave the video anyway?", parent=self):
            return
        vert = self.project.is_vertical()
        default = "My TikTok Video.mp4" if vert else "My Video.mp4"
        out = filedialog.asksaveasfilename(
            title="Save your video as…", defaultextension=".mp4",
            initialfile=default, initialdir=self._videos_dir(), parent=self,
            filetypes=[("MP4 video", "*.mp4")])
        if not out:
            return
        self._run_export(out, proxy=False,
                         after=lambda: self._export_done(out))

    def _checklist(self):
        """Things worth a second look before a long save."""
        p = self.project
        out = []
        tw, th = p.target_size()
        if p.fit_mode.startswith("Fit"):
            for c in p.clips:
                w, h = self._clip_size(c)
                if w and h and abs(w / h - tw / th) > 0.03 and \
                        c.rotate in (0, 180):
                    out.append("Some clips are a different shape, so they "
                               "will have black bars. Pick 'Fill the "
                               "screen' at the top to remove them.")
                    break
        clip_sound = p.keep_clip_sound and p.mix_video > 0 and any(
            c.has_audio and not c.muted and c.volume > 0 and not c.is_photo
            for c in p.clips)
        other = any(a.path and a.volume > 0 and
                    (p.mix_music if a.mix_group == "music" else p.mix_voice)
                    > 0 for a in p.audios)
        if not clip_sound and not other:
            out.append("This video will have no sound (no music, voice or "
                       "clip sound is turned up).")
        if p.upscale_4k:
            low = []
            for c in p.clips:
                w, h = self._clip_size(c)
                if w and h and min(w, h) < 720:
                    low.append(c.name)
            if low:
                out.append("These clips are small and may look soft at 4K: "
                           + ", ".join(low[:4]))
        return out

    @staticmethod
    def _clip_size(c):
        if c.src_w and c.src_h:
            return c.src_w, c.src_h
        if c.is_photo:
            try:
                from PIL import Image
                with Image.open(c.path) as im:
                    c.src_w, c.src_h = im.size
                return c.src_w, c.src_h
            except Exception:
                return None, None
        return None, None

    def _export_done(self, out):
        self.status_var.set("✔ Your video is ready!")
        w, h = self.project.target_size()
        if messagebox.askyesno("Success!",
                               f"Your video was saved ({w}x{h}):\n{out}\n\n"
                               "Open its folder now?", parent=self):
            ff.open_folder(out)

    def _run_export(self, out, proxy, after, project=None):
        self._busy = True
        self.pbar["value"] = 0
        self.save_btn.config(state="disabled")
        self.cancel_btn.pack(side="left", padx=4)
        self.monitor.stop(redraw=False)
        self.project.quality = self.quality_var.get()
        self._exporter = Exporter(project or self.project, out, proxy=proxy)
        q = queue.Queue()

        def worker():
            try:
                self._exporter.run(
                    progress=lambda pct, lbl: q.put(("prog", pct, lbl)))
                q.put(("ok",))
            except ExportCancelled:
                q.put(("cancelled",))
            except Exception as e:
                q.put(("error", str(e)))

        def poll():
            try:
                while True:
                    item = q.get_nowait()
                    if item[0] == "prog":
                        self.pbar.configure(value=item[1])
                        self.status_var.set(item[2])
                    elif item[0] == "ok":
                        self._job_finished()
                        after()
                        return
                    elif item[0] == "cancelled":
                        self._job_finished()
                        self.status_var.set("Cancelled.")
                        return
                    elif item[0] == "error":
                        self._job_finished()
                        self.status_var.set("Could not make the video.")
                        messagebox.showerror("Could not make the video",
                                             item[1][:1200], parent=self)
                        return
            except queue.Empty:
                pass
            if self.winfo_exists():
                self.after(100, poll)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, poll)

    def _job_finished(self):
        self._busy = False
        self.save_btn.config(state="normal")
        self.cancel_btn.pack_forget()

    def cancel_job(self):
        if self._exporter:
            self._exporter.cancel()

    # ================= leaving =================
    def _go_home(self):
        if self._busy:
            if not messagebox.askyesno("Still working",
                                       "A video is still being made. Stop it "
                                       "and go home?", parent=self):
                return
            self.cancel_job()
        if self.project.dirty and self.project.clips and messagebox.askyesno(
                "Save first?", "Save your project before leaving?",
                parent=self):
            self.save_project()
        self.shutdown()
        self.app.show_welcome()

    def shutdown(self):
        top = self.winfo_toplevel()
        for seq, _ in self._binds:
            try:
                top.unbind(seq)
            except Exception:
                pass
        self.monitor.shutdown()
