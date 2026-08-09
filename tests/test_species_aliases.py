"""
Regression test for names_species()/approved_species_list()'s alias support
(Phase 1.5, BUILD_BRIEF_PHASE_1_5.md, per user amendment during subjects expansion —
aliases are a field on the canonical entry, not a duplicate row, and names_species()
must match canonical OR alias, always returning the canonical name).

No network calls, no API keys required.

Run:  python tests/test_species_aliases.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generate_images as gi  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(name)


# ─────────────────────────────────────────────────────────────────────────────
print("\napproved_species_list: alias-bearing entries become (canonical, [aliases]) tuples")
config = {
    "subjects": {
        "Curio rowleyanus": {"common": "String of Pearls", "aliases": ["Senecio rowleyanus"], "visual": "x"},
        "Echeveria elegans": {"common": "Mexican Snowball", "visual": "y"},
    }
}
approved = gi.approved_species_list(config)
check("21-entry-style config: 2 entries returned", len(approved) == 2, approved)
by_canonical = {gi._canonical_name(e): e for e in approved}
check("alias-bearing entry is a tuple", isinstance(by_canonical["Curio rowleyanus"], tuple))
check("no-alias entry stays a bare string", isinstance(by_canonical["Echeveria elegans"], str))

print("\nnames_species: canonical name alone satisfies the match")
result = gi.names_species("A photo of Curio rowleyanus trailing over a pot.", approved)
check("canonical name matches, returns canonical", result == "Curio rowleyanus", result)

print("\nnames_species: ALIAS ALONE (no canonical name in the prompt) satisfies the match")
result = gi.names_species("A photo of Senecio rowleyanus trailing over a pot.", approved)
check("alias-only prompt matches, and returns the CANONICAL name (not the alias)",
      result == "Curio rowleyanus", result)

print("\nnames_species: a no-alias entry still matches on its own name")
result = gi.names_species("A close-up of Echeveria elegans on a windowsill.", approved)
check("plain entry (no aliases) still matches normally", result == "Echeveria elegans", result)

print("\nnames_species: unrelated prompt matches nothing")
result = gi.names_species("A close-up of a terracotta pot with gritty soil.", approved)
check("no species named -> None", result is None, result)

print("\nEnd-to-end against the REAL channel_dna/aeonium_glow.json (21 subjects)")
from config_loader import load_config  # noqa: E402
real_config = load_config(str(Path(__file__).resolve().parent.parent))
real_approved = gi.approved_species_list(real_config)
check("real DNA file has 21 subjects", len(real_approved) == 21, len(real_approved))

result = gi.names_species("A macro shot of Haworthia fasciata on a shaded shelf.", real_approved)
check("real alias 'Haworthia fasciata' resolves to canonical 'Haworthiopsis fasciata'",
      result == "Haworthiopsis fasciata", result)

result = gi.names_species("A macro shot of Haworthiopsis fasciata on a shaded shelf.", real_approved)
check("real canonical 'Haworthiopsis fasciata' also matches directly", result == "Haworthiopsis fasciata", result)

result = gi.names_species("Senecio rowleyanus cascading from a hanging pot.", real_approved)
check("real alias 'Senecio rowleyanus' resolves to canonical 'Curio rowleyanus'",
      result == "Curio rowleyanus", result)

print("\n" + ("=" * 58))
print(f"FAILED ({len(failures)}): {failures}" if failures else "ALL PASS")
sys.exit(1 if failures else 0)
