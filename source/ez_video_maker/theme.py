"""
EZ Video Maker - theme and shared widgets.

Modern look for Tkinter: soft rounded buttons with a brushed-silver or
glossy colour finish (drawn with Pillow, so no image files are needed),
a dark header with a colourful accent line, and a little music
equalizer that dances while something is playing.
"""

import math
import random
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk

# ---------------------------------------------------------------- palette
BLUE_DARK = "#15213A"       # deep midnight (headers, titles)
BLUE = "#2F6FE4"            # vivid blue
BLUE_LIGHT = "#EAF0FB"
ORANGE = "#FF7A1A"          # the EZ orange
ORANGE_DARK = "#E05A00"
ORANGE_LIGHT = "#FFF0E3"
BG = "#EEF1F6"
PANEL = "#E6EAF1"
LINE = "#D6DCE6"
CARD = "#FFFFFF"
TEXT = "#1A2233"
TEXT_MUTED = "#5F6B7D"
GREEN = "#1FA463"
RED = "#E5394B"
DARK = "#0B0F17"
DARK2 = "#131A28"
DARK3 = "#222C40"
PURPLE = "#7B5CFF"
PINK = "#FF4FA3"
TEAL = "#12B5A6"
SILVER = "#E9EDF2"          # "colour" name for the brushed-silver finish

# colours of the accent line under the header and of the equalizer
ACCENT_LINE = ["#FF7A1A", "#FF4FA3", "#7B5CFF", "#2F6FE4"]
EQ_COLORS = ["#22D3EE", "#2DD4BF", "#4ADE80", "#A3E635", "#FACC15",
             "#FB923C", "#F43F5E", "#E879F9"]

FONT = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"


# ---------------------------------------------------------------- colours
def _rgb(c, widget=None):
    """'#RRGGBB' or a Tk colour name -> (r, g, b) 0-255."""
    if isinstance(c, tuple):
        return c[:3]
    c = str(c)
    if c.startswith("#") and len(c) == 7:
        return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    try:
        w = widget or tk._default_root
        r, g, b = w.winfo_rgb(c)
        return r // 257, g // 257, b // 257
    except Exception:
        return 233, 237, 242


def _hex(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(v))) for v in rgb)


def _mix(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def _lum(rgb):
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


def lighten(c, t=0.15):
    return _hex(_mix(_rgb(c), (255, 255, 255), t))


def darken(c, t=0.15):
    return _hex(_mix(_rgb(c), (0, 0, 0), t))


def _parent_bg(parent):
    try:
        return parent.cget("bg")
    except Exception:
        pass
    try:                                    # ttk widgets
        st = parent.cget("style") or parent.winfo_class()
        bg = ttk.Style(parent).lookup(st, "background")
        if bg:
            return bg
    except Exception:
        pass
    return BG


# ---------------------------------------------------------------- drawing
_SS = 3                         # supersampling for smooth rounded corners
_img_cache = {}


def _finish(base, silver):
    """(top, bottom, edge) colours of a button face."""
    if silver:
        top = _mix(base, (255, 255, 255), 0.75)
        bot = _mix(base, (150, 162, 180), 0.32)
        edge = _mix(base, (120, 132, 150), 0.48)
    else:
        top = _mix(base, (255, 255, 255), 0.22)
        bot = _mix(base, (0, 0, 0), 0.10)
        edge = _mix(base, (0, 0, 0), 0.22)
    return top, bot, edge


def _face(w, h, base, radius, silver, shadow):
    """A glossy rounded button face as a PIL RGBA image (cached)."""
    key = (w, h, base, radius, silver, shadow)
    im = _img_cache.get(key)
    if im is not None:
        return im
    S = _SS
    W, H = max(2, w * S), max(2, h * S)
    sh = 2 * S if shadow else 0
    bh = H - sh                                   # body height
    r = max(1, min(radius * S, bh // 2, W // 2))
    top, bot, edge = _finish(base, silver)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if shadow:
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).rounded_rectangle((S, sh, W - S - 1, H - 1), r,
                                            fill=70)
        m = m.filter(ImageFilter.GaussianBlur(S * 1.2))
        out.paste((20, 30, 50, 255), (0, 0), m)
    # vertical gradient body
    grad = Image.new("RGBA", (1, bh))
    for y in range(bh):
        t = y / max(1, bh - 1)
        if silver:              # brushed metal: bright top, soft middle band
            t = t ** 0.85
        grad.putpixel((0, y), _mix(top, bot, t) + (255,))
    grad = grad.resize((W, bh))
    mask = Image.new("L", (W, bh), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, bh - 1), r,
                                           fill=255)
    out.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(out)
    # glossy highlight across the upper part
    gl = Image.new("L", (W, bh), 0)
    ImageDraw.Draw(gl).rounded_rectangle(
        (S * 2, S, W - S * 2 - 1, int(bh * 0.48)), max(1, r - S),
        fill=60 if not silver else 90)
    gl = gl.filter(ImageFilter.GaussianBlur(S))
    out.paste((255, 255, 255, 255), (0, 0), ImageChops.multiply(gl, mask))
    # outline + inner top light line
    d.rounded_rectangle((0, 0, W - 1, bh - 1), r, outline=edge + (255,),
                        width=S)
    d.line((r, S + S // 2, W - r, S + S // 2), fill=(255, 255, 255, 120),
           width=S)
    im = out.resize((w, h), Image.LANCZOS)
    _img_cache[key] = im
    return im


# ---------------------------------------------------------------- button
class RoundButton(tk.Canvas):
    """A modern rounded button, drop-in for tk.Button.

    Understands the tk.Button options this app uses (text, command, image,
    compound, font, bg, fg, activebackground, padx, pady, width, height,
    anchor, justify, state) and ignores the purely "blocky" ones
    (relief, bd, highlightthickness...).  bg is the colour of the button
    face; leave it out (or use SILVER) for the brushed-silver finish."""

    _ALIAS = {"background": "bg", "foreground": "fg"}
    _OWN = ("text", "command", "image", "compound", "font", "bg", "fg",
            "activebackground", "activeforeground", "padx", "pady", "width",
            "height", "anchor", "justify", "state", "radius", "shadow",
            "disabledforeground", "wraplength")
    _class_bound = False

    def __init__(self, parent, text="", command=None, **kw):
        pbg = _parent_bg(parent)
        cursor = kw.pop("cursor", "hand2")
        super().__init__(parent, bg=pbg, highlightthickness=0, bd=0,
                         cursor=cursor, takefocus=0, width=10, height=10)
        self._o = {"text": text, "command": command, "image": None,
                   "compound": "center", "font": (FONT, 10, "bold"),
                   "bg": None, "fg": None, "activebackground": None,
                   "activeforeground": None, "padx": 12, "pady": 6,
                   "width": 0, "height": 0, "anchor": "center",
                   "justify": "center", "state": "normal", "radius": 10,
                   "shadow": True, "disabledforeground": None,
                   "wraplength": 0}
        self._hover = False
        self._down = False
        self._photo = None
        self._parent_bg = pbg
        self._set(kw)
        tags = list(self.bindtags())
        tags[tags.index("Canvas")] = "EZRoundButton"
        self.bindtags(tuple(tags))
        if not RoundButton._class_bound:
            RoundButton._class_bound = True
            for seq, fn in (("<Enter>", "_ev_enter"), ("<Leave>", "_ev_leave"),
                            ("<ButtonPress-1>", "_ev_press"),
                            ("<ButtonRelease-1>", "_ev_release"),
                            ("<Configure>", "_ev_configure")):
                self.bind_class("EZRoundButton", seq,
                                lambda e, f=fn: getattr(e.widget, f)(e)
                                if isinstance(e.widget, RoundButton) else None)
        self._layout()

    # ----- options
    def _set(self, kw):
        canvas_kw = {}
        for k, v in kw.items():
            k = self._ALIAS.get(k, k)
            if k in self._OWN:
                self._o[k] = v
            elif k == "cursor":
                canvas_kw[k] = v
            # relief, bd, highlight*, overrelief ... : not needed
        if canvas_kw:
            super().configure(**canvas_kw)

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        if not kw:
            return super().configure()
        self._set(kw)
        self._layout()

    config = configure

    def cget(self, key):
        key = self._ALIAS.get(key, key)
        if key in self._o:
            v = self._o[key]
            return "" if v is None else v
        return super().cget(key)

    def __getitem__(self, key):
        return self.cget(key)

    def __setitem__(self, key, value):
        self.configure(**{key: value})

    def invoke(self):
        if self._o["state"] != "disabled" and self._o["command"]:
            return self._o["command"]()

    # ----- colours for the current state
    def _base(self):
        bg = self._o["bg"]
        if self._o["state"] == "disabled":
            return _rgb("#E3E7ED"), True
        if bg in (None, "", SILVER) or (
                isinstance(bg, str) and bg.upper() in (CARD, BLUE_LIGHT,
                                                       "#FFFFFF", PANEL,
                                                       BG)):
            base, silver = _rgb(SILVER), True
            if self._down:
                base = _rgb("#D5DCE6")
            elif self._hover:
                base = _rgb(self._o["activebackground"]) if (
                    self._o["activebackground"] and
                    _lum(_rgb(self._o["activebackground"])) > 200) \
                    else _rgb("#F4F8FF")
            return base, silver
        base = _rgb(bg, self)
        if self._down:
            base = _mix(base, (0, 0, 0), 0.14)
        elif self._hover:
            ab = self._o["activebackground"]
            base = _rgb(ab, self) if ab and ab != bg else \
                _mix(base, (255, 255, 255), 0.12)
        return base, _lum(base) > 215

    def _fg(self, base, silver):
        if self._o["state"] == "disabled":
            return self._o["disabledforeground"] or "#9AA5B4"
        fg = self._o["fg"]
        if self._hover and self._o["activeforeground"] and not silver:
            fg = self._o["activeforeground"]
        if not fg or (silver and _lum(_rgb(fg, self)) > 200):
            fg = BLUE_DARK if silver or _lum(base) > 160 else "white"
        if not silver and _lum(base) < 170 and _lum(_rgb(fg, self)) < 90:
            fg = "white"
        return fg

    # ----- geometry
    def _fontobj(self):
        f = self._o["font"]
        try:
            return tkfont.Font(root=self, font=f)
        except Exception:
            return tkfont.Font(root=self, font=(FONT, 10, "bold"))

    def _content_size(self):
        f = self._fontobj()
        txt = str(self._o["text"] or "")
        lines = txt.split("\n") if txt else []
        tw = max((f.measure(ln) for ln in lines), default=0)
        th = f.metrics("linespace") * len(lines)
        img = self._o["image"]
        iw = ih = 0
        if img:
            try:
                iw, ih = int(img.width()), int(img.height())
            except Exception:
                img = None
        return f, lines, tw, th, img, iw, ih

    def _natural(self):
        f, lines, tw, th, img, iw, ih = self._content_size()
        comp = self._o["compound"] or "center"
        gap = 4 if (img and lines) else 0
        if img and lines and comp in ("top", "bottom"):
            cw, ch = max(iw, tw), ih + gap + th
        elif img and lines and comp in ("left", "right"):
            cw, ch = iw + gap + tw, max(ih, th)
        elif img:
            cw, ch = iw, ih
        else:
            cw, ch = tw, th
        px, py = int(self._o["padx"] or 0), int(self._o["pady"] or 0)
        w = cw + 2 * px
        h = ch + 2 * py
        width, height = int(self._o["width"] or 0), int(self._o["height"]
                                                        or 0)
        if width:
            w = max(w, width * f.measure("0") + 2 * px) if not img \
                else max(w, width)
        if height and not img:
            h = max(h, height * f.metrics("linespace") + 2 * py)
        sh = 2 if self._o["shadow"] else 0
        return max(16, w + 2), max(16, h + sh + 2)

    def _layout(self):
        w, h = self._natural()
        super().configure(width=w, height=h)
        self._draw()

    def _draw(self):
        W = self.winfo_width()
        H = self.winfo_height()
        nw, nh = self._natural()
        if W <= 1 or H <= 1:
            W, H = nw, nh
        self.delete("all")
        base, silver = self._base()
        shadow = bool(self._o["shadow"])
        radius = int(self._o["radius"] or 10)
        face = _face(W, H, tuple(base), radius, silver, shadow)
        self._photo = ImageTk.PhotoImage(face, master=self)
        self.create_image(0, 0, anchor="nw", image=self._photo)
        f, lines, tw, th, img, iw, ih = self._content_size()
        fg = self._fg(base, silver)
        sh = 2 if shadow else 0
        body_h = H - sh
        comp = self._o["compound"] or "center"
        gap = 4 if (img and lines) else 0
        px = int(self._o["padx"] or 0)
        if img and lines and comp in ("top", "bottom"):
            bw, bh = max(iw, tw), ih + gap + th
        elif img and lines and comp in ("left", "right"):
            bw, bh = iw + gap + tw, max(ih, th)
        elif img:
            bw, bh = iw, ih
        else:
            bw, bh = tw, th
        anchor = self._o["anchor"] or "center"
        if anchor in ("w", "nw", "sw"):
            x0 = px
        elif anchor in ("e", "ne", "se"):
            x0 = W - px - bw
        else:
            x0 = (W - bw) / 2
        y0 = (body_h - bh) / 2
        if self._down:
            y0 += 1
        just = self._o["justify"] or "center"
        tx_anchor = {"left": "nw", "right": "ne"}.get(just, "n")

        def text_at(x, y, width):
            if not lines:
                return
            if tx_anchor == "nw":
                xx = x
            elif tx_anchor == "ne":
                xx = x + width
            else:
                xx = x + width / 2
            self.create_text(xx, y, text="\n".join(lines), font=f, fill=fg,
                             anchor=tx_anchor, justify=just)
        if img and lines and comp == "top":
            self.create_image(x0 + bw / 2, y0, image=img, anchor="n")
            text_at(x0, y0 + ih + gap, bw)
        elif img and lines and comp == "bottom":
            text_at(x0, y0, bw)
            self.create_image(x0 + bw / 2, y0 + th + gap, image=img,
                              anchor="n")
        elif img and lines and comp == "left":
            self.create_image(x0, y0 + bh / 2, image=img, anchor="w")
            text_at(x0 + iw + gap, y0 + (bh - th) / 2, tw)
        elif img and lines and comp == "right":
            text_at(x0, y0 + (bh - th) / 2, tw)
            self.create_image(x0 + tw + gap, y0 + bh / 2, image=img,
                              anchor="w")
        elif img and not lines:
            self.create_image(x0 + bw / 2, y0 + bh / 2, image=img)
        elif img:                       # compound center: text over image
            self.create_image(x0 + bw / 2, y0 + bh / 2, image=img)
            text_at(x0, y0 + (bh - th) / 2, bw)
        else:
            text_at(x0, y0, bw)

    # ----- events
    def _ev_enter(self, e):
        self._hover = True
        self._draw()

    def _ev_leave(self, e):
        self._hover = False
        self._down = False
        self._draw()

    def _ev_press(self, e):
        if self._o["state"] == "disabled":
            return
        self._down = True
        self._draw()

    def _ev_release(self, e):
        was = self._down
        self._down = False
        inside = 0 <= e.x < self.winfo_width() and \
            0 <= e.y < self.winfo_height()
        self._draw()
        if was and inside and self._o["state"] != "disabled":
            cmd = self._o["command"]
            if cmd:
                cmd()

    def _ev_configure(self, e):
        self._draw()


# ---------------------------------------------------------------- styles
def setup_style(root):
    root.configure(bg=BG)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD)
    style.configure("TLabel", background=BG, foreground=TEXT, font=(FONT, 11))
    style.configure("Card.TLabel", background=CARD, foreground=TEXT,
                    font=(FONT, 11))
    style.configure("TButton", font=(FONT, 11), padding=8)
    style.configure("Orange.Horizontal.TProgressbar",
                    troughcolor="#E4E9F1", background=ORANGE,
                    thickness=14, bordercolor="#E4E9F1",
                    lightcolor=lighten(ORANGE, 0.25), darkcolor=ORANGE)
    style.configure("TCombobox", font=(FONT, 11), padding=4,
                    arrowcolor=BLUE_DARK, bordercolor=LINE,
                    lightcolor=CARD, darkcolor=LINE)
    style.map("TCombobox", fieldbackground=[("readonly", CARD)],
              selectbackground=[("readonly", CARD)],
              selectforeground=[("readonly", TEXT)],
              bordercolor=[("focus", BLUE), ("hover", BLUE)])
    style.configure("TCheckbutton", background=BG, font=(FONT, 11))
    style.configure("Card.TCheckbutton", background=CARD, font=(FONT, 11))
    style.configure("Card.TRadiobutton", background=CARD, font=(FONT, 11))
    style.map("TCheckbutton", indicatorcolor=[("selected", ORANGE)])
    style.map("Card.TCheckbutton", indicatorcolor=[("selected", ORANGE)],
              background=[("active", CARD)])
    style.configure("TNotebook", background=BG, borderwidth=0,
                    tabmargins=(2, 6, 2, 0))
    style.configure("TNotebook.Tab", font=(FONT, 10, "bold"),
                    padding=(10, 8), background=PANEL,
                    foreground=TEXT_MUTED, borderwidth=0,
                    lightcolor=PANEL, bordercolor=BG)
    style.map("TNotebook.Tab",
              background=[("selected", CARD), ("active", "#F2F5FA")],
              foreground=[("selected", ORANGE_DARK), ("active", BLUE_DARK)],
              lightcolor=[("selected", ORANGE)],
              expand=[("selected", (0, 2, 0, 0))])
    style.configure("Treeview", font=(FONT, 10), rowheight=30,
                    background=CARD, fieldbackground=CARD, borderwidth=0)
    style.configure("Treeview.Heading", font=(FONT, 9, "bold"),
                    background=PANEL, foreground=BLUE_DARK, relief="flat",
                    padding=(6, 4))
    style.map("Treeview", background=[("selected", ORANGE_LIGHT)],
              foreground=[("selected", TEXT)])
    style.map("Treeview.Heading", background=[("active", BLUE_LIGHT)])
    for o in ("Horizontal", "Vertical"):
        style.configure(f"{o}.TScrollbar", background="#C9D2DE",
                        troughcolor=BG, borderwidth=0, arrowsize=11,
                        bordercolor=BG, lightcolor="#C9D2DE",
                        darkcolor="#C9D2DE", arrowcolor=TEXT_MUTED,
                        gripcount=0)
        style.map(f"{o}.TScrollbar",
                  background=[("active", "#AEB9C8"), ("pressed", BLUE)])
    style.configure("TSeparator", background=LINE)
    return style


# ---------------------------------------------------------------- buttons
class BigButton(RoundButton):
    """Large, friendly, glossy coloured button."""

    def __init__(self, parent, text, command=None, color=ORANGE,
                 hover=None, fg="white", font_size=14, pady=14, padx=18,
                 **kw):
        self._color = color
        self._hover_col = hover
        kw.setdefault("radius", 12)
        super().__init__(parent, text=text, command=command, bg=color,
                         fg=fg, activebackground=hover,
                         font=(FONT, font_size, "bold"), padx=padx,
                         pady=max(4, pady - 4), **kw)

    def set_color(self, color, hover=None):
        self._color = color
        self._hover_col = hover
        self.configure(bg=color, activebackground=hover)


class GhostButton(RoundButton):
    """Secondary button: brushed silver."""

    def __init__(self, parent, text, command=None, font_size=11, **kw):
        kw.setdefault("radius", 9)
        super().__init__(parent, text=text, command=command, bg=SILVER,
                         fg=BLUE_DARK, font=(FONT, font_size, "bold"),
                         padx=12, pady=5, **kw)


class ToggleButton(RoundButton):
    """A choice button that shows selected (glossy orange) or not
    (brushed silver)."""

    def __init__(self, parent, text, command=None, font_size=12, **kw):
        kw.setdefault("radius", 9)
        super().__init__(parent, text=text, command=command,
                         font=(FONT, font_size, "bold"), padx=14, pady=8,
                         justify="center", **kw)
        self.set_selected(False)

    def set_selected(self, on):
        if on:
            self.configure(bg=ORANGE, fg="white",
                           activebackground=lighten(ORANGE, 0.1))
        else:
            self.configure(bg=SILVER, fg=BLUE_DARK, activebackground=None)


# ---------------------------------------------------------------- equalizer
class Equalizer(tk.Canvas):
    """A little LED-style music equalizer.  It dances while
    is_playing() is true and settles down when the music stops.
    (It is an animation that follows play / pause - it does not
    analyse the actual sound.)"""

    def __init__(self, parent, is_playing, bars=16, segs=8, width=150,
                 height=30, bg=None):
        bg = bg or _parent_bg(parent)
        super().__init__(parent, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0)
        self.is_playing = is_playing
        self.bars, self.segs = bars, segs
        self._lv = [0.0] * bars
        self._pk = [0.0] * bars
        self._t = 0.0
        self._items = []
        self._caps = []
        self._dim = [_hex(_mix(_rgb(c), _rgb(bg), 0.82)) for c in
                     self._seg_colors()]
        self._build(width, height)
        self.bind("<Configure>", lambda e: self._build(e.width, e.height))
        self.after(60, self._tick)

    def _seg_colors(self):
        out = []
        n = len(EQ_COLORS)
        for s in range(self.segs):
            out.append(EQ_COLORS[min(n - 1, int(s * n / self.segs))])
        return out

    def _build(self, W, H):
        self.delete("all")
        self._items = []
        self._caps = []
        gap = 2
        bw = max(2, (W - gap * (self.bars + 1)) / self.bars)
        sg = 1
        sh = max(1, (H - 4 - sg * (self.segs - 1)) / self.segs)
        for b in range(self.bars):
            x0 = gap + b * (bw + gap)
            col = []
            for s in range(self.segs):
                y1 = H - 2 - s * (sh + sg)
                col.append(self.create_rectangle(
                    x0, y1 - sh, x0 + bw, y1, outline="",
                    fill=self._dim[s]))
            self._items.append(col)
            self._caps.append(self.create_rectangle(
                x0, H - 3, x0 + bw, H - 2, outline="", fill="white",
                state="hidden"))
        self._geom = (H, sh, sg, bw)

    def _tick(self):
        if not self.winfo_exists():
            return
        try:
            on = bool(self.is_playing())
        except Exception:
            on = False
        self._t += 0.06
        t = self._t
        beat = 0.55 + 0.45 * abs(math.sin(t * math.pi * 2.05))
        cols = self._seg_colors()
        H, sh, sg, bw = self._geom
        busy = on
        for b in range(self.bars):
            if on:
                low = 1.0 - b / self.bars          # bass on the left
                wave = 0.5 + 0.5 * math.sin(t * (3.1 + b * 0.37) + b)
                target = (0.18 + 0.55 * wave * (0.6 + 0.4 * random.random())
                          + 0.35 * beat * low * low)
                target = min(1.0, target)
            else:
                target = 0.0
            lv = self._lv[b]
            lv += (target - lv) * (0.45 if target > lv else 0.18)
            self._lv[b] = lv
            pk = self._pk[b]
            pk = lv if lv > pk else max(0.0, pk - 0.025)
            self._pk[b] = pk
            if lv > 0.01:
                busy = True
            lit = int(round(lv * self.segs))
            for s, item in enumerate(self._items[b]):
                self.itemconfig(item, fill=cols[s] if s < lit else
                                self._dim[s])
            if pk > 0.04:
                s = min(self.segs - 1, int(pk * self.segs))
                y1 = H - 2 - s * (sh + sg)
                x0 = self.coords(self._items[b][0])[0]
                self.coords(self._caps[b], x0, y1 - sh - 2, x0 + bw,
                            y1 - sh - 1)
                self.itemconfig(self._caps[b], state="normal")
            else:
                self.itemconfig(self._caps[b], state="hidden")
        self.after(55 if busy else 250, self._tick)


# ---------------------------------------------------------------- layout
def card(parent, **kw):
    """White card frame."""
    f = tk.Frame(parent, bg=CARD, bd=0, highlightthickness=1,
                 highlightbackground=LINE, highlightcolor=LINE, **kw)
    return f


def accent_line(parent, height=3):
    """A thin colourful gradient line (orange - pink - purple - blue)."""
    cv = tk.Canvas(parent, height=height, highlightthickness=0, bd=0,
                   bg=ACCENT_LINE[0])
    holder = {}

    def draw(e=None):
        w = max(2, cv.winfo_width())
        stops = [_rgb(c) for c in ACCENT_LINE]
        im = Image.new("RGB", (w, 1))
        n = len(stops) - 1
        for x in range(w):
            p = x / max(1, w - 1) * n
            i = min(n - 1, int(p))
            im.putpixel((x, 0), _mix(stops[i], stops[i + 1], p - i))
        holder["img"] = ImageTk.PhotoImage(im.resize((w, height)),
                                           master=cv)
        cv.delete("all")
        cv.create_image(0, 0, anchor="nw", image=holder["img"])
    cv.bind("<Configure>", draw)
    return cv


def header_bar(parent, title, on_back=None, right_text=None):
    bar = tk.Frame(parent, bg=BLUE_DARK, height=58)
    bar.pack(fill="x", side="top")
    bar.pack_propagate(False)
    accent_line(parent).pack(fill="x", side="top")
    if on_back:
        RoundButton(bar, text="←  Home", command=on_back, bg="#26324D",
                    fg="white", activebackground="#33416A",
                    font=(FONT, 11, "bold"), padx=14, pady=5, radius=14,
                    shadow=False).pack(side="left", padx=(12, 4))
    tk.Label(bar, text=title, bg=BLUE_DARK, fg="white",
             font=(FONT, 16, "bold")).pack(side="left", padx=12)
    from . import __version__
    tk.Label(bar, text=right_text or f"EZ Video Maker {__version__}",
             bg=BLUE_DARK, fg=lighten(ORANGE, 0.1),
             font=(FONT, 11, "bold")).pack(side="right", padx=18)
    return bar


def label(parent, text, bold=False, muted=False, size=11, bg=CARD, **kw):
    return tk.Label(parent, text=text, bg=bg,
                    fg=TEXT_MUTED if muted else TEXT,
                    font=(FONT, size, "bold" if bold else "normal"), **kw)


def hscale(parent, from_, to, var=None, length=160, bg=CARD, resolution=1,
           command=None):
    s = tk.Scale(parent, from_=from_, to=to, orient="horizontal",
                 variable=var, bg=bg, highlightthickness=0, length=length,
                 troughcolor="#DCE4F0", fg=TEXT, font=(FONT, 9),
                 resolution=resolution, command=command, sliderlength=18,
                 sliderrelief="flat", bd=0, width=12,
                 activebackground=ORANGE)
    return s
