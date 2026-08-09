"""
Regression test for run_pipeline.py's --start-from script fail-loud guard
(2026-08-08 correction). generate_script.py is a near-unmodified Shorts copy
(65-75s / 140-165 word defaults) that PRODUCTION_RUNBOOK.md has always warned
against using for long-form, but nothing enforced that -- and "script" is also
--start-from's own DEFAULT, so simply omitting the flag silently ran it. This
test runs the real script as a subprocess (the guard fires before any real
work happens, so this is fast and side-effect-free) and asserts it exits
non-zero with a message pointing at the real supported path.

No network calls, no API keys, no real project needed (the guard fires before
the project directory is ever touched).

Run:  python tests/test_start_from_script_guard.py
"""

import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent / "run_pipeline.py")

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(name)


def run(args):
    # run_pipeline.py reconfigures its own stdout/stderr to UTF-8 (to survive its emoji
    # status glyphs on Windows' cp1252 default console) -- decode the captured output the
    # same way, or a UTF-8-encoded byte sequence fails to decode under the parent's own
    # default locale.
    return subprocess.run([sys.executable, SCRIPT] + args, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")


print("\n--start-from script (explicit): fails loudly, points at the real path")
result = run(["--project", "NoSuchProject", "--start-from", "script"])
check("non-zero exit", result.returncode != 0, result.returncode)
check("message names generate_script.py's Shorts-shape problem",
      "Shorts" in result.stdout, result.stdout)
check("message points at pipeline_script_prompt_template.md",
      "pipeline_script_prompt_template.md" in result.stdout, result.stdout)
check("message points at the --start-from voiceover path",
      "--start-from voiceover" in result.stdout, result.stdout)

print("\n--start-from omitted entirely: hits the same guard via the default, not silently skipped")
result = run(["--project", "NoSuchProject"])
check("non-zero exit on the implicit default too", result.returncode != 0, result.returncode)
check("same guard message fires", "Shorts" in result.stdout, result.stdout)

print("\n--start-from voiceover: does NOT trigger the guard (only 'script' should)")
result = run(["--project", "NoSuchProject", "--start-from", "voiceover"])
check("guard message does not appear for a different start-from value",
      "not supported for long-form" not in result.stdout, result.stdout)


print("\n" + ("=" * 58))
print(f"FAILED ({len(failures)}): {failures}" if failures else "ALL PASS")
sys.exit(1 if failures else 0)
