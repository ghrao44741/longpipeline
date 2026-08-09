"""
Regression test for generate_images.py's build_prompt_map() — specifically the
by_scene_id fallback chain (override_prompt > auto_prompt > legacy "prompt").

Found on Etiolation_S1 (2026-08-06): the fallback skipped straight from
override_prompt to a legacy "prompt" key that prompts_review.json entries don't
have (they use "auto_prompt"), so every shot a human correctly left
un-overridden — the file's own documented normal case — fell out of
by_scene_id entirely and silently got re-generated via a fresh, unreviewed
OpenAI call instead of using the approved prompt sitting right there in the
file. All 10 item shots plus 4 others were affected on that run.

No network calls, no API keys required — uses a real project's --prompts-file
shape against a synthetic prompts_review.json and a minimal manifest.

Run:  python tests/test_build_prompt_map.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generate_images import build_prompt_map  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(name)


with tempfile.TemporaryDirectory() as tmp:
    project_dir = tmp
    scenes = [
        {"id": "SCENE-001", "visual_group_id": "item-01"},
        {"id": "SCENE-002", "visual_group_id": "item-01"},
        {"id": "SCENE-003", "visual_group_id": "item-02"},
    ]
    prompts_review = {
        "image_prompts": [
            {
                "scene_id": "item-01",
                "script": "...",
                "auto_prompt": "AUTO: Echeveria elegans, correct approved content.",
                "override_prompt": "",   # left blank -- the documented normal case
            },
            {
                "scene_id": "item-02",
                "script": "...",
                "auto_prompt": "AUTO: this should be replaced by the override below.",
                "override_prompt": "OVERRIDE: Lithops, human-edited content.",
            },
        ]
    }
    prompts_path = os.path.join(project_dir, "prompts_review.json")
    with open(prompts_path, "w", encoding="utf-8") as f:
        json.dump(prompts_review, f)

    pm = build_prompt_map(project_dir, scenes, prompts_path)

    print("\nbuild_prompt_map: blank override_prompt falls back to auto_prompt, not lost")
    check("SCENE-001 (item-01, blank override) resolves to auto_prompt",
          pm.get("SCENE-001") == "AUTO: Echeveria elegans, correct approved content.",
          pm.get("SCENE-001"))
    check("SCENE-002 (item-01's other member) resolves the same way",
          pm.get("SCENE-002") == "AUTO: Echeveria elegans, correct approved content.",
          pm.get("SCENE-002"))

    print("\nbuild_prompt_map: non-blank override_prompt still wins over auto_prompt")
    check("SCENE-003 (item-02, real override) resolves to override_prompt, not auto_prompt",
          pm.get("SCENE-003") == "OVERRIDE: Lithops, human-edited content.",
          pm.get("SCENE-003"))


print("\n" + ("=" * 58))
print(f"FAILED ({len(failures)}): {failures}" if failures else "ALL PASS")
sys.exit(1 if failures else 0)
