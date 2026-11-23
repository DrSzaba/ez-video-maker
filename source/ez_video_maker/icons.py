"""
EZ Video Maker - colourful picture icons for the buttons.

Drawn from the Windows colour emoji font (Segoe UI Emoji, part of every
Windows 10/11), so no image files are needed. If the font is missing the
buttons simply show text.
"""
import os

from PIL import Image, ImageDraw, ImageFont, ImageTk

_FONT_FILES = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts",
                            "seguiemj.ttf")]
_cache = {}
_fonts = {}


def _font(px):
    if px not in _fonts:
        f = None
        for path in _FONT_FILES:
            if os.path.isfile(path):
                try:
                    f = ImageFont.truetype(path, px)
                    break
                except Exception:
                    pass
        _fonts[px] = f
    return _fonts[px]


def image(emoji, size=32):
    """A PIL image of the emoji, size x size pixels (or None)."""
    big = size * 3
    f = _font(big)
    if f is None:
        return None
    im = Image.new("RGBA", (big * 2, big * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    try:
        d.text((big // 2, big // 2), emoji, font=f, embedded_color=True,
               fill=(40, 40, 40, 255))
    except Exception:
        return None
    box = im.getbbox()
    if not box:
        return None
    im = im.crop(box)
    w, h = im.size
    s = size / max(w, h)
    im = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)
    return out


def get(emoji, size=32):
    """A Tk PhotoImage of the emoji (kept in a cache), or None."""
    key = (emoji, size)
    if key not in _cache:
        im = image(emoji, size)
        _cache[key] = ImageTk.PhotoImage(im) if im is not None else None
    return _cache[key]
