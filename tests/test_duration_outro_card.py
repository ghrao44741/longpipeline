"""
Regression test for verify_output.py's duration-vs-manifest check accounting for
the outro card (Phase 3 follow-up, 2026-08-08). Without this, the first real
re-stitch with cta.outro_card.enabled would fail a check that isn't detecting a
bug -- it's measuring the wrong expected total.

Uses a synthetic project dir + real ffprobe-able audio files (short silent WAVs)
so check_duration_vs_manifest()'s real ffprobe calls have something to measure.
No network calls, no API keys, no real video render.

Run (Python 3.11, mutagen via stitch_video_longform's import chain):
    "C:\\Users\\Girir\\AppData\\Local\\Programs\\Python\\Python311\\python.exe" tests/test_duration_outro_card.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verify_output import check_duration_vs_manifest  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(name)


def make_silent_wav(path: str, seconds: float):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
         "-t", str(seconds), path],
        capture_output=True, text=True,
    )


scripts_dir = os.path.abspath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

with tempfile.TemporaryDirectory() as project_dir:
    # Two 2s scenes -> expected (audio+CLIP_EXTRA) sum = (2.0+0.5)*2 = 5.0s
    scene_ids = ["SCENE-001", "SCENE-002"]
    scenes = []
    for sid in scene_ids:
        aud_rel = os.path.join("audio", f"{sid}.wav")
        aud_abs = os.path.join(project_dir, aud_rel)
        os.makedirs(os.path.dirname(aud_abs), exist_ok=True)
        make_silent_wav(aud_abs, 2.0)
        scenes.append({"id": sid, "audio": aud_rel})
    with open(os.path.join(project_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"episode": "Test", "scenes": scenes}, f)

    print("\ncheck_duration_vs_manifest: outro card DISABLED -- unchanged behavior (regression guard)")
    with tempfile.TemporaryDirectory() as vdir:
        video_path = os.path.join(vdir, "video.mp4")
        make_silent_wav(video_path.replace(".mp4", ".wav"), 5.0)
        subprocess.run(["ffmpeg", "-y", "-i", video_path.replace(".mp4", ".wav"),
                         "-c:a", "aac", video_path], capture_output=True, text=True)
        config_disabled = {"cta": {"outro_card": {"enabled": False}}}
        result = check_duration_vs_manifest(project_dir, video_path, config_disabled, scripts_dir)
        check("passes with no outro card, video matches scene sum",
              result["passed"], result["detail"])
        check("expected does not mention an outro card", "outro card" not in result["detail"],
              result["detail"])

    print("\ncheck_duration_vs_manifest: outro card ENABLED and resolves -- expected includes its seconds")
    with tempfile.TemporaryDirectory() as dna_root:
        dna_dir = os.path.join(dna_root, "channel_dna")
        assets_dir = os.path.join(dna_dir, "test_channel")
        os.makedirs(assets_dir)
        with open(os.path.join(dna_dir, "test_channel.json"), "w", encoding="utf-8") as f:
            f.write('{"channel_name": "Test"}')
        with open(os.path.join(assets_dir, "outro_card.png"), "wb") as f:
            f.write(b"placeholder")

        config_enabled = {
            "channel_dna_file": "channel_dna/test_channel.json",
            "cta": {"outro_card": {"enabled": True, "asset": "outro_card.png", "seconds": 3}},
        }
        with tempfile.TemporaryDirectory() as vdir:
            # Real video = scenes (5.0s) + outro card (3s) = 8.0s -- simulating what
            # stitch_video_longform.py actually produces once the card is appended.
            video_path = os.path.join(vdir, "video.mp4")
            wav_path = video_path.replace(".mp4", ".wav")
            make_silent_wav(wav_path, 8.0)
            subprocess.run(["ffmpeg", "-y", "-i", wav_path, "-c:a", "aac", video_path],
                            capture_output=True, text=True)

            result = check_duration_vs_manifest(project_dir, video_path, config_enabled, dna_root)
            check("passes when actual video includes the outro card's length",
                  result["passed"], result["detail"])
            check("expected detail mentions the outro card and its seconds",
                  "3s outro card" in result["detail"], result["detail"])

        print("\ncheck_duration_vs_manifest: outro card enabled but video does NOT include it -- correctly FAILS")
        with tempfile.TemporaryDirectory() as vdir:
            # Real video = scenes only (5.0s), as if the outro card were configured on but
            # never actually appended (e.g. a stale render) -- should now be caught, not
            # silently passed the way it would have been before this fix in the other
            # direction (missing from expected).
            video_path = os.path.join(vdir, "video.mp4")
            wav_path = video_path.replace(".mp4", ".wav")
            make_silent_wav(wav_path, 5.0)
            subprocess.run(["ffmpeg", "-y", "-i", wav_path, "-c:a", "aac", video_path],
                            capture_output=True, text=True)

            result = check_duration_vs_manifest(project_dir, video_path, config_enabled, dna_root)
            check("fails when the outro card is configured but missing from the actual video",
                  not result["passed"], result["detail"])


print("\n" + ("=" * 58))
print(f"FAILED ({len(failures)}): {failures}" if failures else "ALL PASS")
sys.exit(1 if failures else 0)
