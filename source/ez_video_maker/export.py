"""
EZ Video Maker - the render pipeline.
Turns a Project into a finished MP4 (or a quick draft for preview):
  1. every clip becomes a same-size, same-fps part (with its own trims,
     speed, rotate, crop, color, fades)
  2. parts are joined - straight cuts use a fast copy join, fancy
     transitions use FFmpeg's xfade
  3. finishing pass: words on screen, music, voiceover, sound effects,
     whole-video fades
Runs in a worker thread; reports progress and can be cancelled.
"""

import os
import shutil
import tempfile
import textwrap

from . import ffmpeg_engine as ff
from .model import COLOR_FILTERS, XFADE_NAMES, TEXT_COLORS


def motion_filter(motion, w, h, fps, dur):
    """Pan and zoom: a slow camera move over the picture (needs the picture
    to already be w x h).  The picture is enlarged first so the move is
    smooth instead of shaky."""
    if not motion or motion == "None":
        return None
    n = max(2, int(round(dur * fps)))
    p = f"min(on/{n - 1},1)"                 # 0 -> 1 over the clip
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    fx, fy = "(iw-iw/zoom)", "(ih-ih/zoom)"
    z, x, y = "1.15", cx, cy
    if motion == "Zoom in":
        z = f"1+0.22*{p}"
    elif motion == "Zoom out":
        z = f"1.22-0.22*{p}"
    elif motion == "Pan left":
        x = f"{fx}*(1-{p})"
    elif motion == "Pan right":
        x = f"{fx}*{p}"
    elif motion == "Pan up":
        y = f"{fy}*(1-{p})"
    elif motion == "Pan down":
        y = f"{fy}*{p}"
    elif motion == "Cinematic drift":
        z = f"1.06+0.12*{p}"
        x = f"{fx}*(0.25+0.5*{p})"
        y = f"{fy}*(0.6-0.2*{p})"
    elif motion == "Ken Burns":
        z = f"1+0.28*{p}"
        x = f"{fx}*(0.15+0.7*{p})"
        y = f"{fy}*(0.3+0.4*{p})"
    else:
        return None
    big_w, big_h = w * 2, h * 2
    return (f"scale={big_w}:{big_h}:flags=bicubic,"
            f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={w}x{h}:fps={fps}")


def effect_filter(effect, w, h):
    """The cinematic visual effects."""
    if not effect or effect == "None":
        return None
    if effect.startswith("Cinema bars"):
        if w >= h:   # letterbox to a 2.39:1 movie shape
            bar = max(2, int(round((h - w / 2.39) / 2)))
        else:
            bar = max(2, int(h * 0.09))
        return (f"drawbox=x=0:y=0:w=iw:h={bar}:color=black:t=fill,"
                f"drawbox=x=0:y=ih-{bar}:w=iw:h={bar}:color=black:t=fill")
    if effect == "Film look":
        return ("curves=preset=medium_contrast,"
                "colorchannelmixer=rr=1.05:gg=1.0:bb=0.92,"
                "vignette=angle=PI/5")
    if effect == "Old movie":
        return ("colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:"
                ".272:.534:.131,vignette=angle=PI/4,noise=c0s=4:allf=t")
    if effect.startswith("Dark edges"):
        return "vignette=angle=PI/4.5"
    if effect == "Sharpen":
        return "unsharp=5:5:0.9:5:5:0.0"
    return None


class ExportCancelled(Exception):
    pass


def _fpath(p):
    """Escape a file path for use inside an FFmpeg filter string."""
    p = p.replace("\\", "/")
    p = p.replace("'", r"\'").replace(":", r"\:")
    return f"'{p}'"


def _atempo_chain(speed):
    """atempo only accepts 0.5-100 per stage: chain stages for slow-mo."""
    parts = []
    s = float(speed)
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    while s > 100:
        parts.append("atempo=100")
        s /= 100
    parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


def _crop_filter(crop):
    l, t, r, b = [max(0.0, min(45.0, float(v))) / 100.0 for v in crop]
    return (f"crop=iw*{1 - l - r:.4f}:ih*{1 - t - b:.4f}:"
            f"iw*{l:.4f}:ih*{t:.4f}")


class Exporter:
    def __init__(self, project, out_path, proxy=False):
        self.project = project
        self.out_path = out_path
        self.proxy = proxy
        self.cancelled = False
        self.active_job = None
        self.tmpdir = None
        self.progress = None

    def cancel(self):
        self.cancelled = True
        job = self.active_job
        if job:
            job.cancel()

    # ---------------------------------------------------------------
    def _check(self):
        if self.cancelled:
            raise ExportCancelled()

    def _report(self, pct, label):
        if self.progress:
            self.progress(max(0.0, min(100.0, pct)), label)

    def _step(self, args, duration, label, base, weight):
        self._check()

        def on_prog(pct, secs, eta):
            self._report(base + pct * weight / 100.0, label)

        self._report(base, label)
        ok, msg = ff.run_ffmpeg(args, duration=duration, on_progress=on_prog,
                                cancel_flag=self)
        if self.cancelled:
            raise ExportCancelled()
        if not ok:
            raise RuntimeError(msg)

    def _size(self):
        w, h = self.project.target_size()
        if self.project.upscale_4k and not self.proxy:
            f = 3840.0 / max(w, h)
            if f > 1:
                w, h = int(round(w * f)), int(round(h * f))
        if self.proxy:
            longest = max(w, h)
            scale = min(1.0, 640.0 / longest)
            w, h = int(w * scale), int(h * scale)
        return w - w % 2, h - h % 2

    def _enc(self):
        q = ff.QUALITY_PRESETS.get(self.project.quality,
                                   ff.QUALITY_PRESETS["High Quality"])
        if self.proxy:
            return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                    "-ar", "44100", "-ac", "2"]
        return ["-c:v", "libx264", "-preset", q["preset"], "-crf", q["crf"],
                "-pix_fmt", "yuv420p", "-profile:v", "high",
                "-c:a", "aac", "-b:a", q["abr"], "-ar", "44100", "-ac", "2"]

    # ---------------------------------------------------------------
    def run(self, progress=None):
        self.progress = progress
        p = self.project
        if not p.clips:
            raise RuntimeError("Add at least one video or photo first.")
        self.tmpdir = tempfile.mkdtemp(prefix="ezvm_")
        try:
            parts = self._render_parts()
            joined = self._join(parts)
            self._finish(joined)
            self._report(100, "Done!")
            return self.out_path
        finally:
            shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ---------------- 1. parts ----------------
    def _render_parts(self):
        p = self.project
        w, h = self._size()
        fps = p.fps
        n = len(p.clips)
        weight = 60.0 / n
        parts = []
        for i, c in enumerate(p.clips):
            self._check()
            out = os.path.join(self.tmpdir, f"part{i:03d}.mp4")
            dur = c.duration
            args = []
            # ---- inputs ----
            if c.is_photo:
                args += ["-loop", "1", "-framerate", str(fps),
                         "-t", f"{dur:.3f}", "-i", c.path]
            else:
                # (no -ss at 0: some FLV/AVI files seek badly to time 0)
                if c.in_point >= 0.05:
                    args += ["-ss", f"{c.in_point:.3f}"]
                args += ["-t", f"{(c.out_point - c.in_point):.3f}",
                         "-i", c.path]
            clip_gain = c.volume * p.mix_video
            use_src_audio = (not c.is_photo and c.has_audio and not c.muted
                             and p.keep_clip_sound and clip_gain > 0)
            args += ["-f", "lavfi", "-t", f"{dur:.3f}",
                     "-i", "anullsrc=r=44100:cl=stereo"]
            # ---- video filter chain ----
            vf = []
            if c.rotate == 90:
                vf.append("transpose=1")
            elif c.rotate == 180:
                vf.append("hflip,vflip")
            elif c.rotate == 270:
                vf.append("transpose=2")
            if c.flip_h:
                vf.append("hflip")
            if c.flip_v:
                vf.append("vflip")
            if c.crop and any(c.crop):
                vf.append(_crop_filter(c.crop))
            if not c.is_photo and c.speed != 1.0:
                vf.append(f"setpts=PTS/{c.speed:.4f}")
            sharp = p.upscale_4k and not self.proxy
            vf.append(ff.fit_filter(w, h, p.fit_mode, sharp=sharp))
            mf = motion_filter(c.motion_name, w, h, fps, dur)
            if mf:
                vf.append(f"fps={fps}")
                vf.append(mf)
            cf = COLOR_FILTERS.get(c.color)
            if cf:
                vf.append(cf)
            ef = effect_filter(getattr(c, "effect", "None"), w, h)
            if ef:
                vf.append(ef)
            vf.append(f"fps={fps}")
            vf.append("format=yuv420p")
            if c.fade_in > 0:
                vf.append(f"fade=t=in:st=0:d={min(c.fade_in, dur / 2):.3f}")
            if c.fade_out > 0:
                fo = min(c.fade_out, dur / 2)
                vf.append(f"fade=t=out:st={dur - fo:.3f}:d={fo:.3f}")
            vchain = "[0:v]" + ",".join(vf) + "[v]"
            # ---- audio filter chain ----
            af = []
            if use_src_audio:
                src = "[0:a]"
                if c.speed != 1.0:
                    af.append(_atempo_chain(c.speed))
                if abs(clip_gain - 1.0) > 0.001:
                    af.append(f"volume={clip_gain:.3f}")
            else:
                src = "[1:a]"
            af.append("aresample=44100")
            af.append("aformat=sample_fmts=fltp:channel_layouts=stereo")
            if c.fade_in > 0 and use_src_audio:
                af.append(f"afade=t=in:st=0:d={min(c.fade_in, dur / 2):.3f}")
            if c.fade_out > 0 and use_src_audio:
                fo = min(c.fade_out, dur / 2)
                af.append(f"afade=t=out:st={dur - fo:.3f}:d={fo:.3f}")
            af.append("apad")
            achain = src + ",".join(af) + "[a]"
            args += ["-filter_complex", vchain + ";" + achain,
                     "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}",
                     "-r", str(fps), "-fps_mode", "cfr"] + self._enc() + \
                    ["-movflags", "+faststart", out]
            self._step(args, dur, f"Preparing clip {i + 1} of {n}: {c.name}",
                       i * weight, weight)
            parts.append((out, dur))
        return parts

    # ---------------- 2. join ----------------
    def _join(self, parts):
        p = self.project
        if len(parts) == 1:
            return parts[0][0]
        # split into groups separated by straight cuts
        groups, cur = [], [0]
        for i in range(1, len(parts)):
            if p.clips[i].transition == "Cut" or \
                    p.clips[i].transition not in XFADE_NAMES:
                groups.append(cur)
                cur = [i]
            else:
                cur.append(i)
        groups.append(cur)
        files = []
        n_x = sum(1 for g in groups if len(g) > 1)
        done_x = 0
        for g in groups:
            if len(g) == 1:
                files.append(parts[g[0]][0])
                continue
            out = os.path.join(self.tmpdir, f"group{g[0]:03d}.mp4")
            base = 60 + done_x * (12.0 / max(1, n_x))
            self._xfade_group(g, parts, out, base, 12.0 / max(1, n_x))
            done_x += 1
            files.append(out)
        if len(files) == 1:
            return files[0]
        joined = os.path.join(self.tmpdir, "joined.mp4")
        listfile = os.path.join(self.tmpdir, "list.txt")
        with open(listfile, "w", encoding="utf-8") as fh:
            for f in files:
                fh.write("file '" + f.replace("\\", "/").replace("'", r"'\''")
                         + "'\n")
        total = sum(d for _, d in parts)
        self._step(["-f", "concat", "-safe", "0", "-i", listfile,
                    "-c", "copy", "-movflags", "+faststart", joined],
                   total, "Joining your clips...", 72, 3)
        return joined

    def _xfade_group(self, idxs, parts, out, base, weight):
        p = self.project
        args = []
        for i in idxs:
            args += ["-i", parts[i][0]]
        fc = []
        vprev, aprev = "[0:v]", "[0:a]"
        offset = 0.0
        for k in range(1, len(idxs)):
            prev_dur = parts[idxs[k - 1]][1]
            this_dur = parts[idxs[k]][1]
            clip = p.clips[idxs[k]]
            td = min(clip.trans_len(), prev_dur / 2, this_dur / 2)
            name = XFADE_NAMES.get(clip.transition, "fade")
            offset += prev_dur - td
            last = k == len(idxs) - 1
            vout = "[vout]" if last else f"[v{k}]"
            aout = "[aout]" if last else f"[a{k}]"
            fc.append(f"{vprev}[{k}:v]xfade=transition={name}:"
                      f"duration={td:.3f}:offset={offset:.3f}{vout}")
            fc.append(f"{aprev}[{k}:a]acrossfade=d={td:.3f}:c1=tri:c2=tri"
                      f"{aout}")
            vprev, aprev = vout, aout
        total = offset + parts[idxs[-1]][1]
        args += ["-filter_complex", ";".join(fc), "-map", "[vout]",
                 "-map", "[aout]", "-r", str(p.fps), "-fps_mode", "cfr"] + \
            self._enc() + ["-movflags", "+faststart", out]
        self._step(args, total, "Blending transitions...", base, weight)

    # ---------------- 3. finish ----------------
    def _text_filters(self, w, h):
        p = self.project
        font = ff.font_file()
        filters = []
        if not font:
            return filters
        for k, t in enumerate(p.texts):
            if not t.text.strip():
                continue
            size = {"Small": 0.035, "Medium": 0.05, "Large": 0.07,
                    "Huge": 0.1}.get(t.size, 0.05)
            fs = max(12, int(h * size))
            # wrap long lines so they fit on screen
            max_chars = max(8, int(w / (fs * 0.55)))
            lines = []
            for ln in t.text.splitlines() or [""]:
                lines += textwrap.wrap(ln, max_chars) or [""]
            txt = "\n".join(lines)
            tf = os.path.join(self.tmpdir, f"text{k:02d}.txt")
            with open(tf, "w", encoding="utf-8") as fh:
                fh.write(txt)
            color = TEXT_COLORS.get(t.color, "white")
            margin = int(h * 0.06)
            if t.style.startswith("Title"):
                pos = "x=(w-text_w)/2:y=(h-text_h)/2"
            elif t.style.startswith("Top"):
                pos = f"x=(w-text_w)/2:y={margin}"
            elif t.style.startswith("Credits"):
                th = int(fs * 1.35 * len(lines))
                speed = (h + th) / max(0.5, t.duration)
                pos = (f"x=(w-text_w)/2:y=h-(t-{t.start:.3f})*{speed:.2f}")
            else:
                pos = f"x=(w-text_w)/2:y=h-text_h-{margin}"
            d = (f"drawtext=fontfile={_fpath(font)}:textfile={_fpath(tf)}:"
                 f"fontsize={fs}:fontcolor={color}:line_spacing={fs // 5}:"
                 f"{pos}:enable='between(t,{t.start:.3f},{t.end:.3f})'")
            if t.outline:
                d += f":borderw={max(1, fs // 14)}:bordercolor=black@0.75"
            if t.box:
                d += f":box=1:boxcolor=black@0.55:boxborderw={fs // 3}"
            filters.append(d)
        return filters

    def _finish(self, joined):
        p = self.project
        w, h = self._size()
        total = p.total_duration()
        hold = p.hold_seconds()
        vf = []
        if hold > 0:
            # music is longer than the clips: keep the last picture on
            # screen until the music has finished
            vf.append(f"tpad=stop_mode=clone:stop_duration={hold:.3f}")
        vf += self._text_filters(w, h)
        if p.fade_whole and total > 2.0:
            vf.append("fade=t=in:st=0:d=0.7")
            vf.append(f"fade=t=out:st={max(0.0, total - 0.7):.3f}:d=0.7")
        args = ["-i", joined]
        inputs = 1
        achains = []
        mix = []
        if p.keep_clip_sound:
            if hold > 0:
                achains.append("[0:a]apad[src]")
                mix.append("[src]")
            else:
                mix.append("[0:a]")
        for a in p.audios:
            if not a.path or not os.path.isfile(a.path):
                continue
            level = p.mix_music if a.mix_group == "music" else p.mix_voice
            if a.volume * level <= 0:
                continue
            if a.loop:
                args += ["-stream_loop", "-1"]
            args += ["-i", a.path]
            lbl = f"[m{inputs}]"
            chain = [f"[{inputs}:a]"]
            f = []
            if a.trim_start > 0:
                f.append(f"atrim=start={a.trim_start:.3f}")
                f.append("asetpts=PTS-STARTPTS")
            f.append("aresample=44100")
            f.append("aformat=sample_fmts=fltp:channel_layouts=stereo")
            avail = max(0.1, total - a.start)
            f.append(f"atrim=0:{avail:.3f}")
            if a.fade_in > 0:
                f.append(f"afade=t=in:st=0:d={a.fade_in:.3f}")
            if a.fade_out > 0:
                src_len = avail
                if not a.loop and a.duration:
                    src_len = min(avail, max(0.1, a.duration - a.trim_start))
                fo = min(a.fade_out, src_len / 2)
                f.append(f"afade=t=out:st={max(0, src_len - fo):.3f}:"
                         f"d={fo:.3f}")
            level = p.mix_music if a.mix_group == "music" else p.mix_voice
            f.append(f"volume={a.volume * level:.3f}")
            if a.start > 0:
                ms = int(a.start * 1000)
                f.append(f"adelay={ms}|{ms}")
            f.append("apad")
            chain.append(",".join(f))
            achains.append("".join(chain) + lbl)
            mix.append(lbl)
            inputs += 1
        need_audio_work = (bool(achains) or not p.keep_clip_sound or
                           hold > 0 or (p.fade_whole and total > 2.0))
        fc = []
        if need_audio_work:
            fc += achains
            if len(mix) > 1:
                fc.append("".join(mix) + f"amix=inputs={len(mix)}:"
                          f"duration=first:dropout_transition=0:"
                          f"normalize=0[mixed]")
                alast = "[mixed]"
            elif len(mix) == 1:
                fc.append(f"{mix[0]}anull[mixed]")
                alast = "[mixed]"
            else:
                args += ["-f", "lavfi", "-t", f"{total:.3f}",
                         "-i", "anullsrc=r=44100:cl=stereo"]
                fc.append(f"[{inputs}:a]anull[mixed]")
                alast = "[mixed]"
            if p.fade_whole and total > 2.0:
                fc.append(f"{alast}afade=t=in:st=0:d=0.7,"
                          f"afade=t=out:st={max(0.0, total - 0.7):.3f}:d=0.7"
                          f"[aout]")
            else:
                fc.append(f"{alast}anull[aout]")
        if vf:
            fc.append("[0:v]" + ",".join(vf) + "[vout]")
        out_args = []
        if fc:
            args += ["-filter_complex", ";".join(fc)]
            args += ["-map", "[vout]" if vf else "0:v"]
            args += ["-map", "[aout]" if need_audio_work else "0:a"]
        else:
            args += ["-map", "0:v", "-map", "0:a"]
        enc = self._enc()
        if vf:
            out_args += enc
        else:
            out_args += ["-c:v", "copy"] + enc[enc.index("-c:a"):] \
                if need_audio_work else ["-c", "copy"]
        args += out_args + ["-t", f"{total:.3f}", "-movflags", "+faststart",
                            self.out_path]
        self._step(args, total, "Adding finishing touches...", 75, 25)
