# EZ Video Maker 3.7

Make it. Convert it. Share it. Easy.

The easiest video maker and converter for regular people. Orange & blue,
big friendly buttons, no confusing tech talk. Works 100% offline - your
files never leave your computer.

## New in 3.7

- New green button: WhatsApp audio -> MP3 / WAV. Pick WhatsApp voice
  notes or audio (.opus, .ogg, .m4a, .aac, .amr ...), choose MP3, WAV or
  both, and they are converted in seconds. They can go straight into your
  video as music or as a voice track, or just be saved. Find it on the
  Music tab and in the top bar. Files are saved in
  Music\EZ Video Maker Output\WhatsApp.

## New in 3.6

- New button: Fit music to video. Your video keeps its own length and the
  music is fitted to it - a song that is longer than the video fades out
  gently and stops when the video ends (a short song repeats until the
  video ends). It sits next to Fit to music in the top bar, on the Music
  tab and on the Edit tab. Ctrl+Z undoes it.
- A fresh, modern look: rounded brushed-silver buttons, glossy colour
  buttons for the important actions, a colourful accent line and a
  cleaner dark header.
- A little music equalizer next to the play button dances while music or
  a video is playing.
- The Save My Video button and the play / pause bar always stay visible,
  even on smaller laptop screens.

## New in 3.5

- New Movie-Maker-style look: all the everyday buttons (Add videos, Add
  photos, Add music, Record voice, Title, Caption, Credits, Fit to music,
  Play, Save My Video) are big picture buttons in one bar along the top.
- The music timeline sits right above the storyboard; bigger clip pictures.
- Fit to music works for any length - an hour-long mix or longer: photos
  can stretch up to 4 hours each, the last picture holds until the music
  ends, and if your videos are longer than the music, the music repeats
  until the video ends.
- Times over an hour show as h:mm:ss.

## New in 3.4

- Add several songs and they play one after another (before, every song
  started at the beginning and they played on top of each other).
- The music always plays to the end: if the songs are longer than your
  clips, the last picture stays on screen until the last song finishes.
  (Music tab > untick "Play the music all the way to the end" to cut the
  music when the clips end, like before.)
- Fit to music now also works with videos only.
- A music timeline under the storyboard shows the video and the songs
  side by side, so you can see at a glance if the music fits.
- A cleaner, softer look.


## Installing (Windows 10 / 11, 64-bit)

1. Double-click **EZ-Video-Maker-Setup.exe**
2. If Windows shows a blue "Windows protected your PC" box, click
   **More info** and then **Run anyway** (the installer is new and not
   yet known to Microsoft - this is normal for small independent apps).
3. Click Next, Install, Finish. That's it.

Everything is inside the installer: the program, the video engine
(FFmpeg) and its own copy of Python. Nothing else to download, nothing
else to install. No admin password needed - it installs into your own
user folder.

Start it from the Desktop shortcut or the Start Menu.
To remove it: Settings > Apps > EZ Video Maker > Uninstall.

## What it does

**Updates itself** - every time you open it, EZ Video Maker quietly checks
for a newer version. When one is ready you see an orange bar: click
"Restart & update now", or just keep working and it installs by itself
when you close the program. Click "Version ... Updates" (top right of the
home screen) to see which version you have or to check right away.

**Make a Video** - a Movie-Maker-style storyboard:
- Pick the shape first: **TikTok / Reels / Shorts (vertical 9:16)**,
  **YouTube / DistroKid (horizontal 16:9)**, Square, **Instagram / FB
  post (4:5)**, 4:3, 720p, 4K or custom. Clips fill the screen by
  default - no black bars (or pick blurred sides, or the whole picture).
- Add videos and photos, drag them into order, click any clip to see it.
- Clip tools: trim, split, **photo time (1 second to 5 minutes)**,
  rotate, flip, crop, speed, clip sound (0-100%), mute, duplicate,
  **Fit to music**.
- **Animations tab** (like Movie Maker): 38 transitions in 5 groups -
  Fades (crossfade, fade through black...), Cinematic (cinematic blur,
  soft slides, zoom...), Slides, Wipes, Shapes - each with its own
  length (1/4 second to 3 seconds) and a Preview button. **Pan and
  zoom**: zoom in/out, pan left/right/up/down, Cinematic drift, Ken
  Burns. Fade in from black / fade out to black.
- **Look**: 8 color styles + cinematic effects (cinema bars, film look,
  old movie, dark edges, sharpen).
- **Sound**: music, record your voice (big red button, 3-2-1 countdown,
  pause and resume), voice files, sound effects. **Audio mix**: Video
  sound, Music, and Voice sliders from 0 to 100% - everything starts at
  100%.
- **Fit to music**: makes your photos last just long enough for the
  video to end with the song.
- Words: title, caption, scrolling credits, top banner.
- Safe-area guide for TikTok, a quick check before saving (black bars,
  no sound, blurry clips), Upscale to 4K, undo/redo, save projects.

**Convert Video** - FLV, AVI, MOV, WMV, MKV, WEBM, MPG, 3GP, TS, VOB...
into MP4 (and MOV, MKV, AVI, WEBM, WMV, MPG, M4V, 3GP, TS, FLV, GIF).
Pull the sound out of a video as MP3/WAV. **Change the shape**: turn a
horizontal video into a TikTok vertical (or a vertical into a horizontal
for YouTube / DistroKid) with a blurred background. Many files at once.

**Convert Audio** - MP3, WAV, M4A, AAC, FLAC, OGG, WMA, AIFF, OPUS in any
direction. Many files at once.

Originals are never changed or deleted. Progress bar, time estimate,
cancel button, and a clear success message on every job.

## For the technically curious

- `app/` - the program (Python + Tkinter), `app/ez_video_maker/`
- `python/` - a private copy of Python 3.12 (python-build-standalone)
- `ffmpeg/` - a slim static FFmpeg 6.1 built for this app (GPL; x264, LAME,
  libvpx, libvorbis, FreeType). `installer/build_ffmpeg.sh` rebuilds it.
- Projects are plain JSON (`.ezvm`); a crash log, if ever needed, is in
  `%LOCALAPPDATA%\EZVideoMaker\crash.log`
- To rebuild the installer from source on Linux: `installer/build.sh`
  (needs NSIS `makensis`). Tests: `tests/test_pipeline.py` (headless)
  and `tests/test_gui.py` (needs a display / xvfb).
