"""
EZ Video Maker - pictures of media: frame grabs, thumbnails, waveforms.
Returns Pillow images (in memory) with a small cache so the preview and the
storyboard feel instant.
"""

import io
import os
import subprocess
import threading
from collections import OrderedDict

from PIL import Image, ImageDraw, ImageOps

from . import ffmpeg_engine as ff

_cache = OrderedDict()
_lock = threading.Lock()
_CACHE_MAX = 400


def _key(path, t, w, extra=""):
    try:
        mt = os.path.getmtime(path)
    except OSError:
        mt = 0
    return (path, mt, round(t, 2), w, extra)


def _remember(key, img):
    with _lock:
        _cache[key] = img
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return img


def _cached(key):
    with _lock:
        img = _cache.get(key)
        if img is not None:
            _cache.move_to_end(key)
        return img


def is_image(path):
    return os.path.splitext(path)[1].lower() in ff.IMAGE_EXTS


def is_audio(path):
    return os.path.splitext(path)[1].lower() in ff.AUDIO_EXTS


def load_photo(path, width):
    key = _key(path, 0, width, "photo")
    img = _cached(key)
    if img is not None:
        return img
    try:
        im = Image.open(path)
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        if im.width > width:
            im = im.resize((width, max(1, int(im.height * width / im.width))),
                           Image.LANCZOS)
        return _remember(key, im)
    except Exception:
        return None


def grab_frame(path, t, width):
    """Return a PIL image of the video frame at t seconds (or None)."""
    if is_image(path):
        return load_photo(path, width)
    key = _key(path, t, width)
    img = _cached(key)
    if img is not None:
        return img
    ffmpeg = ff.find_ffmpeg()
    if not ffmpeg or not os.path.isfile(path):
        return None
    w = width - (width % 2)
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error"]
    if t >= 0.05:
        cmd += ["-ss", f"{t:.3f}"]
    cmd += ["-i", path, "-frames:v", "1", "-vf", f"scale={w}:-2",
            "-f", "image2pipe", "-vcodec", "png", "-"]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=30,
                             **ff.POPEN_FLAGS)
        if not out.stdout:
            # maybe past the end: try the very last frames
            cmd2 = [ffmpeg, "-hide_banner", "-loglevel", "error",
                    "-sseof", "-0.5", "-i", path, "-frames:v", "1",
                    "-vf", f"scale={w}:-2", "-f", "image2pipe",
                    "-vcodec", "png", "-"]
            out = subprocess.run(cmd2, capture_output=True, timeout=30,
                                 **ff.POPEN_FLAGS)
        if not out.stdout:
            return None
        im = Image.open(io.BytesIO(out.stdout)).convert("RGB")
        im.load()
        return _remember(key, im)
    except Exception:
        return None


def waveform(path, width=600, height=120, color="#F2811D"):
    """PNG picture of an audio file's waveform as a PIL image."""
    key = _key(path, 0, width, f"wave{height}")
    img = _cached(key)
    if img is not None:
        return img
    ffmpeg = ff.find_ffmpeg()
    if not ffmpeg:
        return None
    w = width - (width % 2)
    col = color.lstrip("#")
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path,
           "-filter_complex",
           f"aformat=channel_layouts=mono,showwavespic=s={w}x{height}:"
           f"colors=0x{col}", "-frames:v", "1", "-f", "image2pipe",
           "-vcodec", "png", "-"]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=60,
                             **ff.POPEN_FLAGS)
        if not out.stdout:
            return None
        im = Image.open(io.BytesIO(out.stdout)).convert("RGBA")
        bg = Image.new("RGBA", im.size, "#101826")
        bg.alpha_composite(im)
        return _remember(key, bg.convert("RGB"))
    except Exception:
        return None


def thumbnail(path, width=160, height=90, t=0.5):
    """Small storyboard picture, letterboxed to width x height."""
    key = _key(path, t, width, f"thumb{height}")
    img = _cached(key)
    if img is not None:
        return img
    if is_audio(path):
        src = waveform(path, width, height)
    else:
        src = grab_frame(path, t, width)
    canvas = Image.new("RGB", (width, height), "#0A0E14")
    if src is not None:
        fitted = ImageOps.contain(src, (width, height), Image.LANCZOS)
        canvas.paste(fitted, ((width - fitted.width) // 2,
                              (height - fitted.height) // 2))
    else:
        d = ImageDraw.Draw(canvas)
        d.text((8, height // 2 - 6), "no picture", fill="#5B6B7C")
    return _remember(key, canvas)


def fit_into(img, cw, ch):
    """Scale a PIL image to fit inside cw x ch (never upscales more than 2x)."""
    if img is None:
        return None
    scale = min(cw / img.width, ch / img.height, 2.0)
    nw, nh = max(1, int(img.width * scale)), max(1, int(img.height * scale))
    if (nw, nh) == img.size:
        return img
    return img.resize((nw, nh), Image.BILINEAR)


def freeze_frame_png(path, t, size):
    """Save a full-size frame as PNG (for freeze frames). Returns path."""
    ffmpeg = ff.find_ffmpeg()
    if not ffmpeg:
        return None
    w, h = size
    out = os.path.join(ff.cache_dir(),
                       f"freeze_{abs(hash((path, round(t, 2))))}.png")
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if t >= 0.05:
        cmd += ["-ss", f"{t:.3f}"]
    cmd += ["-i", path, "-frames:v", "1", out]
    try:
        subprocess.run(cmd, capture_output=True, timeout=30, **ff.POPEN_FLAGS)
        return out if os.path.isfile(out) and os.path.getsize(out) > 0 \
            else None
    except Exception:
        return None


def clear_cache():
    with _lock:
        _cache.clear()
