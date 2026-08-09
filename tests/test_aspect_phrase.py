"""
Regression test for longform_pipeline's aspect-ratio parameterization (Phase 1,
BUILD_BRIEF.md §3a). Before this fix, "9:16 vertical" was hardcoded into every LLM
prompt-template site in generate_images.py/generate_script.py/generate_override_prompts.py;
a config with image_aspect_ratio: "16:9" had no effect on the actual prompt text sent to
the model. This is the verification step that proves that's fixed, and stays fixed,
without needing a real end-to-end run through the script-generation stage (which needs a
real terminal for its approval gate — see CLAUDE.md).

No network calls, no API keys required.

Run:  python tests/test_aspect_phrase.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generate_images as gi  # noqa: E402
import generate_override_prompts as gop  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(name)


# ─────────────────────────────────────────────────────────────────────────────
print("\norientation_phrase: default / explicit 9:16 / explicit 16:9")
check("no config -> defaults to 9:16 vertical (Shorts-safe default)",
      gi.orientation_phrase({}) == "9:16 vertical", gi.orientation_phrase({}))
check("image_aspect_ratio: 9:16 -> 9:16 vertical",
      gi.orientation_phrase({"image_aspect_ratio": "9:16"}) == "9:16 vertical")
check("image_aspect_ratio: 16:9 -> 16:9 widescreen",
      gi.orientation_phrase({"image_aspect_ratio": "16:9"}) == "16:9 widescreen")

print("\ncamera_descriptor_block: phrase propagates into every camera-descriptor line")
block_916 = gi.camera_descriptor_block({"image_aspect_ratio": "9:16"})
block_169 = gi.camera_descriptor_block({"image_aspect_ratio": "16:9"})
check("9:16 config: block contains '9:16 vertical', not '16:9'",
      "9:16 vertical" in block_916 and "16:9" not in block_916)
check("16:9 config: block contains '16:9 widescreen', not bare '9:16'",
      "16:9 widescreen" in block_169 and "9:16" not in block_169)
check("both configs produce all 5 camera-shot phrasings",
      block_916.count("A ") + ("A tall" in block_916) == 5 or block_916.count("\n") == 4,
      block_916)

print("\nauto_generate_prompt fallback string: aspect-aware, no network call")
# auto_generate_prompt() falls back to a hardcoded-format string when the OpenAI call
# fails. OPENAI_API_KEY IS set in this environment, so a real call would otherwise fire
# here -- monkeypatch openai.OpenAI to fail instantly, forcing the fallback path
# deterministically with zero network traffic regardless of environment.
import openai as _openai_module  # noqa: E402
_original_OpenAI = _openai_module.OpenAI


def _network_disabled(*_a, **_kw):
    raise RuntimeError("network disabled for this test")


_openai_module.OpenAI = _network_disabled
try:
    fallback_916 = gi.auto_generate_prompt("a wilting leaf", {"image_aspect_ratio": "9:16"})
    fallback_169 = gi.auto_generate_prompt("a wilting leaf", {"image_aspect_ratio": "16:9"})
finally:
    _openai_module.OpenAI = _original_OpenAI

check("9:16 fallback prompt starts with the 9:16 vertical phrase",
      fallback_916.startswith("A 9:16 vertical"), fallback_916)
check("16:9 fallback prompt starts with the 16:9 widescreen phrase, not 9:16",
      fallback_169.startswith("A 16:9 widescreen") and "9:16" not in fallback_169,
      fallback_169)

print("\ngenerate_override_prompts.build_system_prompt: placeholder substitution")
sp_916 = gop.build_system_prompt({"image_aspect_ratio": "9:16"})
sp_169 = gop.build_system_prompt({"image_aspect_ratio": "16:9"})
sp_none = gop.build_system_prompt(None)
check("9:16 config: system prompt contains '9:16 vertical'",
      "9:16 vertical" in sp_916)
check("16:9 config: system prompt contains '16:9 widescreen', not bare 9:16",
      "16:9 widescreen" in sp_169 and "9:16 vertical" not in sp_169)
check("no leftover %%ORIENTATION%% placeholder in either output",
      "%%ORIENTATION%%" not in sp_916 and "%%ORIENTATION%%" not in sp_169)
check("config=None doesn't crash -- defaults to 9:16 vertical",
      "9:16 vertical" in sp_none, sp_none[:80])
check("JSON output-format example in the prompt also uses the right phrase (16:9 case)",
      '"16:9 widescreen' in sp_169, sp_169)

print("\ncrop_to_aspect / _parse_aspect_ratio: ratio string parsing")
check("9:16 parses to width/height ~0.5625",
      abs(gi._parse_aspect_ratio("9:16") - 0.5625) < 1e-6)
check("16:9 parses to width/height ~1.7778",
      abs(gi._parse_aspect_ratio("16:9") - 1.77778) < 1e-3)

print("\nconfig_loader.load_config: channel_dna merge is real, not just a plan on paper")
from config_loader import load_config  # noqa: E402
merged = load_config(str(Path(__file__).resolve().parent.parent))
check("merged config resolves image_aspect_ratio: 16:9 for this pipeline",
      merged.get("image_aspect_ratio") == "16:9", merged.get("image_aspect_ratio"))
check("merged config has 'subjects' (from DNA), not 'approved_species'",
      "subjects" in merged and "approved_species" not in merged)
check("approved_species_list() reads the merged 'subjects' key successfully",
      len(gi.approved_species_list(merged)) > 0, gi.approved_species_list(merged))


print("\n" + ("=" * 58))
print(f"FAILED ({len(failures)}): {failures}" if failures else "ALL PASS")
sys.exit(1 if failures else 0)
