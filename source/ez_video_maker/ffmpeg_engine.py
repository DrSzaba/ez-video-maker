"""
EZ Video Maker - FFmpeg engine.
Finds the bundled FFmpeg, probes media files, builds conversion commands and
runs jobs with live progress and cancel support. Everything is local.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

IS_WIN = os.name == "nt"
_CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0
POPEN_FLAGS = {"creationflags": _CREATE_NO_WINDOW} if IS_WIN else {}


def app_dir():
    """Folder that holds run_app.py, ez_video_maker/ and assets/."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def install_root():
    """Folder the installer created (one above app_dir)."""
    return os.path.dirname(app_dir())


def assets_dir():
    return os.path.join(app_dir(), "assets")


def font_file():
    """Bundled font used for on-screen text (works on every PC)."""
    p = os.path.join(assets_dir(), "fonts", "DejaVuSans-Bold.ttf")
    if os.path.isfile(p):
        return p
    for c in (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.isfile(c):
            return c
    return None


def cache_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), ".cache")
    d = os.path.join(base, "EZVideoMaker", "cache")
    os.makedirs(d, exist_ok=True)
    return d


def candidate_roots():
    """Every folder that could be the install folder (the one that holds
    app\\, python\\ and ffmpeg\\)."""
    roots = [install_root(), app_dir()]
    try:
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        roots += [os.path.dirname(exe_dir), exe_dir]
    except Exception:
        pass
    la = os.environ.get("LOCALAPPDATA")
    if la:
        roots.append(os.path.join(la, "Programs", "EZ Video Maker"))
    if IS_WIN:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\EZVideoMaker") as k:
                v, _ = winreg.QueryValueEx(k, "InstallDir")
                if v:
                    roots.append(v)
        except Exception:
            pass
    out = []
    for r in roots:
        r = os.path.normpath(r)
        if r not in out:
            out.append(r)
    return out


def ffmpeg_search_dirs():
    dirs = []
    for r in candidate_roots():
        for d in (os.path.join(r, "ffmpeg", "bin"), os.path.join(r, "ffmpeg")):
            if d not in dirs:
                dirs.append(d)
    return dirs


def _find(names):
    for d in ffmpeg_search_dirs():
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def engine_packs():
    """Backup copies of the engine (a zip renamed engine.pack) that the
    installer leaves next to ffmpeg\\bin, used for self-repair."""
    out = []
    for r in candidate_roots():
        p = os.path.join(r, "ffmpeg", "engine.pack")
        if os.path.isfile(p) and p not in out:
            out.append(p)
    return out


def repair_engine():
    """If ffmpeg.exe / ffprobe.exe vanished (antivirus quarantine is the
    usual reason), put them back from engine.pack. Returns ffmpeg path or
    None."""
    import tarfile
    for pack in engine_packs():
        dest = os.path.join(os.path.dirname(pack), "bin")
        try:
            os.makedirs(dest, exist_ok=True)
            with tarfile.open(pack, "r:xz") as t:
                for m in t.getmembers():
                    base = os.path.basename(m.name)
                    if not base or not m.isfile():
                        continue
                    target = os.path.join(dest, base)
                    if os.path.isfile(target) and os.path.getsize(target) > 0:
                        continue
                    src = t.extractfile(m)
                    with open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
                    if not IS_WIN:
                        os.chmod(target, 0o755)
        except Exception:
            continue
        found = find_ffmpeg()
        if found and find_ffprobe():
            return found
    return None


def engine_report():
    """Plain-English list of where the engine was looked for."""
    lines = []
    for d in ffmpeg_search_dirs():
        for n in ("ffmpeg.exe", "ffprobe.exe"):
            p = os.path.join(d, n)
            if os.path.isdir(d):
                lines.append(f"{'FOUND ' if os.path.isfile(p) else 'missing'}: {p}")
    if not lines:
        lines.append("None of the expected folders exist:\n  " +
                     "\n  ".join(ffmpeg_search_dirs()[:4]))
    packs = engine_packs()
    lines.append("Backup pack: " + (packs[0] if packs else "not found"))
    return "\n".join(lines)


def find_ffmpeg():
    return _find(["ffmpeg.exe", "ffmpeg"])


def find_ffprobe():
    return _find(["ffprobe.exe", "ffprobe"])


def find_ffplay():
    return _find(["ffplay.exe", "ffplay"])


# ---------------------------------------------------------------- formats
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".webm", ".mpeg",
              ".mpg", ".m4v", ".3gp", ".ts", ".mts", ".m2ts", ".vob", ".ogv",
              ".f4v", ".asf", ".divx", ".mxf", ".gif"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma", ".aiff",
              ".aif", ".opus", ".amr", ".ac3"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

AUDIO_TARGETS = ["MP3", "WAV", "M4A", "AAC", "FLAC", "OGG", "WMA", "AIFF",
                 "OPUS"]
VIDEO_TARGETS = ["MP4", "MOV", "MKV", "AVI", "WEBM", "WMV", "MPG", "M4V",
                 "3GP", "TS", "FLV", "GIF"]

QUALITY_PRESETS = {
    "Small File":   {"crf": "30", "preset": "faster", "abr": "96k"},
    "Balanced":     {"crf": "23", "preset": "medium", "abr": "160k"},
    "High Quality": {"crf": "19", "preset": "medium", "abr": "224k"},
    "Best Quality": {"crf": "16", "preset": "slow",   "abr": "320k"},
}

# Video shapes, in the words people use.  (label -> (w, h))
SHAPES = {
    "TikTok / Reels / Shorts - Vertical (9:16)": (1080, 1920),
    "YouTube / DistroKid - Horizontal (16:9)": (1920, 1080),
    "Square post (1:1)": (1080, 1080),
    "Instagram / Facebook post (4:5)": (1080, 1350),
    "Facebook classic (4:3)": (1440, 1080),
    "720p Horizontal": (1280, 720),
    "4K Horizontal": (3840, 2160),
    "4K Vertical": (2160, 3840),
}
SHAPE_VERTICAL = "TikTok / Reels / Shorts - Vertical (9:16)"
SHAPE_HORIZONTAL = "YouTube / DistroKid - Horizontal (16:9)"
SHAPE_SQUARE = "Square post (1:1)"
SHAPE_45 = "Instagram / Facebook post (4:5)"

FIT_MODES = ["Fill the screen (no black bars)",
             "Blur background (blurred sides)",
             "Fit whole picture (black bars)"]
# names used by earlier versions -> current name
OLD_FIT_NAMES = {"Fill (zoom in, cut edges)": FIT_MODES[0],
                 "Blur background (fills the screen)": FIT_MODES[1],
                 "Fit (black bars)": FIT_MODES[2],
                 "Fill the screen (zoom in, no black bars)": FIT_MODES[0],
                 "Blur background (whole picture, blurred sides)": FIT_MODES[1],
                 "Fit (whole picture, black bars)": FIT_MODES[2]}

_AUDIO_CODEC = {
    "MP3":  ["-c:a", "libmp3lame"],
    "WAV":  ["-c:a", "pcm_s16le"],
    "M4A":  ["-c:a", "aac"],
    "AAC":  ["-c:a", "aac"],
    "FLAC": ["-c:a", "flac"],
    "OGG":  ["-c:a", "libvorbis"],
    "WMA":  ["-c:a", "wmav2"],
    "AIFF": ["-c:a", "pcm_s16be"],
    "OPUS": ["-c:a", "opus", "-strict", "-2"],
}
_LOSSY_AUDIO = {"MP3", "M4A", "AAC", "OGG", "WMA", "OPUS"}


def _opus_bitrate(abr):
    try:
        v = int(str(abr).lower().rstrip("k"))
    except (ValueError, AttributeError):
        return "160k"
    return f"{min(v, 256)}k"


def fit_filter(w, h, mode, sharp=False):
    """Filter that makes any picture exactly w x h.
    sharp=True uses Lanczos resizing (used for 4K upscale)."""
    mode = OLD_FIT_NAMES.get(mode, mode or "").lower()
    fl = ":flags=lanczos" if sharp else ""
    if mode.startswith("fill"):
        return (f"scale={w}:{h}:force_original_aspect_ratio=increase{fl},"
                f"crop={w}:{h}")
    if mode.startswith("blur"):
        return (f"split[bgin][fgin];"
                f"[bgin]scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},boxblur=luma_radius=min(h\\,w)/20:"
                f"luma_power=1:chroma_radius=min(cw\\,ch)/20:chroma_power=1,"
                f"eq=brightness=-0.08[bg];"
                f"[fgin]scale={w}:{h}:force_original_aspect_ratio=decrease{fl}[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease{fl},"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2")


# ---------------------------------------------------------------- probing
def _run_quiet(cmd, timeout=40):
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, **POPEN_FLAGS)


def probe_info(path):
    """dict: width, height, duration, has_audio, has_video, fps, rotation."""
    info = {"width": None, "height": None, "duration": None,
            "has_audio": False, "has_video": False, "fps": None,
            "rotation": 0}
    ffprobe = find_ffprobe()
    if not ffprobe or not os.path.isfile(path):
        return info
    try:
        out = _run_quiet([ffprobe, "-v", "error", "-show_streams",
                          "-show_format", "-of", "json", path])
        data = json.loads(out.stdout or "{}")
        for s in data.get("streams", []):
            if s.get("codec_type") == "video" and \
                    s.get("disposition", {}).get("attached_pic", 0) != 1 \
                    and not info["has_video"]:
                info["has_video"] = True
                info["width"] = s.get("width")
                info["height"] = s.get("height")
                fr = s.get("avg_frame_rate") or s.get("r_frame_rate") or ""
                if "/" in fr:
                    a, b = fr.split("/")
                    if float(b) > 0:
                        info["fps"] = float(a) / float(b)
                for sd in s.get("side_data_list", []) or []:
                    if "rotation" in sd:
                        info["rotation"] = int(sd["rotation"])
                tags = s.get("tags", {}) or {}
                if "rotate" in tags:
                    try:
                        info["rotation"] = int(tags["rotate"])
                    except ValueError:
                        pass
            elif s.get("codec_type") == "audio":
                info["has_audio"] = True
        dur = data.get("format", {}).get("duration")
        if dur:
            info["duration"] = float(dur)
        if info["duration"] is None:
            for s in data.get("streams", []):
                if s.get("duration"):
                    info["duration"] = float(s["duration"])
                    break
    except Exception:
        pass
    return info


def probe_duration(path):
    return probe_info(path).get("duration")


# ---------------------------------------------------------------- jobs
class FFmpegJob:
    """One FFmpeg run with progress callbacks and cancel support."""

    def __init__(self, args, duration=None, on_progress=None, on_done=None):
        self.args = args
        self.duration = duration
        self.on_progress = on_progress
        self.on_done = on_done
        self.proc = None
        self.cancelled = False
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def run_blocking(self):
        self._run()

    def cancel(self):
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass

    def _run(self):
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            if self.on_done:
                self.on_done(False, "The video engine (FFmpeg) is missing. "
                                    "Please run the EZ Video Maker setup "
                                    "again.")
            return
        cmd = ([ffmpeg, "-hide_banner", "-y"] + list(self.args) +
               ["-progress", "pipe:1", "-nostats", "-loglevel", "error"])
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", **POPEN_FLAGS)
        except Exception as e:
            if self.on_done:
                self.on_done(False, f"Could not start FFmpeg: {e}")
            return
        start_time = time.time()
        for line in self.proc.stdout:
            line = line.strip()
            m = re.match(r"out_time_(?:ms|us)=(\d+)", line)
            if m and self.duration:
                secs = int(m.group(1)) / 1_000_000
                pct = max(0.0, min(100.0, secs / self.duration * 100))
                elapsed = time.time() - start_time
                eta = elapsed * (100 - pct) / pct if pct > 1 else None
                if self.on_progress:
                    self.on_progress(pct, secs, eta)
        self.proc.wait()
        try:
            stderr_tail = (self.proc.stderr.read() or "")[-900:]
        except Exception:
            stderr_tail = ""
        if self.cancelled:
            if self.on_done:
                self.on_done(False, "Cancelled.")
        elif self.proc.returncode == 0:
            if self.on_progress:
                self.on_progress(100.0, self.duration or 0, 0)
            if self.on_done:
                self.on_done(True, "Done!")
        else:
            if self.on_done:
                self.on_done(False, "FFmpeg reported a problem:\n" +
                             stderr_tail.strip())


def run_ffmpeg(args, duration=None, on_progress=None, cancel_flag=None):
    """Run ffmpeg synchronously. Returns (ok, message).
    cancel_flag: object with .cancelled attribute checked by caller."""
    result = {}
    job = FFmpegJob(args, duration=duration, on_progress=on_progress,
                    on_done=lambda ok, msg: result.update(ok=ok, msg=msg))
    if cancel_flag is not None:
        cancel_flag.active_job = job
    job.run_blocking()
    if cancel_flag is not None:
        cancel_flag.active_job = None
    return result.get("ok", False), result.get("msg", "")


def unique_path(path):
    """Never overwrite: add (1), (2)..."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


# ---------------------------------------------------------------- convert
def build_convert_args(src, dst, target_fmt, quality="Balanced",
                       advanced=None, shape=None, fit_mode=None):
    """
    Build ffmpeg args for one conversion.
    target_fmt: 'MP4', 'MP3', ...
    shape: None (keep) or (w, h) to reshape the picture (TikTok etc.)
    advanced: optional dict: resolution, fps, vbitrate, abitrate, vcodec
    """
    advanced = advanced or {}
    q = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["Balanced"])
    fmt = target_fmt.upper()
    args = ["-i", src]

    if fmt in AUDIO_TARGETS:
        args += ["-vn"] + _AUDIO_CODEC[fmt]
        abr = advanced.get("abitrate") or q["abr"]
        if fmt == "OPUS":
            abr = _opus_bitrate(abr)
        if fmt in _LOSSY_AUDIO:
            args += ["-b:a", abr]
        if fmt == "WAV" or fmt == "AIFF":
            args += ["-ar", "44100"]
        args += [dst]
        return args

    if fmt == "GIF":
        w = 480
        vf = f"fps=12,scale={w}:-2:flags=lanczos,split[s0][s1];" \
             f"[s0]palettegen[p];[s1][p]paletteuse"
        args += ["-filter_complex", vf, "-loop", "0", dst]
        return args

    vcodec = advanced.get("vcodec") or {
        "WEBM": "libvpx-vp9", "WMV": "wmv2", "MPG": "mpeg2video",
        "FLV": "flv", "AVI": "libx264", "3GP": "libx264",
    }.get(fmt, "libx264")

    vf = []
    if shape:
        w, h = shape
        vf.append(fit_filter(w, h, fit_mode or FIT_MODES[1]))
    elif advanced.get("resolution"):
        w, h = advanced["resolution"].lower().split("x")
        vf.append(fit_filter(int(w), int(h), "fit"))
    if vcodec in ("libx264", "libx265"):
        vf.append("format=yuv420p")
    if vf:
        args += ["-vf", ",".join(vf)]

    args += ["-c:v", vcodec]
    if vcodec == "libx264":
        args += ["-preset", q["preset"], "-crf", q["crf"]]
        if fmt == "3GP":
            args += ["-profile:v", "baseline", "-level", "3.0"]
    elif vcodec == "libx265":
        args += ["-preset", q["preset"], "-crf", str(int(q["crf"]) + 4)]
    elif vcodec == "libvpx-vp9":
        args += ["-crf", q["crf"], "-b:v", "0", "-row-mt", "1"]
    elif not advanced.get("vbitrate"):
        args += ["-q:v", "4"]
    if advanced.get("vbitrate"):
        args += ["-b:v", advanced["vbitrate"]]
    if advanced.get("fps"):
        args += ["-r", str(advanced["fps"])]

    abr = advanced.get("abitrate") or q["abr"]
    if fmt == "WEBM":
        args += ["-c:a", "libvorbis", "-b:a", abr]
    elif fmt == "MPG":
        args += ["-c:a", "mp2", "-b:a", "192k"]
    elif fmt == "WMV":
        args += ["-c:a", "wmav2", "-b:a", "160k"]
    elif fmt == "FLV":
        args += ["-c:a", "libmp3lame", "-b:a", abr, "-ar", "44100"]
    elif fmt == "3GP":
        args += ["-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2"]
    else:
        args += ["-c:a", "aac", "-b:a", abr]
    if fmt in ("MP4", "MOV", "M4V"):
        args += ["-movflags", "+faststart"]
    args += [dst]
    return args


def open_folder(path):
    """Open a folder (or select a file) in the file manager."""
    try:
        if IS_WIN:
            if os.path.isfile(path):
                subprocess.Popen(["explorer", "/select,", path])
            else:
                os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path if os.path.isdir(path)
                              else os.path.dirname(path)])
        else:
            subprocess.Popen(["xdg-open", path if os.path.isdir(path)
                              else os.path.dirname(path)])
    except Exception:
        pass
