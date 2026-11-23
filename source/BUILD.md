# Building EZ Video Maker

Source for the app (Python 3.12 + tkinter, Pillow, tkinterdnd2, bundled FFmpeg).

The setup folder layout is `app\` (this source plus `lib\` with Pillow and
tkinterdnd2), `python\` (embedded Python 3.12 with tkinter), `ffmpeg\`
(ffmpeg.exe, ffprobe.exe, engine.pack), `README.txt`, `LICENSES.txt` and
`wizard.bmp`. Copy `python\`, `ffmpeg\` and `app\lib\` from the previous setup,
put this source in `app\`, then run `makensis installer.nsi`.
Zip the setup with README.txt as `EZ-Video-Maker-Setup.zip` and attach it to a
GitHub release - installed copies update themselves from the latest release.
