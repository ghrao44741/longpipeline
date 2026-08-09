"""
Regression test for config_loader.py's guard against a nested "cta" object in a
per-project config_override.json (Phase 3, cta_plan.md "Where this lives").

Without this guard, load_config()'s shallow merge would silently REPLACE
channel_dna's entire "cta" block (ask pattern, outro card, subscribe line) with
whatever partial dict a project override happens to contain, no error — the same
silent-substitution shape as three earlier bugs this project already hit.

No network calls, no API keys required.

Run:  python tests/test_config_cta_guard.py
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


scripts_dir = os.path.abspath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("\nload_config: a nested 'cta' object in a project override raises, not silently merges")
with tempfile.TemporaryDirectory() as tmp:
    with open(os.path.join(tmp, "config_override.json"), "w", encoding="utf-8") as f:
        json.dump({"cta": {"outro_card": {"enabled": False}}}, f)
    try:
        load_config(scripts_dir, tmp)
        check("raises ValueError on nested cta override", False, "did not raise")
    except ValueError as e:
        check("raises ValueError on nested cta override", True)
        check("error message names the flat-key convention", "cta_" in str(e), str(e))

print("\nload_config: flat cta_* keys in a project override merge in fine, no exception")
with tempfile.TemporaryDirectory() as tmp:
    with open(os.path.join(tmp, "config_override.json"), "w", encoding="utf-8") as f:
        json.dump({"cta_watch_next_title": "Some Video", "cta_watch_next_id": "abc123"}, f)
    try:
        config = load_config(scripts_dir, tmp)
        check("no exception for flat cta_* keys", True)
        check("flat key actually merged in", config.get("cta_watch_next_title") == "Some Video", config.get("cta_watch_next_title"))
    except ValueError as e:
        check("no exception for flat cta_* keys", False, str(e))

print("\nload_config: a project override with no cta-related keys at all still works (no regression)")
with tempfile.TemporaryDirectory() as tmp:
    with open(os.path.join(tmp, "config_override.json"), "w", encoding="utf-8") as f:
        json.dump({"item_overlay_enabled": True}, f)
    try:
        config = load_config(scripts_dir, tmp)
        check("no exception, unrelated override still merges", config.get("item_overlay_enabled") is True)
    except ValueError as e:
        check("no exception, unrelated override still merges", False, str(e))

print("\nload_config: no project_dir at all -- unaffected (existing callers)")
try:
    config = load_config(scripts_dir)
    check("no exception when project_dir is omitted", True)
except ValueError as e:
    check("no exception when project_dir is omitted", False, str(e))

print("\nload_config: channel_dna's own nested 'cta' block (not a project override) passes through untouched")
config = load_config(scripts_dir)
check("DNA's cta block is present and is a dict (guard only applies to project overrides)",
      isinstance(config.get("cta"), dict), config.get("cta"))


print("\n" + ("=" * 58))
print(f"FAILED ({len(failures)}): {failures}" if failures else "ALL PASS")
sys.exit(1 if failures else 0)
