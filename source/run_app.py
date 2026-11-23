"""Starts EZ Video Maker.  (The installer's shortcut runs this file with
the bundled Python - nothing else needs to be installed.)"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "lib")
if os.path.isdir(LIB) and LIB not in sys.path:
    sys.path.insert(0, LIB)
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _log_crash(exc_text):
    try:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "EZVideoMaker")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "crash.log"), "a", encoding="utf-8") as fh:
            fh.write(exc_text + "\n" + "-" * 60 + "\n")
    except Exception:
        pass


def main():
    try:
        from ez_video_maker.app import main as app_main
        app_main()
    except Exception:
        text = traceback.format_exc()
        _log_crash(text)
        try:
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror(
                "EZ Video Maker - problem",
                "Sorry, something went wrong:\n\n" + text[-900:])
        except Exception:
            print(text, file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
