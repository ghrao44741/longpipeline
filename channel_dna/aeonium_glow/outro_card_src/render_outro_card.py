#!/usr/bin/env python3
"""
render_outro_card.py — regenerate the Aeonium Glow outro card PNG from the HTML
template with per-video copy, so the watch-next line never has to be hand-edited.

Watch-out it fixes (CLAUDE.md backlog, 2026-08-14): the v1/v2 card hardcoded the
watch-next title in HTML, so every new video with a different watch-next target
needed a manual card regen. Now the copy is passed on the command line and the
HTML is a template.

Usage:
    python render_outro_card.py \
        --watch-next-title "Stop Succulent Rotting Fast: The First 5 Minutes Matter" \
        [--ask-line1 "Which number is on"] \
        [--ask-line2 "your"] \
        [--ask-line3 " windowsill right now?"] \
        [--ask-sub "Tell me in the comments"] \
        [--wn-label "Up next — same mistake, opposite direction"] \
        [--out outro_card.png]

Defaults match the Etiolation_S1 card. The watch-next title is split on the first
": " — the part before it renders plain, the part after it renders in the accent
(terracotta) color, matching the v2 design.

Requires Chrome (headless) for the screenshot:
    C:/Users/<user>/AppData/Local/Google/Chrome/Application/chrome.exe
The template references the background image by filename, which must live in the
same folder as the template (bg_aeonium_1920x1080_source.png).

Renders 1920x1080. Writes the PNG to the path given by --out (defaults to
outro_card.png in this folder). The pipeline picks it up from
channel_dna/aeonium_glow/outro_card.png — pass --out with that path when
regenerating the real card.
"""

import argparse
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "card_template.html")
BG_FILENAME = "bg_aeonium_1920x1080_source.png"  # must match the file in HERE
CHROME_CANDIDATES = [
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_chrome() -> str:
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError(
        "Chrome not found. Set CHROME_PATH or install Chrome. Tried: "
        + ", ".join(CHROME_CANDIDATES)
    )


def render(template: str, out_path: str, replacements: dict) -> str:
    with open(template, "r", encoding="utf-8") as f:
        html = f.read()

    # Resolve the background image to an absolute file:// URL — the generated HTML
    # lives in a temp dir, so a bare relative filename would 404 and the card would
    # render as flat dark (background missing). Callers may pass a bare filename
    # (must exist next to the template) or an absolute path.
    bg_name = replacements.get("BG_FILE", BG_FILENAME)
    bg_path = bg_name if os.path.isabs(bg_name) else os.path.join(HERE, bg_name)
    if not os.path.exists(bg_path):
        raise RuntimeError(f"Background image not found: {bg_path}")
    bg_url = "file:///" + os.path.abspath(bg_path).replace("\\", "/")
    replacements = dict(replacements)
    replacements["BG_FILE"] = bg_url

    for key, value in replacements.items():
        html = html.replace("{{" + key + "}}", value)

    with tempfile.TemporaryDirectory() as tmp:
        html_path = os.path.join(tmp, "card.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        chrome = os.environ.get("CHROME_PATH") or find_chrome()
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            f"--screenshot={out_path}",
            "--window-size=1920,1080",
            "--default-background-color=00000000",
            "file:///" + html_path.replace("\\", "/"),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr[-2000:], file=sys.stderr)
            raise RuntimeError(f"Chrome screenshot failed: {result.returncode}")
        if not os.path.exists(out_path):
            raise RuntimeError("Chrome exited 0 but no screenshot was written")
        return out_path


def main():
    parser = argparse.ArgumentParser(description="Render the Aeonium Glow outro card PNG")
    parser.add_argument("--watch-next-title", default="Stop Succulent Rotting Fast: The First 5 Minutes Matter",
                        help="Full title of the watch-next video; split on first ': ' for accent")
    parser.add_argument("--ask-line1", default="Which number is on")
    parser.add_argument("--ask-line2", default="your")
    parser.add_argument("--ask-line3", default=" windowsill right now?")
    parser.add_argument("--ask-sub", default="Tell me in the comments")
    parser.add_argument("--wn-label", default="Up next — same mistake, opposite direction")
    parser.add_argument("--out", default=os.path.join(HERE, "outro_card.png"),
                        help="Output PNG path (default: outro_card.png in this folder)")
    args = parser.parse_args()

    title = args.watch_next_title
    if ": " in title:
        pre, accent = title.split(": ", 1)
    else:
        pre, accent = title, ""

    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    replacements = {
        "BG_FILE": BG_FILENAME,
        "ASK_LINE1": args.ask_line1,
        "ASK_LINE2": args.ask_line2,
        "ASK_LINE3": args.ask_line3,
        "ASK_SUB": args.ask_sub,
        "WN_LABEL": args.wn_label,
        "WN_TITLE_PRE": pre,
        "WN_TITLE_ACCENT": accent,
    }

    print(f"Rendering outro card -> {out_path}")
    print(f"  ask   : {args.ask_line1} <accent>{args.ask_line2}</accent>{args.ask_line3}")
    print(f"  sub   : {args.ask_sub}")
    print(f"  watch : [{args.wn_label}] {pre} <accent>{accent}</accent>")
    render(TEMPLATE, out_path, replacements)
    print("Done.")


if __name__ == "__main__":
    main()
