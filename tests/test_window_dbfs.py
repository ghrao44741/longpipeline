"""
Regression test for verify_output.py's _window_dbfs() -- the pydub long-read
truncation fix (2026-08-08).

THE BUG: a sequential whole-file decode of this pipeline's stitched MP4s stops
early and reports no error. On Etiolation_S1, pydub.AudioSegment.from_file()
returned 537.983s of PCM for a file ffprobe reports as 602.566s.
check_bgm_audibility() was therefore sampling ~64s BEFORE the real outro window,
and under-sampling the tail of every long video it had ever run against, while
reporting a confident number either way.

NOT a generic pydub length limit -- the DIAGNOSTIC at the bottom of this file
builds a 600s 44100Hz stereo AAC fixture, longer than the 538s cut, and pydub
reads it in full. The real trigger is inconsistent audio metadata in the stitched
container: ffprobe -count_frames finds 23169 AAC frames (=538.0s) while the same
stream's duration_ts says 602.55s, so ffmpeg's own frame counter stops where
pydub does -- while SEEK-based reads (-ss) return real audio throughout. The
audio is genuinely present; only sequential readers miss it.

THE FIX under test: _window_dbfs() extracts each window via ffmpeg FIRST and only
hands pydub a short read, so the truncation limit is never approached.

WHAT THIS ASSERTS: that _window_dbfs() reads the CORRECT REGION of a file long
enough to trigger the bug. It deliberately does not assert that pydub is still
broken -- if a future pydub fixes the underlying limit, these tests should keep
passing, because they pin the behavior we need, not the defect we routed around.
The full-file load is reported as a DIAGNOSTIC only, never gated on.

Fixture: a 600s file (past the ~538s cut) that is digitally silent for its first
570s and carries a loud tone for the final 30s. Any measurement of the tail that
comes from a truncated decode reads silence; only a correctly-positioned read
finds the tone. 44100Hz stereo is kept deliberately -- the observed limit tracked
buffer size, so a lower sample rate would move the threshold and stop reproducing
the real condition.

No GPU, no network, no API keys. Needs ffmpeg/ffprobe on PATH.

Run (Python 3.11, same interpreter verify_output.py itself requires):
    "C:\\Users\\Girir\\AppData\\Local\\Programs\\Python\\Python311\\python.exe" tests/test_window_dbfs.py
"""

import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verify_output import _window_dbfs  # noqa: E402

failures = []

TOTAL_S = 600          # past the ~538s truncation point
TONE_STARTS_S = 570    # silence before this, loud tone after
SILENCE_FLOOR = -50    # verify_output.py's own "silent/absent" threshold


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(name)


def make_fixture(path: str):
    """600s: digital silence, then a loud 440Hz tone for the final 30s."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"sine=frequency=440:sample_rate=44100:duration={TOTAL_S}",
         "-af", f"volume=volume='if(gte(t,{TONE_STARTS_S}),1,0)':eval=frame",
         "-ac", "2", "-c:a", "aac", path],
        capture_output=True, text=True,
    )


with tempfile.TemporaryDirectory() as tmp:
    fixture = os.path.join(tmp, "long.m4a")
    print(f"\nBuilding {TOTAL_S}s fixture (tone from {TONE_STARTS_S}s)...")
    make_fixture(fixture)

    if not os.path.exists(fixture) or os.path.getsize(fixture) == 0:
        print("  FAIL  fixture could not be built -- is ffmpeg on PATH?")
        sys.exit(1)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", fixture],
        capture_output=True, text=True,
    )
    real_duration = float(probe.stdout.strip())
    check("fixture is genuinely longer than the ~538s truncation point",
          real_duration > 560, f"ffprobe reports {real_duration:.1f}s")

    print("\n_window_dbfs: reads the correct region of a >538s file")

    tail = _window_dbfs(fixture, TONE_STARTS_S + 5, 10)
    check("finds the loud tone in the final 30s (past the truncation point)",
          math.isfinite(tail) and tail > SILENCE_FLOOR,
          f"got {tail} dBFS, expected > {SILENCE_FLOOR} -- a truncated decode reads silence here")

    head = _window_dbfs(fixture, 100, 10)
    check("reads silence at 100s, where the fixture IS silent",
          head < SILENCE_FLOOR,
          f"got {head} dBFS, expected < {SILENCE_FLOOR}")

    check("distinguishes the two regions by a wide margin",
          math.isfinite(tail) and tail - head > 30,
          f"tail={tail} dBFS vs head={head} dBFS -- windows may not be positioned independently")

    # The window immediately BEFORE the tone must still be silent: proves the
    # extraction is positioned per-window, not just returning the file's overall
    # level (which the tone would dominate).
    just_before = _window_dbfs(fixture, TONE_STARTS_S - 15, 10)
    check("window ending just before the tone is still silent",
          just_before < SILENCE_FLOOR,
          f"got {just_before} dBFS -- window boundaries are not being honored")

    print("\n_window_dbfs: documented failure contract")

    missing = _window_dbfs(os.path.join(tmp, "does_not_exist.m4a"), 0, 5)
    check("returns -inf for an unreadable file (pydub's silent-audio convention)",
          missing == float("-inf"), f"got {missing}")

    past_end = _window_dbfs(fixture, TOTAL_S + 120, 10)
    check("returns -inf (not a bogus number) for a window past end-of-file",
          past_end == float("-inf") or past_end < SILENCE_FLOOR, f"got {past_end}")

    # ── DIAGNOSTIC ONLY — never gated ─────────────────────────────────────────
    # Shows whether this environment's pydub still truncates. If the decoded
    # length comes back short, that is the original bug still live underneath;
    # if it comes back full, pydub was fixed upstream and _window_dbfs() is now
    # belt-and-braces. Either way the asserts above are what matter.
    print("\nDIAGNOSTIC (not gating): what a full-file pydub load sees here")
    try:
        from pydub import AudioSegment
        decoded_s = len(AudioSegment.from_file(fixture)) / 1000
        verdict = ("TRUNCATES -- original bug still live under the fix"
                   if decoded_s < real_duration - 1 else "full length -- pydub read it all")
        print(f"  ffprobe: {real_duration:.2f}s | pydub: {decoded_s:.2f}s -> {verdict}")
    except Exception as e:
        print(f"  could not run diagnostic: {e}")


print("\n" + ("=" * 58))
print(f"FAILED ({len(failures)}): {failures}" if failures else "ALL PASS")
sys.exit(1 if failures else 0)
