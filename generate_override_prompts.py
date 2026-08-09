"""
generate_override_prompts.py — Aeonium Glow / That's Why pipeline
Reads a project's prompts_review.json (from --dry-run-prompts), calls the
OpenAI API to write photorealistic override prompts in the channel's
established visual style, and saves them back to the same file.

Usage:
    python generate_override_prompts.py --project Wrinkled_Leaves_S3_yt

Options:
    --project         Project variant folder (e.g. Wrinkled_Leaves_S3_yt)
    --all             Re-generate overrides even if override_prompt is already filled
    --scene           Only generate for a specific scene ID (e.g. SCENE-007)
    --model           OpenAI model to use (default: gpt-4o)
    --dry-run         Print prompts to stdout instead of saving
    --source-doc      Explicit path to the source document (overrides auto-detection)
    --no-source-doc   Ignore the source document entirely

Source document:
    Auto-detected via the project's source_doc.path pointer (see
    resolve_source_doc_path in generate_images.py). The variant folder
    (Wrinkled_Leaves_S3_yt) and its base folder (Wrinkled_Leaves_S3) are both
    searched, so the pointer only needs to exist once in the base folder.

Requirements:
    pip install openai --break-system-packages
    OPENAI_API_KEY in .env (same .env used by the rest of the pipeline)
"""

import argparse
import json
import os
import re
import sys

# ── load .env ─────────────────────────────────────────────────────────────────
def load_dotenv(path: str):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ── system prompt ─────────────────────────────────────────────────────────────
def build_system_prompt(config: dict = None) -> str:
    """
    Same visual-style-pattern system prompt as before, with the orientation phrase
    ("9:16 vertical" / "16:9 widescreen") driven off config["image_aspect_ratio"]
    instead of hardcoded, via generate_images.orientation_phrase(). Defaults to
    "9:16 vertical" when config is None/omits the key, matching prior behavior.
    """
    try:
        from generate_images import orientation_phrase
        o = orientation_phrase(config or {})
    except ImportError:
        o = "9:16 vertical"

    # Plain string + str.replace(), NOT an f-string — the body below contains literal
    # JSON braces (the OUTPUT FORMAT example) that an f-string would try to parse as
    # replacement fields. %%ORIENTATION%% is a placeholder token, substituted below.
    prompt = """\
You are an expert image prompt writer for the Aeonium Glow (@aeoniumglow) YouTube channel — a science-backed succulent care channel.

Your job: for each scene, read the script narration and the auto-generated prompt, then write a high-quality override_prompt that matches the channel's exact visual style.

━━━ VISUAL STYLE PATTERN ━━━
Follow this structure precisely:

  %%ORIENTATION%%. Warm cinematic [macro / extreme macro] photography [COMPOSITION] [SUBJECT + SPECIES] [PROPS]. Shallow depth of field, natural golden-hour soft diffused window light. Rich earthy tones — terracotta, sage green, deep charcoal. Botanical and editorial feel. Botanically accurate, photorealistic. No text, no logos, no blue or cool tones.

Where [COMPOSITION] is one of:
  • "showing faceless human hands [verb]-ing [object]"          ← action/hands scene
  • "of [species], [state/condition]"                           ← plant-only observation
  • "looking down at [subject]"                                 ← top-down: soil check, roots, pot base
  • "focused on [subject]"                                      ← close-up detail without hands

━━━ COMPOSITION RULES ━━━
• Hands in frame → ALWAYS faceless (cut off at mid-forearm, no faces visible)
• Plant-state scenes → NO hands; just the plant showing its current visual state
• CTA / final scene → MUST end with: "Leave negative space in the lower third — deep charcoal background area for text overlay."
• Light is ALWAYS warm: golden hour, soft window light, warm ambient — never harsh, studio, or blue-tinted
• For stressed/dry/damaged plant scenes → use warm light but show duller plant colour and visible dehydration/damage

━━━ CRITICAL RULE — SHOW CURRENT STATE, NOT SOLUTION ━━━
The image shows exactly what the narration is describing RIGHT NOW — not what happens next, not the fix.
Examples:
  "the leaves are wrinkled and shriveling" → show wrinkled shriveling leaves — NOT a watering can
  "you might be tempted to water immediately" → show dry stressed plant — NOT someone watering
  "roots need room to breathe" → show packed, root-bound soil — NOT a newly repotted plant
  "at 3 a.m., the stomata open" → moonlight/night atmosphere — NOT golden hour

━━━ SPECIES SELECTION ━━━
Always name a real species. Choose based on what the scene's visual needs:

  Echeveria elegans (Mexican Snowball)
    → pale grey-green compact rosette, powdery white farina
    → best for: general watering demos, repotting, healthy baseline, hydration checks

  Graptopetalum paraguayense (Ghost Plant)
    → pale lavender-grey to pink-purple rosette
    → best for: color-change examples, beginner references

  Crassula ovata (Jade Plant)
    → thick oval glossy leaves, deep green, woody stems
    → best for: indoor/overwatering examples, thick-leaved comparisons

  Aeonium arboreum Zwartkop (Black Rose Aeonium)
    → deep purple-black architectural rosette
    → best for: channel identity shots, dormancy, dark contrast, anthocyanin

  Echeveria 'Perle von Nürnberg' (Pearl of Nuremberg)
    → dusty pink-purple rosette with farina, deepens under stress
    → best for: stress colouration, aesthetic close-ups, anthocyanin

  Haworthia fasciata (Zebra Plant)
    → dark green with white horizontal banding, compact
    → best for: low-light, indoor shade-tolerant examples

  Sedum rubrotinctum Aurora (Pink Jelly Beans)
    → small bean-shaped leaves, pale pink-green with red-coral tips
    → best for: sunlight/light stress colouration

  Sedum morganianum (Burro's Tail)
    → trailing stems with plump blue-green teardrop leaves
    → best for: trailing/hanging succulent examples

━━━ PROP PALETTE ━━━
terracotta pot, unglazed terracotta saucer, linen cloth surface, copper or brass watering can, small wooden trowel, potting bench, natural wood surface

━━━ FORBIDDEN ━━━
• No faces, eyes, or full body
• No clocks or watches
• No text or logos
• No blue or cool tones — warm palette only
• No "generic succulent" — always a named species
• No fantasy plants or anatomically impossible forms
• No dark rectangular backing bands behind text areas

━━━ OUTPUT FORMAT ━━━
Return a single JSON object with one key, "scenes", holding an array with ONE ENTRY FOR
EVERY SCENE YOU WERE GIVEN — never fewer. Each entry has ONLY these two keys:

{"scenes": [
  {"scene_id": "SCENE-001", "override_prompt": "%%ORIENTATION%%. Warm cinematic ..."},
  {"scene_id": "SCENE-002", "override_prompt": "%%ORIENTATION%%. Warm cinematic ..."}
]}

If you were given 9 scenes, the array must contain 9 entries. Do not stop after the first
one. No markdown fences, no extra keys, no explanation — raw JSON only.
"""
    return prompt.replace("%%ORIENTATION%%", o)


def build_user_message(scenes_data: list, source_doc: str = "") -> str:
    """Build the user turn listing all scenes that need an override prompt."""
    lines = []
    if source_doc:
        lines += [
            "Background — the long-form source document these Shorts were cut from.",
            "Use it to understand what each scene is actually describing "
            "(which plant, which stage, what is physically happening). "
            "Do NOT illustrate anything from this document that the scene's own "
            "narration does not mention:",
            '"""',
            source_doc,
            '"""',
            "",
        ]
    lines.append(
        f"Generate override prompts for ALL {len(scenes_data)} scenes below. "
        f'Return {{"scenes": [...]}} containing exactly {len(scenes_data)} entries, '
        f"one per scene_id, in this order:\n"
    )
    for item in scenes_data:
        lines.append(f"---")
        lines.append(f"scene_id: {item['scene_id']}")
        lines.append(f"script:   {item['script']}")
        if item.get("auto_prompt"):
            lines.append(f"auto_prompt: {item['auto_prompt']}")
        lines.append("")
    return "\n".join(lines)


def generate_prompts(
    scenes_to_write: list,
    model: str = "gpt-4o",
    dry_run: bool = False,
    source_doc: str = "",
    extra_instruction: str = "",
    config: dict = None,
) -> dict:
    """
    Call OpenAI and return {scene_id: override_prompt} for each scene.
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ openai package not found. Run: pip install openai --break-system-packages")
        sys.exit(1)

    client = OpenAI()  # uses OPENAI_API_KEY from env

    user_msg = build_user_message(scenes_to_write, source_doc)
    if extra_instruction:
        user_msg += (
            "\n━━━ CORRECTION REQUIRED — a validator rejected your previous prompts ━━━\n"
            f"{extra_instruction}\n"
            "Rewrite the scenes above fixing exactly these problems, keeping the same "
            "visual style pattern and the same scene_ids.\n"
        )

    if dry_run:
        print("\n── DRY RUN — would send this to OpenAI ────────────────────")
        print(f"Model: {model}")
        print(f"Scenes: {[s['scene_id'] for s in scenes_to_write]}")
        print(f"Source doc: {len(source_doc)} chars" if source_doc else "Source doc: (none)")
        print("User message (truncated):")
        print(user_msg[:800])
        print("...")
        return {}

    print(f"   Calling {model} for {len(scenes_to_write)} scene(s)...")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": build_system_prompt(config)},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.7,
        response_format={"type": "json_object"} if "gpt-4o" in model else None,
    )

    raw = response.choices[0].message.content.strip()

    # Parse — the model may return a JSON array or a wrapped object
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Try stripping markdown fences if the model added them anyway
        raw_clean = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        parsed = json.loads(raw_clean)

    # Normalise: accept {"scenes": [...]} or [...]
    if isinstance(parsed, dict):
        for key in ("scenes", "prompts", "results", "override_prompts"):
            if key in parsed and isinstance(parsed[key], list):
                parsed = parsed[key]
                break
        else:
            # Single scene returned as a dict — wrap it
            if "scene_id" in parsed:
                parsed = [parsed]
            else:
                # Last resort: grab the first list value
                for v in parsed.values():
                    if isinstance(v, list):
                        parsed = v
                        break

    if isinstance(parsed, dict):
        # Still a dict here means the model ignored the {"scenes": [...]} contract.
        print("   ⚠️  Model returned an unexpected JSON shape; could not extract a scene list.")
        return {}

    results = {
        item["scene_id"]: item["override_prompt"]
        for item in parsed
        if isinstance(item, dict) and "scene_id" in item and item.get("override_prompt")
    }

    # The json_object response format used to coax a single scene object out of the
    # model, which the normalisation above would happily wrap — silently dropping
    # every other scene. Never let a short response pass unnoticed again.
    missing = [s["scene_id"] for s in scenes_to_write if s["scene_id"] not in results]
    if missing:
        print(f"   ⚠️  Model returned {len(results)}/{len(scenes_to_write)} scenes. "
              f"Missing: {', '.join(missing)}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Generate Aeonium Glow override prompts from dry-run prompts_review.json"
    )
    parser.add_argument("--project",  required=True,
                        help="Project variant folder (e.g. Wrinkled_Leaves_S3_yt)")
    parser.add_argument("--all",      action="store_true",
                        help="Re-generate even if override_prompt is already set")
    parser.add_argument("--scene",    default=None,
                        help="Generate for one scene only (e.g. SCENE-007)")
    parser.add_argument("--model",    default="gpt-4o",
                        help="OpenAI model (default: gpt-4o)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Print what would be sent to OpenAI; don't save")
    parser.add_argument("--source-doc", default=None,
                        help="Path to the source document. If omitted, resolved from the "
                             "project's source_doc.path pointer (base folder included).")
    parser.add_argument("--no-source-doc", action="store_true",
                        help="Ignore the source document entirely")
    parser.add_argument("--skip-validate", action="store_true",
                        help="Skip the brand-rule validation pass (setting overuse, generic "
                             "species, action mismatch, semantic reversal, hallucination)")
    args = parser.parse_args()

    # ── resolve paths ─────────────────────────────────────────────────────────
    script_dir   = os.path.dirname(os.path.abspath(__file__))
    env_path     = os.path.join(script_dir, ".env")
    load_dotenv(env_path)

    project_dir = (
        args.project if os.path.isabs(args.project)
        else os.path.join(script_dir, args.project)
    )
    if not os.path.isdir(project_dir):
        print(f"❌ Project folder not found: {project_dir}")
        sys.exit(1)

    review_path = os.path.join(project_dir, "prompts_review.json")
    if not os.path.exists(review_path):
        print(f"❌ prompts_review.json not found in {project_dir}")
        print("   Run: python run_pipeline.py --project X --start-from images --dry-run-prompts")
        sys.exit(1)

    if not os.environ.get("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not set. Add it to your .env file.")
        sys.exit(1)

    # ── load review file ──────────────────────────────────────────────────────
    with open(review_path, "r", encoding="utf-8") as f:
        review_data = json.load(f)

    # Support both top-level list and {"scenes": [...]}
    if isinstance(review_data, list):
        scenes = review_data
        top_level_key = None
    else:
        # Find the list of scenes regardless of wrapper key
        scenes = None
        for k, v in review_data.items():
            if isinstance(v, list) and len(v) and isinstance(v[0], dict) and "scene_id" in v[0]:
                scenes = v
                top_level_key = k
                break
        if scenes is None:
            print("❌ Could not find scene list in prompts_review.json")
            sys.exit(1)

    print(f"📋 Loaded {len(scenes)} scene(s) from {review_path}")

    # ── decide which scenes need prompts ──────────────────────────────────────
    if args.scene:
        scenes_to_write = [s for s in scenes if s.get("scene_id") == args.scene]
        if not scenes_to_write:
            print(f"❌ Scene '{args.scene}' not found in prompts_review.json")
            sys.exit(1)
    elif args.all:
        scenes_to_write = scenes
    else:
        scenes_to_write = [s for s in scenes if not s.get("override_prompt", "").strip()]

    if not scenes_to_write:
        print("✅ All scenes already have override_prompt set. Use --all to regenerate.")
        sys.exit(0)

    print(f"   Scenes to write: {[s['scene_id'] for s in scenes_to_write]}")

    # ── load config once (drives orientation phrase + source-doc/validator calls) ──
    try:
        from generate_images import load_config
        config = load_config(script_dir)
    except ImportError as e:
        print(f"   ⚠️  Could not import config loader ({e}) — using defaults (9:16).")
        config = {}

    # ── load source doc (shared resolver — honours source_doc.path pointers) ───
    source_doc = ""
    if args.no_source_doc:
        print("   📖 Source doc: skipped (--no-source-doc)")
    else:
        try:
            from generate_images import load_source_doc
            source_doc = load_source_doc(project_dir, args.source_doc, config=config)
        except ImportError as e:
            print(f"   ⚠️  Could not import source-doc resolver ({e}) — continuing without it.")
        if not source_doc:
            print("   📖 Source doc: none found — prompts will be written without story context.")

    # ── call OpenAI ───────────────────────────────────────────────────────────
    results = generate_prompts(scenes_to_write, model=args.model, dry_run=args.dry_run,
                               source_doc=source_doc, config=config)

    if args.dry_run:
        sys.exit(0)

    # Retry any scenes the model skipped, asking only for what's still missing.
    for attempt in range(2):
        still_missing = [s for s in scenes_to_write if s["scene_id"] not in results]
        if not still_missing:
            break
        print(f"   ↻  Retry {attempt + 1}/2 for {len(still_missing)} missing scene(s)...")
        retry = generate_prompts(still_missing, model=args.model, source_doc=source_doc,
                                 config=config)
        if not retry:
            break
        results.update(retry)

    # ── brand validation ──────────────────────────────────────────────────────
    # Same programmatic checks generate_images.py applies to its auto-generated
    # prompts: setting overuse, bare "succulent", action mismatch, semantic
    # reversal, hallucination. Violating scenes are rewritten through THIS
    # script's own model call so they keep the override visual style.
    if args.skip_validate:
        print("   ⏭  Brand validation skipped (--skip-validate)")
    elif results:
        try:
            from generate_images import validate_and_fix_shots, load_brand_brief
        except ImportError as e:
            print(f"   ⚠️  Could not import validator ({e}) — skipping brand validation.")
        else:
            by_id = {s["scene_id"]: s for s in scenes_to_write}
            shots = [{"id": sid, "script": by_id[sid].get("script", "")} for sid in results]

            def regenerate(retry_shots, fix_note):
                subset = [by_id[s["id"]] for s in retry_shots if s["id"] in by_id]
                return generate_prompts(subset, model=args.model, source_doc=source_doc,
                                        extra_instruction=fix_note, config=config)

            print("\n🔎 Validating prompts against brand rules...")
            results = validate_and_fix_shots(
                dict(results), shots, config,
                source_doc=source_doc,
                brand_brief=load_brand_brief(script_dir),
                regenerate_fn=regenerate,
            )

    # ── patch scenes in place ─────────────────────────────────────────────────
    updated = 0
    for scene in scenes:
        sid = scene.get("scene_id")
        if sid in results:
            scene["override_prompt"] = results[sid]
            updated += 1
            print(f"   ✔  {sid}: {results[sid][:80]}...")

    if updated == 0:
        print("⚠️  OpenAI returned no matching scene IDs. Check the model response above.")
        sys.exit(1)

    # ── save back ─────────────────────────────────────────────────────────────
    if top_level_key is None:
        out_data = scenes
    else:
        review_data[top_level_key] = scenes
        out_data = review_data

    with open(review_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved {updated} override prompt(s) → {review_path}")
    print("   Next: python run_pipeline.py --project X --variants yt --start-from images --prompts-file path/to/prompts_review.json")


if __name__ == "__main__":
    main()
