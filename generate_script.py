"""
generate_script.py — AeoniumGlow Shorts Pipeline
Polishes a rough draft or expands a topic into a final narration script.
Also generates one image prompt per scene estimate (saved to script_prompts.json).

Usage:
    python generate_script.py --project short-04 --topic "what happens to succulents in winter"
    python generate_script.py --project short-04 --draft rough.txt
    python generate_script.py --project short-04 --topic "..." --model gpt-4o

Requires:
    pip install openai
    OPENAI_API_KEY in environment (or .env file)

Output:
    {project}/script.txt            ← final polished narration
    {project}/script_prompts.json   ← image prompt suggestions per scene block
"""

import argparse
import json
import os
import sys
import textwrap

from config_loader import load_config  # single source of truth, see config_loader.py
from console_encoding import ensure_utf8_console
ensure_utf8_console()

# ── optional .env support ─────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from openai import OpenAI
except ImportError:
    print("❌ openai not installed. Run: pip install openai")
    sys.exit(1)


def polish_script(rough: str, config: dict, model: str, source_doc: str = "") -> str:
    """Call OpenAI to polish the rough draft into a final narration."""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    style = config.get("script_style", "Warm, approachable YouTube Shorts narration. 65–75 seconds when spoken.")

    source_doc_block = (
        "\n\nBACKGROUND — the long-form source document this Short is drawn from. Use it to verify "
        "every factual claim, mechanism, and recommended fix in the draft below. Do NOT invent, add, "
        "or imply anything this document doesn't support, even if it would make a satisfying closing "
        "line — a fluent, plausible-sounding claim that isn't actually true is worse than a plain one. "
        "If the rough draft already contains something the source doesn't support, correct it to match "
        "the source rather than polishing the wording around it:\n"
        f'"""\n{source_doc}\n"""\n'
        if source_doc else ""
    )

    default_comment_pattern = (
        "specific and self-categorising, answerable with one concrete detail from the "
        "viewer's own experience -- never \"let me know what you think\""
    )
    comment_prompt_pattern = config.get("cta", {}).get("comment_prompt_pattern", default_comment_pattern)

    system_prompt = f"""You are an expert YouTube Shorts scriptwriter. {style}
{source_doc_block}
Rules:
- Output ONLY the final spoken narration. No stage directions, no headers, no labels.
- Do not include anything like "Narration:", "Script:", or scene numbers.
- Write in a natural speaking voice — contractions are fine.
- Keep sentences short and punchy for Shorts pacing.
- The script should be 140–165 words total.
- End with the closing insight (the emotional payoff), then — strictly after it, never before or
  woven into it — a two-sentence-maximum ask, in this order: comment, then watch-next. The
  comment prompt must follow this pattern: {comment_prompt_pattern}. Nothing after the ask.
- Every factual claim and recommended fix must be traceable to the background document above, when one is provided. When you need a closing/practical-takeaway line and the draft doesn't already supply one, use the source document's own stated fix — never invent a plausible-sounding alternative."""

    user_prompt = f"Polish this into a final script:\n\n{rough}"

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.7,
    )

    return response.choices[0].message.content.strip()


def generate_image_prompts(script: str, config: dict, model: str, n_scenes: int = 8) -> list:
    """Generate image prompt suggestions for the estimated number of scenes."""
    from generate_images import camera_descriptor_block
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    image_style = config.get("image_style", "Cinematic macro photography, warm natural light, photorealistic.")

    system_prompt = f"""You are a visual director for a succulent care YouTube channel.
Given a narration script, divide it into roughly {n_scenes} visual segments and write one image prompt per segment.

Every prompt must start with one of these camera descriptors — pick whichever best suits the scene:
{camera_descriptor_block(config)}

Rules:
- Be highly specific: describe the exact action, texture, sensory detail, and mood
  Good: "dark, damp soil particles clinging to the skin, visually indicating moisture is still present"
  Bad: "person touching soil"
- Always specify lighting: warm golden-hour sunlight, bright natural light, soft diffused light, etc.
- Include props where natural: terracotta pots, metal or copper watering cans, wooden skewers, wooden tools, linen surfaces
- Vary the setting across segments: home windowsill, backyard garden, small nursery, horticulture room, florist, home plant room
- Show a real person genuinely engaged in the craft where it fits — hands AND faces are both welcome and encouraged. A face can be partially visible, in profile, or looking down at the work — natural and candid, not posed for the camera. Don't default to isolated hand-only shots when a fuller, more human shot would read better.
- No text overlays, no logos, no fantasy plants
- Photorealistic only
- Visual style: {image_style}

Output a JSON array of objects with these fields:
  - "segment": the narration text this image covers (a few words or a sentence)
  - "prompt": the full image generation prompt

Output ONLY valid JSON — no markdown, no explanation."""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": f"Script:\n\n{script}"},
        ],
        temperature=0.6,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content.strip()
    data = json.loads(raw)

    # Handle both {"prompts": [...]} and bare [...]
    if isinstance(data, list):
        return data
    for key in ("prompts", "scenes", "segments", "images"):
        if key in data and isinstance(data[key], list):
            return data[key]
    # Fallback: return whatever values are in the object
    return list(data.values())[0] if data else []


def main():
    parser = argparse.ArgumentParser(description="Polish a script for AeoniumGlow Shorts")
    parser.add_argument("--project", required=True,
                        help="Project folder name (e.g. short-04)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--topic",  help="Topic or rough idea to expand into a script")
    source.add_argument("--draft",  help="Path to a rough draft text file")
    parser.add_argument("--model",  default="gpt-4o",
                        help="OpenAI model (default: gpt-4o)")
    parser.add_argument("--scenes", type=int, default=8,
                        help="Estimated number of scenes (for image prompt count, default: 8)")
    parser.add_argument("--cta", default=None,
                        help="Override the call-to-action sentence at the end of the script")
    parser.add_argument("--skip-prompts", action="store_true",
                        help="Skip image prompt generation")
    parser.add_argument("--source-doc", default=None,
                        help="Path to the source document. If omitted, resolved from the "
                             "project's source_doc.path pointer (base folder included).")
    parser.add_argument("--no-source-doc", action="store_true",
                        help="Ignore the source document entirely")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not set. Add it to your environment or a .env file.")
        sys.exit(1)

    scripts_dir  = os.path.dirname(os.path.abspath(__file__))
    project_dir  = (
        args.project if os.path.isabs(args.project)
        else os.path.join(scripts_dir, args.project)
    )
    os.makedirs(project_dir, exist_ok=True)

    config = load_config(scripts_dir)

    # ── build rough draft ─────────────────────────────────────────────────────
    if args.topic:
        rough = f"Topic: {args.topic}\n\nWrite a complete narration script for this topic."
    else:
        # Look for draft in: as given → project folder → scripts folder
        if os.path.isabs(args.draft):
            draft_path = args.draft
        elif os.path.exists(os.path.join(project_dir, args.draft)):
            draft_path = os.path.join(project_dir, args.draft)
        elif os.path.exists(os.path.join(scripts_dir, args.draft)):
            draft_path = os.path.join(scripts_dir, args.draft)
        else:
            draft_path = os.path.join(project_dir, args.draft)  # for error message
        if not os.path.exists(draft_path):
            print(f"❌ Draft file not found. Looked in:")
            print(f"   {os.path.join(project_dir, args.draft)}")
            print(f"   {os.path.join(scripts_dir, args.draft)}")
            sys.exit(1)
        with open(draft_path, "r", encoding="utf-8") as f:
            rough = f.read().strip()

    # ── load source doc (grounds facts/fixes; prevents the model inventing its own) ──
    source_doc_text = ""
    if args.no_source_doc:
        print("   📖 Source doc: skipped (--no-source-doc)")
    else:
        try:
            from generate_images import load_source_doc
            source_doc_text = load_source_doc(project_dir, args.source_doc, config=config)
        except ImportError as e:
            print(f"   ⚠️  Could not import source-doc resolver ({e}) — continuing without it.")
        if not source_doc_text:
            print("   📖 Source doc: none found — polishing without fact-checking context.")

    # ── polish script ─────────────────────────────────────────────────────────
    print(f"\n✍️  Polishing script with {args.model}...")
    script = polish_script(rough, config, args.model, source_doc=source_doc_text)

    # ── swap CTA if --cta provided ────────────────────────────────────────────
    if args.cta:
        # Replace the last sentence with the provided CTA
        sentences = script.rstrip().rstrip(".!?")
        # Find last sentence boundary
        for sep in [". ", "! ", "? "]:
            idx = script.rfind(sep)
            if idx != -1:
                script = script[:idx + 1].rstrip() + " " + args.cta
                break
        else:
            script = script + " " + args.cta
        print(f"   CTA applied: {args.cta}")

    word_count = len(script.split())
    approx_seconds = round(word_count / 2.2)  # ~130 wpm at -10% TTS rate

    script_path = os.path.join(project_dir, "script.txt")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    print(f"\n{'─'*60}")
    print(f"📄 POLISHED SCRIPT  ({word_count} words ≈ {approx_seconds}s)")
    print(f"{'─'*60}")
    for line in textwrap.wrap(script, width=60):
        print(f"  {line}")
    print(f"{'─'*60}")
    print(f"\n✅ Saved to: {script_path}")

    # ── generate image prompts ────────────────────────────────────────────────
    if not args.skip_prompts:
        print(f"\n🎨 Generating {args.scenes} image prompts...")
        try:
            prompts = generate_image_prompts(script, config, args.model, n_scenes=args.scenes)
            prompts_path = os.path.join(project_dir, "script_prompts.json")
            with open(prompts_path, "w", encoding="utf-8") as f:
                json.dump({"script": script, "image_prompts": prompts}, f, indent=2, ensure_ascii=False)
            print(f"✅ {len(prompts)} image prompts saved to: {prompts_path}")
            print("\n   Preview:")
            for i, p in enumerate(prompts[:3], 1):
                seg = p.get("segment", "")[:50]
                prompt_preview = p.get("prompt", "")[:80]
                print(f"   [{i}] Segment : {seg}...")
                print(f"       Prompt  : {prompt_preview}...")
            if len(prompts) > 3:
                print(f"   ... and {len(prompts) - 3} more.")
        except Exception as e:
            print(f"⚠️  Image prompt generation failed: {e}")
            print("   You can re-run with --skip-prompts and add prompts to manifest.json manually.")

    print(f"\n{'─'*60}")
    print("NEXT STEP:")
    print(f"  Review {script_path}")
    print(f"  Then run:  python run_pipeline.py --project {args.project} --start-from voiceover")
    print(f"{'─'*60}\n")


if __name__ == "__main__":
    main()
