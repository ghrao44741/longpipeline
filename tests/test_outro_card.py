"""
Regression test for stitch_video_longform.py's Phase 3 outro-card support
(cta_plan.md "End card"): resolve_outro_card()'s DNA-gating and graceful-missing-
asset behavior. Does NOT test build_outro_card_clip() itself (that's a real
ffmpeg render) — covers the pure-logic resolution path only.

No network calls, no API keys, no ffmpeg required.

Run:  python tests/test_outro_card.py
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stitch_video_longform import resolve_outro_card  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(name)


print("\nresolve_outro_card: disabled in DNA -> (None, None), no warning printed")
config_disabled = {"cta": {"outro_card": {"enabled": False}}}
image, seconds = resolve_outro_card(".", config_disabled)
check("disabled -> (None, None)", (image, seconds) == (None, None), (image, seconds))

print("\nresolve_outro_card: no cta block at all -> (None, None) (narrative-safe default)")
image, seconds = resolve_outro_card(".", {})
check("no cta block -> (None, None)", (image, seconds) == (None, None), (image, seconds))

print("\nresolve_outro_card: enabled but asset doesn't exist yet -> (None, None), not an error")
print("  (Phase 3 built this support before the asset was generated -- must not block)")
with tempfile.TemporaryDirectory() as scripts_dir:
    config_missing_asset = {
        "channel_dna_file": "channel_dna/nonexistent_channel.json",
        "cta": {"outro_card": {"enabled": True, "asset": "outro_card.png", "seconds": 18}},
    }
    image, seconds = resolve_outro_card(scripts_dir, config_missing_asset)
    check("missing asset -> (None, None), no exception raised", (image, seconds) == (None, None), (image, seconds))

print("\nresolve_outro_card: enabled and asset exists -> resolves the path and configured seconds")
with tempfile.TemporaryDirectory() as scripts_dir:
    dna_dir = os.path.join(scripts_dir, "channel_dna")
    assets_dir = os.path.join(dna_dir, "test_channel")
    os.makedirs(assets_dir)
    with open(os.path.join(dna_dir, "test_channel.json"), "w", encoding="utf-8") as f:
        f.write('{"channel_name": "Test"}')
    asset_path = os.path.join(assets_dir, "outro_card.png")
    with open(asset_path, "wb") as f:
        f.write(b"not a real png, just needs to exist")

    config_real_asset = {
        "channel_dna_file": "channel_dna/test_channel.json",
        "cta": {"outro_card": {"enabled": True, "asset": "outro_card.png", "seconds": 12}},
    }
    image, seconds = resolve_outro_card(scripts_dir, config_real_asset)
    check("resolves to the real asset path", image == asset_path, image)
    check("resolves the configured seconds (not the 18s default)", seconds == 12, seconds)

print("\nresolve_outro_card: enabled, asset exists, seconds omitted -> defaults to 18")
with tempfile.TemporaryDirectory() as scripts_dir:
    dna_dir = os.path.join(scripts_dir, "channel_dna")
    assets_dir = os.path.join(dna_dir, "test_channel")
    os.makedirs(assets_dir)
    with open(os.path.join(dna_dir, "test_channel.json"), "w", encoding="utf-8") as f:
        f.write('{"channel_name": "Test"}')
    with open(os.path.join(assets_dir, "outro_card.png"), "wb") as f:
        f.write(b"placeholder")

    config_no_seconds = {
        "channel_dna_file": "channel_dna/test_channel.json",
        "cta": {"outro_card": {"enabled": True, "asset": "outro_card.png"}},
    }
    image, seconds = resolve_outro_card(scripts_dir, config_no_seconds)
    check("defaults to 18s when unspecified", seconds == 18, seconds)


print("\n" + ("=" * 58))
print(f"FAILED ({len(failures)}): {failures}" if failures else "ALL PASS")
sys.exit(1 if failures else 0)
