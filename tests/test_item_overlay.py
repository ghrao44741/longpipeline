"""
Regression test for stitch_video_longform.py's item-number overlay (Phase 2,
BUILD_BRIEF.md §8b task #37). Covers build_item_overlay_windows() (pure logic,
no ffmpeg) and add_item_number_overlay()'s no-op path (windows == [], the case
every narrative-format project hits — must copy the file through untouched,
never shell out to ffmpeg).

Requires Python 3.11 (mutagen) — same interpreter as stitch_video_longform.py
itself. No network calls, no API keys required.

Run:  "C:\\Users\\Girir\\AppData\\Local\\Programs\\Python\\Python311\\python.exe" tests/test_item_overlay.py
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import stitch_video_longform as svl  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(name)


# ─────────────────────────────────────────────────────────────────────────────
print("\nbuild_item_overlay_windows: one window per item, spanning to the first scene after its own group")
scenes = [
    {"id": "SCENE-001", "video_start": 0.0, "visual_group_id": "group-01"},              # hook, untagged
    {"id": "SCENE-002", "video_start": 3.0, "visual_group_id": "item-10",
     "item_number": 10, "item_name": "Gasteria"},
    {"id": "SCENE-003", "video_start": 6.0, "visual_group_id": "item-10"},               # rest of item #10
    {"id": "SCENE-004", "video_start": 9.0, "visual_group_id": "item-09",
     "item_number": 9, "item_name": "Aeonium arboreum"},
    {"id": "SCENE-005", "video_start": 12.0, "visual_group_id": "item-09"},              # rest of item #9
]
windows = svl.build_item_overlay_windows(scenes, total_duration=15.0)
check("2 windows produced (one per tagged scene)", len(windows) == 2, windows)
check("item #10 window spans its own start to item #9's start",
      windows[0] == {"item_number": 10, "item_name": "Gasteria", "start": 3.0, "end": 9.0}, windows[0])
check("item #9 (last item, no outro) window spans to total_duration",
      windows[1] == {"item_number": 9, "item_name": "Aeonium arboreum", "start": 9.0, "end": 15.0}, windows[1])

print("\nbuild_item_overlay_windows: last item's window stops at an outro, not total_duration")
print("  (regression for Etiolation_S1, 2026-08-06: '#1 Echeveria elegans' stayed on screen")
print("   120+ seconds into the outro because the old logic only knew about total_duration)")
scenes_with_outro = [
    {"id": "SCENE-098", "video_start": 400.0, "visual_group_id": "item-01",
     "item_number": 1, "item_name": "Echeveria elegans"},
    {"id": "SCENE-099", "video_start": 405.0, "visual_group_id": "item-01"},
    {"id": "SCENE-104", "video_start": 430.0, "visual_group_id": "item-01"},   # item #1's real last scene
    {"id": "SCENE-105", "video_start": 434.0, "visual_group_id": "outro-group"},  # "here's the fix..."
    {"id": "SCENE-122", "video_start": 580.0, "visual_group_id": "outro-group"},  # video's real last scene
]
windows_outro = svl.build_item_overlay_windows(scenes_with_outro, total_duration=584.0)
check("item #1's window ends at the outro's start (434.0), not total_duration (584.0)",
      windows_outro[0]["end"] == 434.0, windows_outro[0])

print("\nbuild_item_overlay_windows: no tagged scenes -> [] (narrative no-op path)")
narrative_scenes = [{"id": "S1", "video_start": 0.0}, {"id": "S2", "video_start": 5.0}]
check("empty for narrative manifests", svl.build_item_overlay_windows(narrative_scenes, 10.0) == [])

print("\nbuild_item_overlay_windows: tagged scene missing video_start is skipped, not crashed on")
missing_start_scenes = [{"id": "S1", "item_number": 1, "item_name": "Foo", "visual_group_id": "item-01"}]
check("skipped silently (write_video_timeline() may have skipped this scene too)",
      svl.build_item_overlay_windows(missing_start_scenes, 5.0) == [])


# ─────────────────────────────────────────────────────────────────────────────
print("\nadd_item_number_overlay: empty windows -> file copied through, no ffmpeg invoked")
with tempfile.TemporaryDirectory() as tmp:
    src = os.path.join(tmp, "in.mp4")
    dst = os.path.join(tmp, "out.mp4")
    payload = b"not a real mp4, just bytes to prove pass-through"
    with open(src, "wb") as f:
        f.write(payload)
    svl.add_item_number_overlay(src, dst, windows=[])
    check("output file created", os.path.exists(dst))
    with open(dst, "rb") as f:
        check("output bytes match input exactly (pure copy, no ffmpeg ran)", f.read() == payload)


print("\n" + ("=" * 58))
print(f"FAILED ({len(failures)}): {failures}" if failures else "ALL PASS")
sys.exit(1 if failures else 0)
