"""
make_contact_sheet.py — one labelled sheet of every generated image, for fast visual review.

The pipeline's `--dry-run-prompts` hard stop reviews PROMPT TEXT, not pixels. A prompt can read
perfectly and still render the wrong thing — the canonical case being a "succulent stem
cross-section" prompt that came back as a sliced kiwi. Nothing between generation and stitch
looks at an actual image.

This closes that gap cheaply: montage every PNG in {project}/images/ into a single sheet,
captioned with its shot key, item number, and the species its prompt names, in NARRATION ORDER.
Scan it, note the bad keys, delete those PNGs, and re-run generate_images.py — which skips
anything already on disk, so it regenerates exactly what you deleted.

Usage:
    python make_contact_sheet.py --project Etiolation_S1
    python make_contact_sheet.py --project Etiolation_S1 --tile-width 600 --cols 5

Output:
    {project}/output/contact_sheet.png

Requires Pillow. No network, no browser, no external service.
"""

import argparse
import json
import os
import re
import sys

from console_encoding import ensure_utf8_console
ensure_utf8_console()

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("❌ Pillow is required:  pip install Pillow")
    sys.exit(1)


CAPTION_H = 46          # px of caption strip under each tile
PAD = 10                # px between tiles
BG = (24, 24, 26)
FG = (238, 238, 238)
DIM = (150, 150, 155)
ITEM_FG = (255, 196, 92)   # item shots highlighted — they carry the countdown


# ── inputs ────────────────────────────────────────────────────────────────────

def load_prompt_map(project_dir: str) -> dict:
    """
    Read prompts_review.json into {shot_key: prompt_text}, tolerating the several
    shapes it has had (dict of dicts, dict of strings, list of dicts, and this
    pipeline's actual shape — {"image_prompts": [...]}, mirroring the "scene_id"/
    "override_prompt"/"auto_prompt" fields generate_images.py itself reads at
    build_prompt_map():216-218). Prefers override_prompt over auto_prompt, matching
    what generate_images.py actually uses.
    """
    path = os.path.join(project_dir, "prompts_review.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    def pick(entry):
        if isinstance(entry, str):
            return entry
        if isinstance(entry, dict):
            return (entry.get("override_prompt") or entry.get("auto_prompt")
                    or entry.get("prompt") or "")
        return ""

    out = {}
    if isinstance(raw, dict):
        # could be {key: entry}, {"shots": [...]}, or {"image_prompts": [...]}
        list_key = "shots" if isinstance(raw.get("shots"), list) else (
            "image_prompts" if isinstance(raw.get("image_prompts"), list) else None
        )
        if list_key:
            for e in raw[list_key]:
                k = e.get("key") or e.get("shot") or e.get("scene_id") or e.get("id")
                if k:
                    out[k] = pick(e)
        else:
            for k, e in raw.items():
                out[k] = pick(e)
    elif isinstance(raw, list):
        for e in raw:
            k = e.get("key") or e.get("shot") or e.get("scene_id") or e.get("id")
            if k:
                out[k] = pick(e)
    return {k: v for k, v in out.items() if k}


def load_subjects(scripts_dir: str) -> list:
    """Canonical subject names from the merged config, for labelling. Best-effort."""
    try:
        sys.path.insert(0, scripts_dir)
        from config_loader import load_config          # noqa
        cfg = load_config(scripts_dir)
        raw = cfg.get("subjects", cfg.get("approved_species", {}))
        return list(raw) if isinstance(raw, dict) else [
            s if isinstance(s, str) else (s.get("name") or "") for s in raw
        ]
    except Exception:
        return []


def name_species(prompt: str, subjects: list) -> str:
    """First subject whose first two name-words both appear in the prompt. Mirrors
    names_species()'s heuristic so labels agree with what the validator sees."""
    p = prompt.lower()
    for sp in subjects:
        words = sp.replace("'", "").split()[:2]
        if words and all(w.lower() in p for w in words):
            return sp
    return ""


def narration_order(project_dir: str) -> list:
    """Shot keys in the order a viewer meets them. Falls back to natural sort."""
    manifest = os.path.join(project_dir, "manifest.json")
    if os.path.exists(manifest):
        try:
            with open(manifest, "r", encoding="utf-8") as f:
                scenes = json.load(f).get("scenes", [])
            seen, order = set(), []
            for s in scenes:
                key = s.get("visual_group_id") or s.get("id")
                if key and key not in seen:
                    seen.add(key)
                    order.append(key)
            if order:
                return order
        except Exception:
            pass
    return []


def item_numbers(project_dir: str) -> dict:
    """{shot_key: item_number} for listicles, so item shots are obvious on the sheet."""
    out = {}
    path = os.path.join(project_dir, "items.json")
    if not os.path.exists(path):
        return out
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        items = raw.get("items", raw) if isinstance(raw, dict) else raw
        manifest = os.path.join(project_dir, "manifest.json")
        if not os.path.exists(manifest):
            return out
        with open(manifest, "r", encoding="utf-8") as f:
            scenes = json.load(f).get("scenes", [])
        for s in scenes:
            n = s.get("item_number")
            if n is None:
                continue
            key = s.get("visual_group_id") or s.get("id")
            if key:
                out.setdefault(key, n)
    except Exception:
        pass
    return out


def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


# ── rendering ─────────────────────────────────────────────────────────────────

def get_font(size: int):
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def build(project_dir: str, tile_w: int, cols: int) -> str:
    images_dir = os.path.join(project_dir, "images")
    if not os.path.isdir(images_dir):
        print(f"❌ No images folder: {images_dir}")
        sys.exit(1)

    files = {os.path.splitext(f)[0]: os.path.join(images_dir, f)
             for f in os.listdir(images_dir)
             if f.lower().endswith((".png", ".jpg", ".jpeg"))}
    if not files:
        print(f"❌ No images in {images_dir}")
        sys.exit(1)

    prompts = load_prompt_map(project_dir)
    subjects = load_subjects(os.path.dirname(os.path.abspath(__file__)))
    items = item_numbers(project_dir)

    order = [k for k in narration_order(project_dir) if k in files]
    order += sorted((k for k in files if k not in order), key=natural_key)

    missing = [k for k in prompts if k not in files]

    # tile geometry from the first image's aspect
    with Image.open(files[order[0]]) as probe:
        aspect = probe.height / probe.width
    tile_h = int(tile_w * aspect)

    if not cols:
        cols = 6 if len(order) > 24 else 4
    rows = (len(order) + cols - 1) // cols

    sheet_w = cols * tile_w + (cols + 1) * PAD
    sheet_h = rows * (tile_h + CAPTION_H) + (rows + 1) * PAD + 52
    sheet = Image.new("RGB", (sheet_w, sheet_h), BG)
    draw = ImageDraw.Draw(sheet)

    f_title = get_font(26)
    f_key = get_font(19)
    f_sub = get_font(16)

    # Plain ASCII in the drawn title — system fonts often lack the warning glyph and
    # render it as a tofu box. Emoji is fine on stdout, not on the sheet.
    title = f"{os.path.basename(project_dir.rstrip(os.sep))}   {len(order)} images"
    draw.text((PAD, 14), title, font=f_title, fill=FG)
    if missing:
        w = draw.textlength(title, font=f_title)
        draw.text((PAD + w + 24, 14), f"{len(missing)} MISSING", font=f_title,
                  fill=(255, 120, 110))

    for i, key in enumerate(order):
        r, c = divmod(i, cols)
        x = PAD + c * (tile_w + PAD)
        y = 52 + PAD + r * (tile_h + CAPTION_H + PAD)

        try:
            with Image.open(files[key]) as im:
                sheet.paste(im.convert("RGB").resize((tile_w, tile_h), Image.LANCZOS), (x, y))
        except Exception as e:
            draw.rectangle([x, y, x + tile_w, y + tile_h], fill=(60, 30, 30))
            draw.text((x + 8, y + 8), f"unreadable\n{e}", font=f_sub, fill=FG)

        n = items.get(key)
        label = f"#{n}  {key}" if n is not None else key
        draw.text((x, y + tile_h + 5), label, font=f_key,
                  fill=ITEM_FG if n is not None else FG)

        sp = name_species(prompts.get(key, ""), subjects)
        if not sp:
            sp = (prompts.get(key, "")[:52] + "…") if prompts.get(key) else "— no prompt found —"
        draw.text((x, y + tile_h + 26), sp[:58], font=f_sub, fill=DIM)

    out_dir = os.path.join(project_dir, "output")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "contact_sheet.png")
    sheet.save(out_path)

    print(f"✅ {out_path}")
    print(f"   {len(order)} images, {cols}×{rows} grid, {sheet_w}×{sheet_h}px")
    if items:
        print(f"   {len(items)} item shots highlighted in amber")
    if missing:
        print(f"\n⚠️  {len(missing)} shot(s) have a prompt but NO image — generation failed:")
        for k in sorted(missing, key=natural_key):
            print(f"     {k}")
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Labelled contact sheet of a project's generated images")
    ap.add_argument("--project", required=True, help="Project folder name or absolute path")
    ap.add_argument("--tile-width", type=int, default=480, help="Tile width in px (default 480)")
    ap.add_argument("--cols", type=int, default=0, help="Columns (default: auto)")
    args = ap.parse_args()

    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = (args.project if os.path.isabs(args.project)
                   else os.path.join(scripts_dir, args.project))
    if not os.path.isdir(project_dir):
        print(f"❌ Project folder not found: {project_dir}")
        sys.exit(1)

    build(project_dir, args.tile_width, args.cols)


if __name__ == "__main__":
    main()
