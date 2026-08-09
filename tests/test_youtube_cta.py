"""
Regression test for upload_youtube.py's Phase 3 CTA helpers: build_chapters(),
build_description(), build_pinned_comment() (cta_plan.md "PER-SURFACE SPECIFICS").

Synthetic manifest/config data throughout — no real project, no network calls,
no YouTube credentials required.

Run:  python tests/test_youtube_cta.py
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from upload_youtube import (  # noqa: E402
    build_chapters, build_description, build_pinned_comment, format_chapter_timestamp,
)

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(name)


listicle_manifest = {
    "episode": "Test_S1",
    "scenes": [
        {"id": "SCENE-001", "video_start": 0.0},
        {"id": "SCENE-002", "video_start": 30.0, "item_number": 10, "item_name": "Gasteria"},
        {"id": "SCENE-003", "video_start": 35.0},
        {"id": "SCENE-004", "video_start": 90.0, "item_number": 9, "item_name": "Aeonium arboreum"},
    ],
}
narrative_manifest = {"episode": "Narrative_S1", "scenes": [{"id": "SCENE-001", "video_start": 0.0}]}


# ─────────────────────────────────────────────────────────────────────────────
print("\nformat_chapter_timestamp: M:SS below an hour, H:MM:SS past it")
check("30.0 -> 0:30", format_chapter_timestamp(30.0) == "0:30", format_chapter_timestamp(30.0))
check("90.0 -> 1:30", format_chapter_timestamp(90.0) == "1:30", format_chapter_timestamp(90.0))
check("3661.0 -> 1:01:01", format_chapter_timestamp(3661.0) == "1:01:01", format_chapter_timestamp(3661.0))

print("\nbuild_chapters: listicle -- synthetic Intro at 0:00 plus one row per item, sorted by time")
chapters = build_chapters(listicle_manifest)
check("3 chapters (Intro + 2 items)", len(chapters) == 3, chapters)
check("first chapter is Intro at 0:00", chapters[0] == (0.0, "Intro"), chapters[0])
check("item #10 chapter correct", chapters[1] == (30.0, "#10 Gasteria"), chapters[1])
check("item #9 chapter correct", chapters[2] == (90.0, "#9 Aeonium arboreum"), chapters[2])

print("\nbuild_chapters: include_intro=False drops the synthetic row (for the pinned comment)")
chapters_no_intro = build_chapters(listicle_manifest, include_intro=False)
check("2 chapters, no Intro row", chapters_no_intro == [(30.0, "#10 Gasteria"), (90.0, "#9 Aeonium arboreum")],
      chapters_no_intro)

print("\nbuild_chapters: narrative (no scene carries item_number) -> [] (no error)")
check("empty for narrative manifests", build_chapters(narrative_manifest) == [])


# ─────────────────────────────────────────────────────────────────────────────
print("\nbuild_description: custom_description passed through verbatim, nothing else runs")
config = {"channel_handle": "@aeoniumglow"}
with tempfile.TemporaryDirectory() as tmp:
    check("custom description short-circuits",
          build_description(tmp, listicle_manifest, config, custom_description="EXACT TEXT") == "EXACT TEXT")

print("\nbuild_description: hook + watch-next above the fold, chapters, links, subscribe, tags -- never #shorts")
config = {
    "channel_handle": "@aeoniumglow",
    "cta_watch_next_title": "Stop Succulent Rotting Fast",
    "cta_watch_next_id": "abc123",
    "cta_watch_next_why": "the same kind of mistake, in the opposite direction",
    "cta": {"subscribe_line": "Subscribe to @aeoniumglow for science-backed succulent care."},
    "youtube_tags": ["succulents", "plantcare", "shorts"],
}
with tempfile.TemporaryDirectory() as tmp:
    with open(os.path.join(tmp, "script.txt"), "w", encoding="utf-8") as f:
        f.write("Your succulent is stretching. It is reaching for light it cannot find.")
    desc = build_description(tmp, listicle_manifest, config)
    lines = desc.split("\n")
    check("first line is the hook (from script.txt's opening)",
          lines[0].startswith("Your succulent is stretching"), lines[0])
    check("watch-next tease is the second line (above the fold)",
          "Stop Succulent Rotting Fast" in lines[1] and "opposite direction" in lines[1], lines[1])
    check("chapters present (item lines with timestamps)",
          any("#10 Gasteria" in l for l in lines), lines)
    check("watch-next link present", any("youtu.be/abc123" in l for l in lines), lines)
    check("subscribe line present", any("Subscribe to @aeoniumglow" in l for l in lines), lines)
    check("hashtags present but #shorts stripped out",
          any(l.startswith("#") and "succulents" in l for l in lines)
          and not any("#shorts" in l for l in lines), lines)

print("\nbuild_description: no script.txt, no watch-next config -- degrades cleanly, no crash")
config_minimal = {"channel_handle": "@aeoniumglow"}
with tempfile.TemporaryDirectory() as tmp:
    desc = build_description(tmp, narrative_manifest, config_minimal)
    check("no exception, produces some description text", isinstance(desc, str) and len(desc) > 0, desc)


# ─────────────────────────────────────────────────────────────────────────────
print("\nbuild_pinned_comment: ranked_index mode with items.json present -- full list with timestamps")
config_ranked = {
    "cta": {"pinned_comment_mode": "ranked_index"},
    "cta_comment_prompt": "Which number is sitting on your windowsill right now?",
}
with tempfile.TemporaryDirectory() as tmp:
    with open(os.path.join(tmp, "items.json"), "w", encoding="utf-8") as f:
        f.write("{}")  # presence is all build_pinned_comment checks for
    comment = build_pinned_comment(tmp, listicle_manifest, config_ranked)
    check("contains item #10 with timestamp", "0:30" in comment and "#10 Gasteria" in comment, comment)
    check("contains item #9 with timestamp", "1:30" in comment and "#9 Aeonium arboreum" in comment, comment)
    check("contains the per-video comment prompt", "windowsill" in comment, comment)
    check("does NOT contain a synthetic Intro row (include_intro=False)", "Intro" not in comment, comment)

print("\nbuild_pinned_comment: no items.json -- falls back to the DNA's generic prompt text")
config_fallback = {"cta": {"pinned_comment_mode": "ranked_index"}, "youtube_pinned_comment": "Generic prompt."}
with tempfile.TemporaryDirectory() as tmp:
    comment = build_pinned_comment(tmp, listicle_manifest, config_fallback)
    check("falls back to youtube_pinned_comment when no items.json", comment == "Generic prompt.", comment)

print("\nbuild_pinned_comment: narrative (pinned_comment_mode != ranked_index) -- always the generic prompt")
config_narrative = {"cta": {"pinned_comment_mode": "prompt_only"}, "youtube_pinned_comment": "Narrative prompt."}
with tempfile.TemporaryDirectory() as tmp:
    with open(os.path.join(tmp, "items.json"), "w", encoding="utf-8") as f:
        f.write("{}")  # even if present, mode isn't ranked_index -- should still fall back
    comment = build_pinned_comment(tmp, listicle_manifest, config_narrative)
    check("prompt_only mode ignores items.json, uses generic prompt", comment == "Narrative prompt.", comment)


print("\n" + ("=" * 58))
print(f"FAILED ({len(failures)}): {failures}" if failures else "ALL PASS")
sys.exit(1 if failures else 0)
