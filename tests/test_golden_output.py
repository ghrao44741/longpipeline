"""
test_golden_output.py — Phase 1.5 behaviour-preservation check (BUILD_BRIEF_PHASE_1_5.md §6.1).
Renamed 2026-08-08 from golden_output_test.py -- the old name didn't match test_*.py, so
glob-based test runners silently skipped it. If anything still calls it by the old name,
that's stale.

Captures validate_and_fix_shots()'s exact stdout output (which shot keys are flagged, in
which category, with what reasons) over a fixed corpus of real prompts_review.json files,
BEFORE and AFTER the domain-rule extraction into channel_dna. Byte-identical stdout is a
strictly stronger and simpler proof than parsing+comparing structured violation sets: any
difference at all -- including a mis-escaped regex that silently matches nothing -- shows up
as a diff, with zero risk of a parsing bug in this harness masking a real regression.

Always imports validate_and_fix_shots from THIS pipeline's own generate_images.py (the fork
actually being modified), not shorts_pipeline2's copy. The corpus *data* (prompts_review.json
files) is read from real shorts_pipeline2 projects -- that's fine, it's just input text.

Usage:
    python tests/test_golden_output.py --save baseline.json      # before extraction
    python tests/test_golden_output.py --compare baseline.json   # after extraction
    python tests/test_golden_output.py                           # same as --compare
                                                                   # tests/golden_baseline.json

Run with no flags (2026-08-08 -- the shape any glob-based test runner invokes it in, now
that it matches test_*.py) defaults to comparing against the committed
tests/golden_baseline.json rather than just dumping output and exiting 0 unconditionally.
Before this, the bare/no-flags path could not fail -- it looked like suite coverage once the
rename made it discoverable, but asserted nothing. Also fails loudly (not a silent pass) if
the corpus resolves to fewer projects than CORPUS_PROJECTS -- an empty or partial `results`
previously still printed "IDENTICAL" against whatever it did find, which reads as a pass on
a missing or moved corpus.
"""

import argparse
import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generate_images as gi  # noqa: E402
from config_loader import load_config  # noqa: E402

CORPUS_ROOT = r"C:\Bakcup_Asus\Aeonium_Glow\shorts_pipeline2"
CORPUS_PROJECTS = [
    "Misting_S1_yt", "Misting_S2_yt", "Misting_S3_yt",
    "Myths_S1_yt", "Myths_S2_yt", "Myths_S3_yt",
    "Propagation_S1_yt", "Propagation_S2_ig", "Propagation_S3_yt",
    "Wrinkled_Leaves_S1_yt", "Wrinkled_Leaves_S2_yt", "Wrinkled_Leaves_S3_yt",
]


def _noop_regenerate(retry_shots, fix_note):
    """Stubbed regenerate_fn: returns each shot's CURRENT prompt unchanged. No network call,
    fully deterministic -- the point is to observe what gets flagged, not to actually fix it."""
    return {s["id"]: shot_prompts_ref[s["id"]] for s in retry_shots if s["id"] in shot_prompts_ref}


shot_prompts_ref = {}  # set per-project inside run_one() so the closure above can see it


def run_one(project_name: str, config: dict) -> str:
    """Run validate_and_fix_shots() over one project's prompts_review.json, capturing stdout."""
    global shot_prompts_ref
    path = os.path.join(CORPUS_ROOT, project_name, "prompts_review.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data["image_prompts"]
    shot_prompts = {
        e["scene_id"]: (e.get("override_prompt") or e.get("auto_prompt") or "")
        for e in entries
    }
    shots_needing_gen = [{"id": e["scene_id"], "script": e.get("script", "")} for e in entries]
    shot_prompts_ref = shot_prompts

    buf = io.StringIO()
    with redirect_stdout(buf):
        # max_retries=1: one detection pass is what we want to observe. A no-op regenerate_fn
        # means a second pass would just re-detect the same violations -- redundant, not wrong,
        # but max_retries=1 keeps the captured output minimal and deterministic.
        gi.validate_and_fix_shots(
            dict(shot_prompts), shots_needing_gen, config,
            max_retries=1, regenerate_fn=_noop_regenerate,
        )
    return buf.getvalue()


DEFAULT_BASELINE = str(Path(__file__).resolve().parent / "golden_baseline.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save", help="Capture golden output and save to this JSON file")
    ap.add_argument("--compare", help="Compare current output against this saved JSON file")
    ap.add_argument("--dump", action="store_true",
                     help="Just print captured output for every project, no comparison. "
                          "Explicit escape hatch — bare/no-flags no longer means this.")
    args = ap.parse_args()

    # No flags -> compare against the committed baseline instead of dumping output and
    # exiting 0 unconditionally (2026-08-08). That bare path is exactly what a glob-based
    # test runner invokes, and it could not fail before this -- it looked like coverage
    # once the file was renamed to match test_*.py, but asserted nothing. --dump is now the
    # only way to get the old unconditional-pass dump behavior, and it says so on the label.
    if not args.save and not args.compare and not args.dump:
        args.compare = DEFAULT_BASELINE

    scripts_dir = str(Path(__file__).resolve().parent.parent)
    config = load_config(scripts_dir)

    results = {}
    for project in CORPUS_PROJECTS:
        path = os.path.join(CORPUS_ROOT, project, "prompts_review.json")
        if not os.path.exists(path):
            print(f"  ⚠️  SKIP {project} — prompts_review.json not found")
            continue
        print(f"  Running: {project}...")
        results[project] = run_one(project, config)

    # A missing or moved corpus previously still reported "IDENTICAL" against whatever
    # (possibly zero) projects it found -- silently reads as a pass on a broken corpus path.
    if len(results) < len(CORPUS_PROJECTS):
        missing = [p for p in CORPUS_PROJECTS if p not in results]
        print(f"\n❌ Corpus incomplete: {len(results)}/{len(CORPUS_PROJECTS)} project(s) found. "
              f"Missing: {', '.join(missing)}")
        print(f"   Check CORPUS_ROOT ({CORPUS_ROOT}) — this cannot be a valid golden-output run.")
        sys.exit(1)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Golden output saved: {args.save} ({len(results)} project(s))")

    if args.compare:
        with open(args.compare, "r", encoding="utf-8") as f:
            baseline = json.load(f)

        mismatches = []
        for project in results:
            if project not in baseline:
                mismatches.append((project, "not in baseline"))
                continue
            if results[project] != baseline[project]:
                mismatches.append((project, "output differs"))

        print(f"\n{'=' * 60}")
        if not mismatches:
            print(f"✅ IDENTICAL — all {len(results)} project(s) match the baseline byte-for-byte")
        else:
            print(f"❌ MISMATCH in {len(mismatches)} project(s):")
            for project, reason in mismatches:
                print(f"\n--- {project} ({reason}) ---")
                if reason == "output differs":
                    print("BASELINE:")
                    print(baseline[project])
                    print("CURRENT:")
                    print(results[project])
        print(f"{'=' * 60}")
        sys.exit(1 if mismatches else 0)

    if args.dump:
        for project, output in results.items():
            print(f"\n{'=' * 60}\n{project}\n{'=' * 60}")
            print(output)


if __name__ == "__main__":
    main()
