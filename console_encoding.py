"""
console_encoding.py — AeoniumGlow Long-form Pipeline

Shared UTF-8 stdout/stderr guard. Windows' cp1252 default console encoding can't encode
this project's emoji status glyphs (checkmarks, warning signs, X marks) that every
pipeline script prints — without this guard, the FIRST emoji print raises
UnicodeEncodeError and kills the process, often destroying the actual error message it was
trying to show (see upload_youtube.py's missing-googleapiclient handler, 2026-08-08).

This bit four separate scripts before becoming a shared helper instead of a fifth
copy-paste (run_pipeline.py, verify_output.py, make_contact_sheet.py, upload_youtube.py
each carried their own inline copy first). The gap that finally forced this: even with the
guard, `errors="replace"` on an interactive console silently substitutes '?' for
unencodable characters and looks fine — but reconfigure() only ever ran on scripts someone
had already hit the crash on. Five more files (stitch_video_longform.py,
generate_images.py, generate_script.py, stamp_items.py, config_loader.py) had no guard at
all and only surfaced when tests ran with stdout redirected (a pipe, a file, any CI
runner) instead of an interactive console — redirected stdout defaults to the system's
non-UTF-8 codepage even where an interactive terminal happens to tolerate it. Call this at
the top of any script (or test) that prints emoji, before any such print runs.
"""

import sys


def ensure_utf8_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
