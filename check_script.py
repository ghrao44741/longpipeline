"""
check_script.py — AeoniumGlow Long-form Pipeline

Pre-voiceover validation for a project's script.txt. Catches two mechanical bug classes
found in production (2026-08-15, Gravel_S1) that a human read-through does not reliably
catch because the *text* reads fine either way -- both are formatting-level, not content-
level, defects:

1. Mid-sentence line wraps. `edge-tts --file` treats ANY newline in the input as a
   pause-insertion point (~1.1s of dead air), including ones that land mid-sentence purely
   from human-readable word-wrapping (e.g. copying prose out of a ~90-char-wrapped
   markdown doc). Confirmed directly: "The person who\npotted it was being careful."
   rendered with a genuine 1.08s silence between "who" and "potted"; the same text on one
   line rendered with none, 1.2s shorter. Etiolation_S1's script.txt happens to have zero
   mid-sentence wraps (whichever way it was authored, it avoided this by accident, not by
   any check); Gravel_S1's had 77, accounting for ~90s of pure dead air across the finished
   narration before this checker existed -- the actual root cause behind a real "the video
   feels like it's pausing" complaint that CLIP_EXTRA tuning would not have fixed, because
   the pause is baked into the narration audio itself, upstream of every downstream stage.
   See CLAUDE.md's BACKLOG entry (2026-08-15) for the full root-cause writeup.

2. Forbidden spoken-text symbols -- the pipeline's own documented constraint ("no
   markdown/parentheses/symbols in the spoken text"), previously enforced only by a human
   noticing on read-through. Em/en dashes, semicolons, and colons are auto-fixed to a plain
   sentence break (matching how they were fixed by hand this same session); markdown
   characters and brackets/parentheses are flagged only, never auto-fixed, since the right
   fix depends on what's inside them.

Usage:
    python check_script.py --project Gravel_S1              # report only, exit 1 if issues found
    python check_script.py --project Gravel_S1 --fix         # report + auto-fix in place (backs up original)

Wired into run_pipeline.py's voiceover step -- a script with unresolved issues fails loud
before edge-tts ever runs, rather than silently shipping another ~90s of dead air.
"""
import argparse
import os
import re
import shutil
import sys

from console_encoding import ensure_utf8_console

ensure_utf8_console()

SENTENCE_END = (".", "?", "!")

# Auto-fixable inline symbols -> sentence break. Order doesn't matter, none overlap.
SYMBOL_AUTOFIX = {
    "—": ". ",
    "–": ". ",
    ";": ". ",
    ":": ". ",
}

# Markdown / bracket characters -- flagged only, never auto-fixed (context-dependent).
FLAG_ONLY_PATTERN = re.compile(r"[*_#`\[\]{}()]")


def find_mid_sentence_wraps(text: str) -> list:
    """
    A line that doesn't end in sentence-ending punctuation, immediately followed by
    another non-blank line, is a wrap WITHIN a paragraph -- exactly what edge-tts turns
    into an unwanted mid-sentence pause. A line ending mid-word right before a blank line
    (a real paragraph break) is not flagged -- that pause is correct and intentional.
    """
    lines = text.split("\n")
    hits = []
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if stripped and not stripped.endswith(SENTENCE_END):
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if nxt:
                hits.append((i + 1, stripped[-50:]))
    return hits


def find_forbidden_symbols(text: str) -> list:
    hits = []
    for i, line in enumerate(text.split("\n"), start=1):
        for ch in SYMBOL_AUTOFIX:
            if ch in line:
                hits.append((i, ch, line.strip()[:70]))
        m = FLAG_ONLY_PATTERN.search(line)
        if m:
            hits.append((i, m.group(0), line.strip()[:70]))
    return hits


def fix_mid_sentence_wraps(text: str) -> str:
    """Join every paragraph into a single line; blank lines between paragraphs are kept."""
    paragraphs = text.split("\n\n")
    fixed = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        joined = " ".join(p.split("\n"))
        joined = " ".join(joined.split())  # collapse incidental double spaces
        fixed.append(joined)
    return "\n\n".join(fixed) + "\n"


def fix_symbols(text: str) -> str:
    for ch, repl in SYMBOL_AUTOFIX.items():
        text = text.replace(ch, repl)
    text = re.sub(r"\.\s*\.", ".", text)  # collapse ". ." from adjacent replacements
    text = re.sub(r" {2,}", " ", text)    # collapse doubled spaces left by a substitution
    # Best-effort re-capitalize the word right after a break we just inserted.
    text = re.sub(r"(\.\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    return text


def main():
    ap = argparse.ArgumentParser(
        description="Pre-voiceover script.txt validator for the long-form pipeline"
    )
    ap.add_argument("--project", required=True, help="Project folder (e.g. Gravel_S1)")
    ap.add_argument(
        "--fix", action="store_true",
        help="Apply auto-fixes in place (backs up original to script.txt.pre_check_backup)"
    )
    args = ap.parse_args()

    script_path = os.path.join(args.project, "script.txt")
    if not os.path.exists(script_path):
        print(f"❌ script.txt not found: {script_path}")
        sys.exit(1)

    text = open(script_path, encoding="utf-8").read()

    wraps = find_mid_sentence_wraps(text)
    symbols = find_forbidden_symbols(text)

    print(f"Checking {script_path}")
    print(f"  Mid-sentence line wraps : {len(wraps)}")
    for ln, tail in wraps[:10]:
        print(f"    line {ln}: ...{tail}")
    if len(wraps) > 10:
        print(f"    ...and {len(wraps) - 10} more")

    print(f"  Forbidden symbols       : {len(symbols)}")
    for ln, ch, context in symbols[:10]:
        print(f"    line {ln} [{ch!r}]: {context}")
    if len(symbols) > 10:
        print(f"    ...and {len(symbols) - 10} more")

    if not wraps and not symbols:
        print("✅ Clean — no mid-sentence wraps, no forbidden symbols.")
        return

    if not args.fix:
        print("\n❌ Issues found. Run with --fix to auto-correct wraps and dash/semicolon/colon")
        print("   symbols. Bracket/asterisk/markdown-style symbols are flagged only — fix by hand.")
        sys.exit(1)

    backup_path = script_path + ".pre_check_backup"
    shutil.copy2(script_path, backup_path)
    print(f"\nBacked up original to {backup_path}")

    fixed = fix_mid_sentence_wraps(text)
    fixed = fix_symbols(fixed)
    open(script_path, "w", encoding="utf-8").write(fixed)
    print("✅ Fixed wraps and dash/semicolon/colon symbols in place.")

    remaining = find_forbidden_symbols(fixed)
    remaining_flagged = [r for r in remaining if r[1] not in SYMBOL_AUTOFIX]
    if remaining_flagged:
        print(f"⚠️  {len(remaining_flagged)} symbol(s) still need manual review (markdown/brackets):")
        for ln, ch, context in remaining_flagged[:10]:
            print(f"    line {ln} [{ch!r}]: {context}")
        sys.exit(1)


if __name__ == "__main__":
    main()
