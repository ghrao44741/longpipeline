"""
run_pipeline.py — AeoniumGlow Long-form (16:9) Pipeline
Master orchestrator. Runs all steps from script to YouTube upload, single linear run
(no yt/ig variant fork — long-form has no equivalent to that split).

Steps:
  1. script      → generate_script.py            (LLM polish, in this folder)
  [GATE]         → You review + approve the script
  2. voiceover   → edge-tts                       (TTS audio)
  3. scenes      → shorts_pipeline2/auto_split_scenes.py  (WhisperX — edited in place there,
                    not copied here; see BUILD_BRIEF.md §4 — invoked cross-directory by
                    subprocess so a future WhisperX-artifact fix lands once, not twice)
  4. images      → generate_images.py             (in this folder — 16:9, config-driven
                    provider order + normalization, see BUILD_BRIEF.md §3)
  5. stitch      → stitch_video_longform.py        (in this folder — 1920x1080 Ken Burns +
                    bottom-third SRT captions, adapted from the sibling long-form pipeline)
  6. upload      → upload_youtube.py               (in this folder — YouTube private draft)

Usage:
    python run_pipeline.py --project MyVideo --draft my_rough_draft.txt
    python run_pipeline.py --project MyVideo --start-from voiceover --skip-upload
    python run_pipeline.py --project MyVideo --start-from images --prompts-file MyVideo\\prompts_review.json --skip-upload

Valid --start-from values: script, voiceover, scenes, images, stitch, upload

No --format flag yet (narrative vs listicle) — deliberately omitted in this phase rather
than accepted-and-ignored; see BUILD_BRIEF.md §5. It returns when listicle mode is built.
"""

import argparse
import json
import os
import subprocess
import sys
import time

from config_loader import load_config
from console_encoding import ensure_utf8_console
ensure_utf8_console()

# ── optional .env support ─────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


STEPS = ["script", "voiceover", "scenes", "images", "stitch", "upload"]

STEP_LABELS = {
    "script":    "Polish script",
    "voiceover": "Generate voiceover",
    "scenes":    "Split scenes (WhisperX)",
    "images":    "Generate images",
    "stitch":    "Stitch + captions",
    "upload":    "Upload to YouTube",
}

# auto_split_scenes.py is edited in place in shorts_pipeline2, not copied here — see this
# file's docstring and BUILD_BRIEF.md §4. Stated explicitly (not derived implicitly) so
# the cross-directory dependency is visible at a glance, not just in a comment.
SHORTS_PIPELINE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shorts_pipeline2")
)
AUTO_SPLIT_SCENES_PATH = os.path.join(SHORTS_PIPELINE_DIR, "auto_split_scenes.py")


def header(text: str):
    print(f"\n{'═'*60}")
    print(f"  {text}")
    print(f"{'═'*60}")


def step_banner(label: str):
    print(f"\n{'─'*60}")
    print(f"  STEP: {label}")
    print(f"{'─'*60}")


def run_cmd(cmd: list, label: str):
    print(f"\n$ {' '.join(str(c) for c in cmd)}\n")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n❌ {label} failed (exit code {result.returncode})")
        sys.exit(result.returncode)


def should_run(step: str, start_from: str) -> bool:
    if start_from not in STEPS:
        return True
    return STEPS.index(step) >= STEPS.index(start_from)


# ── step runners ──────────────────────────────────────────────────────────────

def run_script(scripts_dir, project_dir, args):
    step_banner(STEP_LABELS["script"])
    cmd = [sys.executable, os.path.join(scripts_dir, "generate_script.py"),
           "--project", project_dir]
    if args.topic:
        cmd += ["--topic", args.topic]
    elif args.draft:
        cmd += ["--draft", args.draft]
    else:
        if os.path.exists(os.path.join(project_dir, "script.txt")):
            print("   script.txt already exists — skipping generation.")
            return
        else:
            print("❌ No --topic or --draft provided and no script.txt found.")
            sys.exit(1)
    run_cmd(cmd, "Script generation")


def approval_gate(project_dir: str) -> bool:
    """
    generate_script.py's approval step needs a real terminal (input()) — the shorts
    pipeline's version printed the whole script to stdout for review, which is fine at
    140-160 words but unusable at long-form length (1500+ words). Open the file in the
    default editor instead, matching what the shorts version's own 'edit' branch already
    did — just make that the default action rather than a secondary option.
    """
    script_path = os.path.join(project_dir, "script.txt")
    if not os.path.exists(script_path):
        print(f"❌ script.txt not found: {script_path}")
        return False

    with open(script_path, "r", encoding="utf-8") as f:
        script = f.read().strip()
    word_count = len(script.split())

    print(f"\n{'═'*60}")
    print("  ✋  APPROVAL GATE — Review the script before continuing")
    print(f"{'═'*60}")
    print(f"\n  [{word_count} words]")
    print(f"  Script saved at: {script_path}")
    print(f"  Opening it for review — edit and save, then come back here.\n")

    if sys.platform == "win32":
        os.startfile(script_path)
    else:
        subprocess.run(["open", script_path])

    while True:
        answer = input("  Approve and continue? [y/n]: ").strip().lower()
        if answer == "y":
            return True
        elif answer == "n":
            print("\n  Pipeline stopped. Edit the script and re-run with --start-from voiceover")
            return False
        else:
            print("  Please enter y or n")


def run_voiceover(scripts_dir, project_dir, config):
    step_banner(STEP_LABELS["voiceover"])

    script_path = os.path.join(project_dir, "script.txt")
    if not os.path.exists(script_path):
        print(f"❌ script.txt not found at {script_path}")
        sys.exit(1)

    # Pre-flight: mid-sentence line wraps make edge-tts insert a ~1.1s pause at the wrap
    # point (confirmed directly, Gravel_S1, 2026-08-15 — see check_script.py's own
    # docstring and CLAUDE.md's BACKLOG for the full root-cause writeup). Fails loud here
    # rather than silently shipping another ~90s of dead air into the narration — cheap to
    # fix (edge-tts is free/local) and much cheaper to catch here than by ear later.
    check = subprocess.run(
        [sys.executable, os.path.join(scripts_dir, "check_script.py"), "--project", project_dir],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check.returncode != 0:
        print(check.stdout)
        print(f"❌ script.txt has unresolved issues — see above.")
        print(f"   Fix with: python check_script.py --project {project_dir} --fix")
        sys.exit(1)

    source_audio_dir = os.path.join(project_dir, "source_audio")
    os.makedirs(source_audio_dir, exist_ok=True)
    wav_out = os.path.join(source_audio_dir, "narration.wav")

    voice = config.get("voice", "en-US-JennyNeural")
    rate  = config.get("voice_rate", "-10%")

    # --file (not --text on argv) — argv gets fragile past ~20-minute scripts;
    # a long-form narration script is exactly that case, unlike a 65-75s Short.
    run_cmd(
        ["edge-tts", "--voice", voice, f"--rate={rate}",
         "--file", script_path, "--write-media", wav_out],
        "Voiceover generation",
    )

    # edge-tts outputs mono 24000Hz; upsample to stereo 44100Hz so BGM mixing
    # doesn't downgrade to narration's native format
    wav_stereo = wav_out + ".stereo.wav"
    run_cmd(
        ["ffmpeg", "-y", "-i", wav_out,
         "-ar", "44100", "-ac", "2", wav_stereo],
        "Upsample narration to stereo 44100Hz",
    )
    import shutil
    shutil.move(wav_stereo, wav_out)

    print(f"✅ Voiceover saved: {wav_out}")


def run_scenes(project_dir, config):
    step_banner(STEP_LABELS["scenes"])

    wav_path = os.path.join(project_dir, "source_audio", "narration.wav")
    if not os.path.exists(wav_path):
        print(f"❌ narration.wav not found: {wav_path}")
        sys.exit(1)

    venv_python = config.get(
        "transcription_venv_python",
        r"C:\Bakcup_Asus\shared-tools\transcription-tools\.venv\Scripts\python.exe"
    )
    if not os.path.exists(venv_python):
        print(f"❌ Transcription venv Python not found: {venv_python}")
        print("   Update 'transcription_venv_python' in pipeline_config.json")
        sys.exit(1)

    manifest_path = os.path.join(project_dir, "manifest.json")
    title = os.path.basename(project_dir)
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            title = json.load(f).get("title", title)

    cmd = [venv_python, AUTO_SPLIT_SCENES_PATH,
           "--audio", "narration.wav",
           "--project", project_dir,
           "--max-seconds", str(config.get("max_scene_seconds", 18)),
           "--title", title,
           "--voice", config.get("voice", "en-US-JennyNeural"),
           "--video-type", "LongVideo",
           "--device", config.get("whisper_device", "cpu")]

    # A 10-15 minute long-form narration is far more transcription load than a 60-90s
    # Short — the unchanged WhisperX defaults (float16/batch_size=16) OOM at real length
    # (confirmed, PHASE_1_REPORT.md §5). Without these, every real run hits that same OOM.
    compute_type = config.get("whisper_compute_type")
    if compute_type:
        cmd += ["--compute-type", compute_type]
    batch_size = config.get("whisper_batch_size")
    if batch_size:
        cmd += ["--batch-size", str(batch_size)]

    run_cmd(cmd, "Scene splitting")


def run_images(scripts_dir, project_dir, force=False, source_doc=None,
               prompts_file=None, dry_run_prompts=False):
    step_banner(STEP_LABELS["images"])
    cmd = [sys.executable, os.path.join(scripts_dir, "generate_images.py"),
           "--project", project_dir]
    if force:
        cmd.append("--force")
    if source_doc:
        abs_source_doc = source_doc if os.path.isabs(source_doc) else os.path.join(scripts_dir, source_doc)
        cmd += ["--source-doc", abs_source_doc]
    if prompts_file:
        abs_prompts_file = prompts_file if os.path.isabs(prompts_file) else os.path.join(scripts_dir, prompts_file)
        cmd += ["--prompts-file", abs_prompts_file]
    if dry_run_prompts:
        cmd += ["--dry-run-prompts"]
    run_cmd(cmd, "Image generation")


def run_stitch(scripts_dir, project_dir):
    step_banner(STEP_LABELS["stitch"])
    run_cmd(
        [sys.executable, os.path.join(scripts_dir, "stitch_video_longform.py"),
         "--project", project_dir],
        "Stitch + captions",
    )


def run_upload(scripts_dir, project_dir, title=None):
    step_banner(STEP_LABELS["upload"])
    cmd = [sys.executable, os.path.join(scripts_dir, "upload_youtube.py"),
           "--project", project_dir]
    if title:
        cmd += ["--title", title]
    run_cmd(cmd, "YouTube upload")


def print_summary(project_dir: str, t_start: float):
    elapsed = time.time() - t_start
    mins, secs = divmod(int(elapsed), 60)
    header(f"✅ Pipeline complete in {mins}m {secs}s")

    manifest_path = os.path.join(project_dir, "manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            m = json.load(f)
        episode    = m.get("episode", "")
        output_dir = os.path.join(project_dir, "output")
        captioned  = os.path.join(output_dir, f"{episode}_captioned.mp4")

        if os.path.exists(captioned):
            size_mb = os.path.getsize(captioned) / (1024 * 1024)
            print(f"   Video  : {captioned}  ({size_mb:.1f} MB)")
        yt_url = m.get("youtube_video_url")
        if yt_url:
            vid_id = m.get("youtube_video_id", "")
            print(f"   YouTube: {yt_url}  (private)")
            print(f"   Studio : https://studio.youtube.com/video/{vid_id}/edit")

    print(f"\n  → Add thumbnails in YouTube Studio, then set to Public.\n")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AeoniumGlow Long-form Pipeline — script to YouTube upload",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--project",      required=True,
                        help="Project name (e.g. Rot_Rescue_Species_Countdown)")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--topic",        help="Topic/idea to expand into a script")
    source.add_argument("--draft",        help="Path to rough draft file")
    parser.add_argument("--start-from",   default="script", choices=STEPS,
                        help="Resume from this step (default: script)")
    parser.add_argument("--skip-upload",  action="store_true",
                        help="Don't upload to YouTube")
    parser.add_argument("--force-images", action="store_true",
                        help="Re-generate images even if they already exist")
    parser.add_argument("--source-doc",   default=None,
                        help="Path to the long-form video source document, passed to "
                             "generate_images.py for story-aware auto-prompt generation. "
                             "If omitted, auto-detects a .md/.txt file in {project}/source_doc/ "
                             "or resolves {project}/source_doc.path.")
    parser.add_argument("--prompts-file", default=None,
                        help="Path to a hand-written prompts JSON (the prompts_review.json "
                             "produced by --dry-run-prompts) to override auto-generation. "
                             "Passed through to generate_images.py.")
    parser.add_argument("--dry-run-prompts", action="store_true",
                        help="Stop after generating and validating image prompts — writes "
                             "prompts_review.json to the project folder and exits without "
                             "generating any images. Review the file, fill in 'override_prompt' "
                             "for any scenes you want to change, then re-run with "
                             "--start-from images --prompts-file <path>.")
    parser.add_argument("--title",        default=None,
                        help="Override YouTube video title")
    args = parser.parse_args()

    # generate_script.py is a near-unmodified Shorts copy (Shorts-length defaults: 65-75s,
    # 140-165 words, "short and punchy for Shorts pacing") that has never been adapted for
    # long-form. PRODUCTION_RUNBOOK.md has said "do not use --start-from script" since it was
    # written, but nothing enforced it -- "script" is also this flag's own DEFAULT, so simply
    # omitting --start-from silently ran the Shorts generator against a long-form project. Fail
    # loudly here instead: cheaper and safer than adapting the generator (see CLAUDE.md
    # BACKLOG), and it turns a silent trap into a signpost pointing at the actual supported path.
    if args.start_from == "script":
        print("❌ --start-from script is not supported for long-form (it defaults to this — you")
        print("   may not have set --start-from at all).")
        print()
        print("   generate_script.py is a near-unmodified Shorts copy: Shorts-length defaults")
        print("   (65-75 seconds, 140-165 words, Shorts pacing), never adapted for a 10-minute")
        print("   video. Running it against a long-form project produces a Shorts-length script.")
        print()
        print("   Write script.txt by hand instead, using:")
        print("     C:\\Users\\Girir\\Documents\\Giri Knowledge Base\\02-PROJECTS\\YouTube\\"
              "Succulents\\Aeonium Glow\\Workflows\\pipeline_script_prompt_template.md")
        print()
        print("   Then save it to {project}\\script.txt and run:")
        print(f"     python run_pipeline.py --project {args.project} --start-from voiceover --skip-upload")
        sys.exit(1)

    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    config      = load_config(scripts_dir)
    t_start     = time.time()

    project_dir = (
        args.project if os.path.isabs(args.project)
        else os.path.join(scripts_dir, args.project)
    )
    project_name = os.path.basename(project_dir)

    header(f"AeoniumGlow Long-form Pipeline — {project_name}")
    print(f"  Starting from: {args.start_from}")
    active = [s for s in STEPS if should_run(s, args.start_from)]
    if args.skip_upload and "upload" in active:
        active.remove("upload")
    print(f"  Steps        : {' → '.join(active)}")

    os.makedirs(project_dir, exist_ok=True)

    if should_run("script", args.start_from):
        run_script(scripts_dir, project_dir, args)
        approved = approval_gate(project_dir)
        if not approved:
            sys.exit(0)

    if should_run("voiceover", args.start_from):
        run_voiceover(scripts_dir, project_dir, config)

    if should_run("scenes", args.start_from):
        run_scenes(project_dir, config)

    if should_run("images", args.start_from):
        run_images(scripts_dir, project_dir, force=args.force_images,
                   source_doc=args.source_doc, prompts_file=args.prompts_file,
                   dry_run_prompts=args.dry_run_prompts)
        if args.dry_run_prompts:
            print("\n✋  Dry-run complete. Review prompts_review.json in the project folder,")
            print("   then re-run with --start-from images --prompts-file <path>.")
            return

    if should_run("stitch", args.start_from):
        run_stitch(scripts_dir, project_dir)

    if should_run("upload", args.start_from) and not args.skip_upload:
        run_upload(scripts_dir, project_dir, title=args.title)
    elif args.skip_upload:
        print(f"\n⏭  Upload skipped (--skip-upload)")

    print_summary(project_dir, t_start)


if __name__ == "__main__":
    main()
