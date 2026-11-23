"""
EZ Video Maker - project data model.
Pure Python (no tkinter) so everything can be tested without a screen.
A project is: an ordered storyboard of clips, text items, sound items,
and the video shape.  Undo/redo and save/open included.
"""

import copy
import json
import os
import uuid

from . import ffmpeg_engine as ff

COLOR_STYLES = ["Normal", "Black & White", "Warm", "Cool", "Brighter",
                "Vintage", "Vivid", "Dramatic"]
COLOR_FILTERS = {
    "Black & White": "hue=s=0",
    "Warm": "colorbalance=rs=.12:gs=.03:bs=-.12",
    "Cool": "colorbalance=rs=-.12:bs=.12",
    "Brighter": "eq=brightness=0.08:saturation=1.1",
    "Vintage": "curves=preset=vintage,eq=saturation=0.85",
    "Vivid": "eq=saturation=1.45:contrast=1.08",
    "Dramatic": "eq=contrast=1.3:brightness=-0.05:saturation=0.9",
}

# Transitions ("Animations" in Movie Maker), grouped like a gallery.
# label -> FFmpeg xfade name.  Labels from older versions are kept.
TRANSITION_GROUPS = [
    ("Fades", [("Crossfade", "fade"), ("Fade through black", "fadeblack"),
               ("Fade through white", "fadewhite"), ("Dissolve", "dissolve"),
               ("Fade through gray", "fadegrays"), ("Quick fade", "fadefast"),
               ("Slow fade", "fadeslow")]),
    ("Cinematic", [("Cinematic blur", "hblur"), ("Zoom in", "zoomin"),
                   ("Soft slide left", "smoothleft"),
                   ("Soft slide right", "smoothright"),
                   ("Soft slide up", "smoothup"),
                   ("Soft slide down", "smoothdown"),
                   ("Radar sweep", "radial"), ("Pixelate", "pixelize"),
                   ("Squeeze", "squeezeh")]),
    ("Slides", [("Slide left", "slideleft"), ("Slide right", "slideright"),
                ("Slide up", "slideup"), ("Slide down", "slidedown"),
                ("Cover left", "coverleft"), ("Cover right", "coverright"),
                ("Reveal left", "revealleft"),
                ("Reveal right", "revealright")]),
    ("Wipes", [("Wipe left", "wipeleft"), ("Wipe right", "wiperight"),
               ("Wipe up", "wipeup"), ("Wipe down", "wipedown"),
               ("Diagonal wipe", "wipetl"), ("Wind", "hlwind")]),
    ("Shapes", [("Circle open", "circleopen"),
                ("Circle close", "circleclose"), ("Circle", "circlecrop"),
                ("Rectangle", "rectcrop"), ("Doors open", "horzopen"),
                ("Doors close", "horzclose"), ("Blinds", "hlslice"),
                ("Diagonal", "diagtl")]),
]
XFADE_NAMES = {lbl: name for _, items in TRANSITION_GROUPS
               for lbl, name in items}
TRANSITIONS = ["Cut"] + list(XFADE_NAMES)
TRANSITION_SECONDS = 1.0        # default length of a new transition
TRANSITION_MIN, TRANSITION_MAX = 0.25, 3.0

# Pan and zoom - slow camera moves over a photo or video
MOTIONS = ["None", "Zoom in", "Zoom out", "Pan left", "Pan right",
           "Pan up", "Pan down", "Cinematic drift", "Ken Burns"]

# Visual effects (the "Cinematic" set in Movie Maker)
EFFECTS = ["None", "Cinema bars (widescreen)", "Film look", "Old movie",
           "Dark edges (vignette)", "Sharpen"]

PHOTO_MIN, PHOTO_MAX = 1.0, 300.0     # how long a photo can stay on screen
FIT_PHOTO_MAX = 4 * 3600.0            # Fit to music may go longer (hour-long mixes)


def _say_time(t):
    """3 seconds / 2 min 05 s / 1 h 02 min"""
    t = int(round(t))
    if t < 60:
        return f"{t} second{'s' if t != 1 else ''}"
    if t < 3600:
        return f"{t // 60} min {t % 60:02d} s"
    return f"{t // 3600} h {t % 3600 // 60:02d} min"

TEXT_STYLES = ["Title (big, middle)", "Caption (bottom)", "Credits (scrolling)",
               "Top banner"]
TEXT_SIZES = ["Small", "Medium", "Large", "Huge"]
TEXT_COLORS = {"White": "white", "Yellow": "#FFE14D", "Orange": "#F2811D",
               "Blue": "#4DA3FF", "Black": "black", "Red": "#FF4D4D",
               "Green": "#5CE38A", "Pink": "#FF7BD4"}
SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0]


def _new_id():
    return uuid.uuid4().hex[:10]


class Clip:
    """One clip on the storyboard (a video or a photo)."""

    def __init__(self, path=None, kind="video", source_duration=None):
        self.id = _new_id()
        self.path = path
        self.kind = kind                  # video / photo
        self.name = os.path.basename(path) if path else "clip"
        self.source_duration = source_duration
        self.in_point = 0.0
        self.out_point = (source_duration if kind == "video" and
                          source_duration else 5.0)
        self.speed = 1.0
        self.volume = 1.0
        self.muted = False
        self.rotate = 0
        self.flip_h = False
        self.flip_v = False
        self.crop = None                  # (left, top, right, bottom) percent
        self.fade_in = 0.0
        self.fade_out = 0.0
        self.color = "Normal"
        self.transition = "Cut"           # transition INTO this clip
        self.has_audio = True
        self.src_w = None
        self.src_h = None
        self.zoom = False                 # (old versions) slow zoom on/off
        self.transition_seconds = TRANSITION_SECONDS
        self.motion = "None"              # pan and zoom
        self.effect = "None"              # visual effect

    @property
    def duration(self):
        """Seconds this clip lasts in the finished video."""
        return max(0.1, (self.out_point - self.in_point) /
                   max(0.05, self.speed))

    @property
    def is_photo(self):
        return self.kind == "photo"

    def to_dict(self):
        return dict(self.__dict__)

    @property
    def motion_name(self):
        if self.motion and self.motion != "None":
            return self.motion
        return "Zoom in" if self.zoom else "None"

    def trans_len(self):
        try:
            v = float(self.transition_seconds)
        except (TypeError, ValueError):
            v = TRANSITION_SECONDS
        return max(TRANSITION_MIN, min(TRANSITION_MAX, v))

    @classmethod
    def from_dict(cls, d):
        c = cls()
        c.__dict__.update(d)
        if isinstance(c.crop, list):
            c.crop = tuple(c.crop)
        if "transition_seconds" not in d:      # older projects
            c.transition_seconds = 0.6
        c.volume = max(0.0, min(1.0, float(c.volume)))
        if c.transition not in TRANSITIONS:
            c.transition = "Crossfade"
        return c

    def describe(self):
        bits = [f"{self.duration:.1f}s"]
        if self.kind == "video" and (self.in_point > 0 or (
                self.source_duration and
                self.out_point < self.source_duration - 0.05)):
            bits.append("trimmed")
        if self.speed != 1.0:
            bits.append(f"x{self.speed:g}")
        if self.muted:
            bits.append("muted")
        if self.color != "Normal":
            bits.append(self.color)
        if self.transition != "Cut":
            bits.append(self.transition)
        if self.motion_name != "None":
            bits.append(self.motion_name)
        if self.effect != "None":
            bits.append(self.effect.split(" (")[0])
        return " · ".join(bits)


class TextItem:
    def __init__(self, text="", style=TEXT_STYLES[0], start=0.0,
                 duration=4.0):
        self.id = _new_id()
        self.text = text
        self.style = style
        self.start = float(start)
        self.duration = float(duration)
        self.size = "Large" if style.startswith("Title") else "Medium"
        self.color = "White"
        self.outline = True
        self.box = False

    @property
    def end(self):
        return self.start + self.duration

    def to_dict(self):
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d):
        t = cls()
        t.__dict__.update(d)
        return t


class AudioItem:
    def __init__(self, path=None, kind="music", start=0.0, duration=None):
        self.id = _new_id()
        self.path = path
        self.kind = kind                  # music / voice / sfx
        self.name = os.path.basename(path) if path else kind
        self.start = float(start)
        self.duration = duration          # source length, seconds
        self.volume = 1.0
        self.loop = kind == "music"
        self.fade_in = 0.0
        self.fade_out = 2.0 if kind == "music" else 0.0
        self.trim_start = 0.0

    def to_dict(self):
        return dict(self.__dict__)

    @property
    def mix_group(self):
        """Which Audio Mix slider controls this sound."""
        return "music" if self.kind == "music" else "voice"

    @classmethod
    def from_dict(cls, d):
        a = cls()
        a.__dict__.update(d)
        a.volume = max(0.0, min(1.0, float(a.volume)))
        return a


class Project:
    def __init__(self):
        self.clips = []
        self.texts = []
        self.audios = []
        self.shape = ff.SHAPE_HORIZONTAL
        self.custom_size = None
        self.fit_mode = ff.FIT_MODES[0]
        self.quality = "High Quality"
        self.keep_clip_sound = True
        self.fade_whole = True
        # keep the video going (last picture stays on screen) until the
        # music has finished, so a song is never cut off part way
        self.play_whole_song = True
        # Audio Mix (0.0 - 1.0): sound in the video clips, music, voice
        self.mix_video = 1.0
        self.mix_music = 1.0
        self.mix_voice = 1.0
        self.upscale_4k = False
        self.fps = 30
        self.path = None
        self.dirty = False
        self._undo = []
        self._redo = []

    # ---------------- undo / redo ----------------
    def _snapshot(self):
        return {"clips": [c.to_dict() for c in self.clips],
                "texts": [t.to_dict() for t in self.texts],
                "audios": [a.to_dict() for a in self.audios],
                "shape": self.shape, "custom_size": self.custom_size,
                "fit_mode": self.fit_mode, "quality": self.quality,
                "keep_clip_sound": self.keep_clip_sound,
                "fade_whole": self.fade_whole, "fps": self.fps,
                "play_whole_song": self.play_whole_song,
                "mix_video": self.mix_video, "mix_music": self.mix_music,
                "mix_voice": self.mix_voice, "upscale_4k": self.upscale_4k}

    def _restore(self, s):
        self.clips = [Clip.from_dict(d) for d in s.get("clips", [])]
        self.texts = [TextItem.from_dict(d) for d in s.get("texts", [])]
        self.audios = [AudioItem.from_dict(d) for d in s.get("audios", [])]
        self.shape = s.get("shape", self.shape)
        cs = s.get("custom_size")
        self.custom_size = tuple(cs) if cs else None
        self.fit_mode = ff.OLD_FIT_NAMES.get(s.get("fit_mode"),
                                             s.get("fit_mode", self.fit_mode))
        if self.fit_mode not in ff.FIT_MODES:
            self.fit_mode = ff.FIT_MODES[0]
        self.quality = s.get("quality", self.quality)
        self.keep_clip_sound = s.get("keep_clip_sound", True)
        self.fade_whole = s.get("fade_whole", True)
        self.play_whole_song = bool(s.get("play_whole_song", True))
        self.fps = s.get("fps", 30)

        def lvl(k):
            try:
                return max(0.0, min(1.0, float(s.get(k, 1.0))))
            except (TypeError, ValueError):
                return 1.0
        self.mix_video, self.mix_music, self.mix_voice = (
            lvl("mix_video"), lvl("mix_music"), lvl("mix_voice"))
        self.upscale_4k = bool(s.get("upscale_4k", False))

    def push_undo(self):
        self._undo.append(copy.deepcopy(self._snapshot()))
        if len(self._undo) > 80:
            self._undo.pop(0)
        self._redo.clear()
        self.dirty = True

    def undo(self):
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        self.dirty = True
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        self.dirty = True
        return True

    # ---------------- queries ----------------
    def target_size(self):
        if self.custom_size:
            return tuple(self.custom_size)
        return ff.SHAPES.get(self.shape, (1920, 1080))

    def is_vertical(self):
        w, h = self.target_size()
        return h > w

    def clip_start(self, index):
        """When clip #index begins in the finished video (transitions
        overlap, so later clips start a little earlier)."""
        t = 0.0
        for i, c in enumerate(self.clips):
            if i == index:
                return t
            t += c.duration
            nxt = self.clips[i + 1] if i + 1 < len(self.clips) else None
            if nxt:
                t -= self.overlap(c, nxt)
        return t

    @staticmethod
    def overlap(prev, nxt):
        """Seconds two clips overlap because of the transition into nxt."""
        if nxt.transition == "Cut" or nxt.transition not in XFADE_NAMES:
            return 0.0
        return min(nxt.trans_len(), prev.duration / 2, nxt.duration / 2)

    def clips_duration(self):
        """How long the clips on the storyboard last, one after another."""
        if not self.clips:
            return 0.0
        last = len(self.clips) - 1
        return self.clip_start(last) + self.clips[last].duration

    def hold_seconds(self):
        """Extra seconds the last picture stays on screen so the music can
        play to the end (0 when the clips are already long enough)."""
        if not self.clips or not self.play_whole_song:
            return 0.0
        end = self.music_length(include_repeats=False)
        if not end:
            return 0.0
        extra = end - self.clips_duration()
        return extra if extra > 0.05 else 0.0

    def total_duration(self):
        """Length of the finished video."""
        return self.clips_duration() + self.hold_seconds()

    def clip_at(self, t):
        """(index, clip, seconds into clip) at project time t."""
        for i, c in enumerate(self.clips):
            s = self.clip_start(i)
            if s <= t < s + c.duration or i == len(self.clips) - 1:
                return i, c, max(0.0, min(t - s, c.duration))
        return None, None, 0.0

    def find_clip(self, clip_id):
        for i, c in enumerate(self.clips):
            if c.id == clip_id:
                return i, c
        return None, None

    # ---------------- edits ----------------
    def add_clip(self, path, index=None):
        """Add a video or photo. Returns the Clip."""
        ext = os.path.splitext(path)[1].lower()
        if ext in ff.IMAGE_EXTS:
            clip = Clip(path, "photo")
            clip.has_audio = False
        else:
            info = ff.probe_info(path)
            dur = info.get("duration") or 5.0
            clip = Clip(path, "video", source_duration=dur)
            clip.has_audio = bool(info.get("has_audio"))
            clip.src_w, clip.src_h = info.get("width"), info.get("height")
        self.push_undo()
        if index is None or index >= len(self.clips):
            self.clips.append(clip)
        else:
            self.clips.insert(index, clip)
        return clip

    def remove_clip(self, clip_id):
        i, c = self.find_clip(clip_id)
        if c is None:
            return False
        self.push_undo()
        del self.clips[i]
        return True

    def move_clip(self, clip_id, new_index):
        i, c = self.find_clip(clip_id)
        if c is None:
            return False
        new_index = max(0, min(new_index, len(self.clips) - 1))
        if new_index == i:
            return False
        self.push_undo()
        self.clips.pop(i)
        self.clips.insert(new_index, c)
        return True

    def duplicate_clip(self, clip_id):
        i, c = self.find_clip(clip_id)
        if c is None:
            return None
        self.push_undo()
        d = Clip.from_dict(copy.deepcopy(c.to_dict()))
        d.id = _new_id()
        self.clips.insert(i + 1, d)
        return d

    def set_trim(self, clip_id, in_point, out_point):
        i, c = self.find_clip(clip_id)
        if c is None:
            return False
        self.push_undo()
        if c.kind == "video":
            total = c.source_duration or c.out_point
            in_point = max(0.0, min(in_point, total - 0.2))
            out_point = max(in_point + 0.2, min(out_point, total))
        else:
            in_point = 0.0
            out_point = max(0.5, out_point)
        c.in_point, c.out_point = in_point, out_point
        return True

    def split_clip(self, clip_id, at_seconds_into_clip):
        """Split at a point measured in finished-video seconds into the clip."""
        i, c = self.find_clip(clip_id)
        if c is None:
            return None
        src_t = c.in_point + at_seconds_into_clip * c.speed
        if not (c.in_point + 0.2 < src_t < c.out_point - 0.2):
            return None
        self.push_undo()
        right = Clip.from_dict(copy.deepcopy(c.to_dict()))
        right.id = _new_id()
        right.in_point = src_t
        right.transition = "Cut"
        right.fade_in = 0.0
        c.out_point = src_t
        c.fade_out = 0.0
        self.clips.insert(i + 1, right)
        return right

    def set_clip(self, clip_id, **fields):
        """Change one or more clip settings (with undo)."""
        i, c = self.find_clip(clip_id)
        if c is None:
            return False
        self.push_undo()
        for k, v in fields.items():
            setattr(c, k, v)
        return True

    def set_all_clips(self, **fields):
        if not self.clips:
            return False
        self.push_undo()
        for c in self.clips:
            for k, v in fields.items():
                setattr(c, k, v)
        return True

    def add_text(self, text, style, start, duration):
        self.push_undo()
        t = TextItem(text, style, start, duration)
        self.texts.append(t)
        return t

    def remove_text(self, text_id):
        self.push_undo()
        self.texts = [t for t in self.texts if t.id != text_id]

    def find_text(self, text_id):
        for t in self.texts:
            if t.id == text_id:
                return t
        return None

    def next_music_start(self):
        """Where a newly added song goes: right after the songs already
        there, so several songs play one after another (not on top of
        each other)."""
        return round(self.music_length() or 0.0, 2)

    def add_audio(self, path, kind, start=None):
        self.push_undo()
        dur = ff.probe_duration(path)
        if start is None:
            start = self.next_music_start() if kind == "music" else 0.0
        a = AudioItem(path, kind, start, dur)
        self.audios.append(a)
        songs = [x for x in self.audios if x.kind == "music"]
        if len(songs) > 1:
            # a playlist of songs: each plays once, in order (repeating one
            # song would play over the next song)
            for x in songs:
                x.loop = False
        return a

    def remove_audio(self, audio_id):
        self.push_undo()
        self.audios = [a for a in self.audios if a.id != audio_id]

    def find_audio(self, audio_id):
        for a in self.audios:
            if a.id == audio_id:
                return a
        return None

    def set_photo_time(self, seconds, clip_ids=None):
        """Set how long photos stay on screen (all photos, or some)."""
        seconds = max(PHOTO_MIN, min(PHOTO_MAX, float(seconds)))
        photos = [c for c in self.clips if c.is_photo and
                  (clip_ids is None or c.id in clip_ids)]
        if not photos:
            return 0
        self.push_undo()
        for c in photos:
            c.in_point, c.out_point, c.speed = 0.0, seconds, 1.0
        return len(photos)

    def music_length(self, include_repeats=True):
        """When the music ends (seconds into the video), or None.
        Uses the music track(s) as they are, without looping."""
        end = None
        for a in self.audios:
            if a.kind != "music" or not a.path or not a.duration:
                continue
            if not include_repeats and getattr(a, "auto_repeat", False):
                continue
            e = a.start + max(0.0, a.duration - a.trim_start)
            end = e if end is None else max(end, e)
        return end

    def fit_to_music(self):
        """Like Movie Maker's Fit to music, for any length (an hour or more):
          * photos stay on screen just long enough for the video to end
            with the music (from 1 second up to 4 hours each)
          * music longer than the clips: the last picture stays on screen
            until the music ends
          * clips longer than the music: the music repeats until the video
            ends
        Returns (ok, message)."""
        if not self.clips:
            return False, "Add some videos or photos first."
        if not [a for a in self.audios if a.kind == "music" and a.path and
                a.duration]:
            return False, ("Add a song first (Add music), then press Fit to "
                           "music.")
        self.push_undo()
        # start from the songs you added (drop repeats made by an earlier fit)
        self.audios = [a for a in self.audios
                       if not getattr(a, "auto_repeat", False)]
        songs = sorted([a for a in self.audios if a.kind == "music" and
                        a.path and a.duration], key=lambda a: a.start)
        for a in songs:
            a.loop = False
        self.play_whole_song = True
        target = self.music_length()
        photos = [c for c in self.clips if c.is_photo]
        notes = []
        if photos:
            def total_with(d):
                for c in photos:
                    c.in_point, c.out_point, c.speed = 0.0, d, 1.0
                return self.clips_duration()
            lo, hi = PHOTO_MIN, FIT_PHOTO_MAX
            if total_with(lo) >= target - 0.05:
                d = lo
            elif total_with(hi) <= target + 0.05:
                d = hi
            else:
                for _ in range(80):
                    mid = (lo + hi) / 2
                    if total_with(mid) < target:
                        lo = mid
                    else:
                        hi = mid
                d = (lo + hi) / 2
            d = round(d, 3)
            total_with(d)
            notes.append(f"Each photo now shows for {_say_time(d)}.")
        clips_len = self.clips_duration()
        if clips_len > target + 0.5:
            # the video is longer than the music: repeat the music
            if len(songs) == 1:
                songs[0].loop = True
            else:
                t = target
                k = 0
                while t < clips_len - 0.5 and k < 200:
                    src = songs[k % len(songs)]
                    c = AudioItem(src.path, "music", round(t, 3),
                                  src.duration)
                    for attr in ("volume", "fade_in", "fade_out",
                                 "trim_start"):
                        setattr(c, attr, getattr(src, attr))
                    c.name = src.name + "  (repeat)"
                    c.loop = False
                    c.auto_repeat = True
                    self.audios.append(c)
                    t += max(0.1, src.duration - src.trim_start)
                    k += 1
            notes.append(f"The video is longer than the music "
                         f"({_say_time(target)}), so the music repeats "
                         f"until the video ends.")
        elif clips_len < target - 0.5:
            notes.append(f"The last picture stays on screen until the "
                         f"music ends.")
        msg = (f"Fitted to the music. Your video is now "
               f"{_say_time(self.total_duration())} long.  " +
               "  ".join(notes) + "  (Ctrl+Z undoes it.)")
        return True, msg

    def _repeat_music(self, songs, target, clips_len):
        """Repeat the songs from `target` until the clips end."""
        if len(songs) == 1:
            songs[0].loop = True
            return
        t = target
        k = 0
        while t < clips_len - 0.5 and k < 200:
            src = songs[k % len(songs)]
            c = AudioItem(src.path, "music", round(t, 3), src.duration)
            for attr in ("volume", "fade_in", "fade_out", "trim_start"):
                setattr(c, attr, getattr(src, attr))
            c.name = src.name + "  (repeat)"
            c.loop = False
            c.auto_repeat = True
            self.audios.append(c)
            t += max(0.1, src.duration - src.trim_start)
            k += 1

    def fit_to_video(self):
        """Fit music to video - the opposite of Fit to music: the video
        keeps its own length and the music is fitted to it.
          * music longer than the video: the music fades out and stops
            when the video ends
          * music shorter than the video: the music repeats until the
            video ends
        Photos and videos are not changed. Returns (ok, message)."""
        if not self.clips:
            return False, "Add some videos or photos first."
        if not [a for a in self.audios if a.kind == "music" and a.path and
                a.duration]:
            return False, ("Add a song first (Add music), then press Fit "
                           "music to video.")
        self.push_undo()
        # start from the songs you added (drop repeats made by an earlier fit)
        self.audios = [a for a in self.audios
                       if not getattr(a, "auto_repeat", False)]
        songs = sorted([a for a in self.audios if a.kind == "music" and
                        a.path and a.duration], key=lambda a: a.start)
        for a in songs:
            a.loop = False
            if a.fade_out < 2.0:
                a.fade_out = 2.0          # a gentle ending, never a hard cut
        self.play_whole_song = False
        target = self.music_length()
        clips_len = self.clips_duration()
        if clips_len > target + 0.5:
            self._repeat_music(songs, target, clips_len)
            note = ("The music is shorter than the video, so it repeats "
                    "until the video ends.")
        elif clips_len < target - 0.5:
            note = ("The music is longer than the video, so it fades out "
                    "and stops when the video ends.")
        else:
            note = "The music and the video already end together."
        msg = (f"Fitted the music to the video. Your video is "
               f"{_say_time(self.total_duration())} long.  {note}  "
               f"(Ctrl+Z undoes it.)")
        return True, msg

    def set_shape(self, label, custom=None):
        self.push_undo()
        self.shape = label
        self.custom_size = tuple(custom) if custom else None

    # ---------------- save / open ----------------
    def save(self, path=None):
        path = path or self.path
        if not path:
            raise ValueError("no path")
        data = {"app": "EZ Video Maker", "version": 3}
        data.update(self._snapshot())
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        self.path = path
        self.dirty = False
        return path

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        p = cls()
        p._restore(data)
        p.path = path
        return p

    def missing_files(self):
        out = []
        for c in self.clips:
            if c.path and not os.path.isfile(c.path):
                out.append(c.name)
        for a in self.audios:
            if a.path and not os.path.isfile(a.path):
                out.append(a.name)
        return out
