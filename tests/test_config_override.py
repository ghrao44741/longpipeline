"""
Regression test for config_loader.load_config()'s optional project-level
override layer (added 2026-08-06 for Etiolation_S1's item_overlay_enabled —
several config keys' doc comments claimed a per-project override existed
before this, but it didn't; this is that layer, built when it was actually
needed).

Priority order: project config_override.json > channel_dna > pipeline_config.json.

No network calls, no API keys required.

Run:  python tests/test_config_override.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config_loader import load_config  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(name)


with tempfile.TemporaryDirectory() as tmp:
    scripts_dir = os.path.join(tmp, "scripts")
    dna_dir = os.path.join(scripts_dir, "channel_dna")
    project_dir = os.path.join(tmp, "MyProject")
    os.makedirs(scripts_dir)
    os.makedirs(dna_dir)
    os.makedirs(project_dir)

    with open(os.path.join(scripts_dir, "pipeline_config.json"), "w", encoding="utf-8") as f:
        json.dump({
            "channel_dna_file": "channel_dna/test_channel.json",
            "item_overlay_enabled": False,
            "base_only_key": "from_base",
        }, f)

    with open(os.path.join(dna_dir, "test_channel.json"), "w", encoding="utf-8") as f:
        json.dump({
            "dna_only_key": "from_dna",
            "item_overlay_enabled": False,  # DNA doesn't override this either, base case
        }, f)

    print("\nload_config: no project_dir -> unaffected (existing callers, backward compatible)")
    cfg = load_config(scripts_dir)
    check("base_only_key present", cfg.get("base_only_key") == "from_base")
    check("dna_only_key present (DNA merged over base)", cfg.get("dna_only_key") == "from_dna")
    check("item_overlay_enabled is False (no override layer consulted)",
          cfg.get("item_overlay_enabled") is False)

    print("\nload_config: project_dir given but no config_override.json -> same as above")
    cfg = load_config(scripts_dir, project_dir)
    check("still resolves normally with no override file present",
          cfg.get("item_overlay_enabled") is False)

    print("\nload_config: project config_override.json wins over base AND DNA")
    with open(os.path.join(project_dir, "config_override.json"), "w", encoding="utf-8") as f:
        json.dump({"item_overlay_enabled": True, "project_only_key": "from_project"}, f)

    cfg = load_config(scripts_dir, project_dir)
    check("item_overlay_enabled flipped to True by project override",
          cfg.get("item_overlay_enabled") is True, cfg.get("item_overlay_enabled"))
    check("project_only_key present", cfg.get("project_only_key") == "from_project")
    check("base_only_key still present (override is additive, not a replacement)",
          cfg.get("base_only_key") == "from_base")
    check("dna_only_key still present", cfg.get("dna_only_key") == "from_dna")


print("\n" + ("=" * 58))
print(f"FAILED ({len(failures)}): {failures}" if failures else "ALL PASS")
sys.exit(1 if failures else 0)
