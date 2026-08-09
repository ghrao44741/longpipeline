"""
Regression test for stamp_items.py's item-keyed grouping mechanism (Phase 2,
BUILD_BRIEF.md §8b). Tested against SYNTHETIC data first, per the user's explicit
build-order instruction — the mechanism must be proven generic and correct before
any real items.json or real project touches it.

Also covers outro_opening_line (added after the mechanism hit real content on
Etiolation_S1 — its script has a closing "here's the fix" section after the last
item, which without this would have been silently swept into the last item's
group and mislabeled with its item_number/item_name).

No network calls, no API keys required.

Run:  python tests/test_stamp_items.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import stamp_items as si  # noqa: E402

failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + str(detail)}")
    if not cond:
        failures.append(name)


def make_scene(i, script, group_id=None):
    return {"id": f"SCENE-{i:03d}", "script": script, "visual_group_id": group_id}


# ─────────────────────────────────────────────────────────────────────────────
print("\nresolve_boundary_indices: finds each item's opening scene by text prefix")
scenes = [
    make_scene(1, "Welcome back to Aeonium Glow.", "group-01"),
    make_scene(2, "Today we count down ten succulents.", "group-01"),
    make_scene(3, "Number ten is Gasteria.", None),
    make_scene(4, "It tolerates low light better than anything else here.", "group-02"),
    make_scene(5, "That is not the same as liking it.", "group-02"),
    make_scene(6, "Number nine is Aeonium arboreum.", None),
    make_scene(7, "It is naturally tall on woody stems.", None),
]
items = [
    {"rank": 10, "species": "Gasteria", "opening_line": "Number ten is Gasteria."},
    {"rank": 9, "species": "Aeonium arboreum", "opening_line": "Number nine is Aeonium arboreum."},
]
boundaries, outro_index = si.resolve_boundary_indices(scenes, items)
check("no outro_opening_line given -> outro_index is None", outro_index is None, outro_index)
check("item #10 resolves to scene index 2 (SCENE-003)", boundaries[0]["start_index"] == 2, boundaries)
check("item #9 resolves to scene index 5 (SCENE-006)", boundaries[1]["start_index"] == 5, boundaries)
check("group_key follows item-NN zero-padded convention",
      boundaries[0]["group_key"] == "item-10" and boundaries[1]["group_key"] == "item-09", boundaries)

print("\nresolve_boundary_indices: no match raises loudly, not a silent skip")
bad_items = [{"rank": 1, "species": "Nonexistent", "opening_line": "This text is not in any scene."}]
try:
    si.resolve_boundary_indices(scenes, bad_items)
    check("raises ValueError on no match", False, "did not raise")
except ValueError as e:
    check("raises ValueError on no match", True)
    check("error message names the missing item", "Nonexistent" in str(e), str(e))

print("\nresolve_boundary_indices: ambiguous match (matches >1 scene) raises loudly")
ambiguous_scenes = [
    make_scene(1, "The leaves are green."),
    make_scene(2, "The leaves are green and healthy."),
]
ambiguous_items = [{"rank": 1, "species": "X", "opening_line": "The leaves are green"}]
try:
    si.resolve_boundary_indices(ambiguous_scenes, ambiguous_items)
    check("raises ValueError on ambiguous match", False, "did not raise")
except ValueError as e:
    check("raises ValueError on ambiguous match", True)

print("\nresolve_boundary_indices: out-of-order boundaries raise (bad opening_line specificity)")
out_of_order_items = [
    {"rank": 9, "species": "Aeonium arboreum", "opening_line": "Number nine is Aeonium arboreum."},
    {"rank": 10, "species": "Gasteria", "opening_line": "Number ten is Gasteria."},
]
try:
    si.resolve_boundary_indices(scenes, out_of_order_items)
    check("raises ValueError on out-of-order boundaries", False, "did not raise")
except ValueError as e:
    check("raises ValueError on out-of-order boundaries", True)


# ─────────────────────────────────────────────────────────────────────────────
print("\nassign_item_groups: scenes before the first boundary are left untouched")
scenes2 = [
    make_scene(1, "Welcome back to Aeonium Glow.", "group-01"),
    make_scene(2, "Today we count down ten succulents.", "group-01"),
    make_scene(3, "Number ten is Gasteria.", None),
    make_scene(4, "It tolerates low light better than anything else here.", "group-02"),
    make_scene(5, "That is not the same as liking it.", "group-02"),
    make_scene(6, "Number nine is Aeonium arboreum.", None),
    make_scene(7, "It is naturally tall on woody stems.", None),
]
boundaries2, outro_index2 = si.resolve_boundary_indices(scenes2, items)
summary = si.assign_item_groups(scenes2, boundaries2, outro_index2)
check("hook scenes (before item #10) keep their original grouping",
      scenes2[0]["visual_group_id"] == "group-01" and scenes2[1]["visual_group_id"] == "group-01",
      [s["visual_group_id"] for s in scenes2[:2]])

print("\nassign_item_groups: every scene in an item's span shares its group_key")
check("SCENE-003, 004, 005 all share item-10's group_key",
      all(scenes2[i]["visual_group_id"] == "item-10" for i in (2, 3, 4)),
      [s["visual_group_id"] for s in scenes2[2:5]])
check("SCENE-006, 007 (item #9, runs to end of manifest) share item-09's group_key",
      all(scenes2[i]["visual_group_id"] == "item-09" for i in (5, 6)),
      [s["visual_group_id"] for s in scenes2[5:7]])

print("\nassign_item_groups: item_number/item_name stamped ONLY on the opening scene of each item")
check("SCENE-003 (item #10's opening scene) has item_number=10",
      scenes2[2].get("item_number") == 10, scenes2[2])
check("SCENE-004 (item #10's second scene) has NO item_number", "item_number" not in scenes2[3], scenes2[3])
check("SCENE-006 (item #9's opening scene) has item_number=9", scenes2[5].get("item_number") == 9, scenes2[5])
check("SCENE-006's item_name is correct", scenes2[5].get("item_name") == "Aeonium arboreum", scenes2[5])

print("\nassign_item_groups: summary dict reports every group's member scene ids")
check("summary has exactly 2 groups (item-10, item-09)", set(summary.keys()) == {"item-10", "item-09"}, summary)
check("item-10's members are SCENE-003/004/005",
      summary["item-10"] == ["SCENE-003", "SCENE-004", "SCENE-005"], summary)
check("item-09's members are SCENE-006/007",
      summary["item-09"] == ["SCENE-006", "SCENE-007"], summary)

print("\nassign_item_groups: overwrites whatever pre-existing grouping was in an item's span")
check("SCENE-004 and SCENE-005 no longer carry the old 'group-02' id",
      scenes2[3]["visual_group_id"] == "item-10" and scenes2[4]["visual_group_id"] == "item-10")


# ─────────────────────────────────────────────────────────────────────────────
print("\nouter_opening_line: caps the LAST item's span instead of running to end-of-manifest")
scenes3 = [
    make_scene(1, "Number one is Echeveria elegans.", None),
    make_scene(2, "The rosette opens like a flower.", "orig"),
    make_scene(3, "The shape you bought it for is the first thing it loses.", "orig"),
    make_scene(4, "So here is the fix I promised.", "outro-group"),
    make_scene(5, "Increase the light gradually.", "outro-group"),
]
items3 = [{"rank": 1, "species": "Echeveria elegans", "opening_line": "Number one is Echeveria elegans."}]
boundaries3, outro_index3 = si.resolve_boundary_indices(
    scenes3, items3, outro_opening_line="So here is the fix I promised."
)
check("outro_index resolves to scene index 3 (SCENE-004)", outro_index3 == 3, outro_index3)
summary3 = si.assign_item_groups(scenes3, boundaries3, outro_index3)
check("item #1's span stops BEFORE the outro (SCENE-001..003 only)",
      summary3["item-01"] == ["SCENE-001", "SCENE-002", "SCENE-003"], summary3)
check("outro scenes (SCENE-004, SCENE-005) are left untouched, not swept into item-01",
      scenes3[3]["visual_group_id"] == "outro-group" and scenes3[4]["visual_group_id"] == "outro-group",
      [s["visual_group_id"] for s in scenes3[3:]])

print("\nouter_opening_line: omitted -> last item's span still runs to end-of-manifest (unchanged default)")
scenes4 = [make_scene(i, s) for i, s in enumerate([
    "Number one is Echeveria elegans.", "The rosette opens.", "It loses its shape.",
], start=1)]
boundaries4, outro_index4 = si.resolve_boundary_indices(scenes4, items3)
summary4 = si.assign_item_groups(scenes4, boundaries4, outro_index4)
check("all 3 scenes swept into item-01 when no outro_opening_line is given",
      summary4["item-01"] == ["SCENE-001", "SCENE-002", "SCENE-003"], summary4)

print("\nouter_opening_line: resolving at or before the last item's start raises loudly")
try:
    si.resolve_boundary_indices(scenes3, items3, outro_opening_line="Number one is Echeveria elegans.")
    check("raises ValueError when outro resolves no later than the last item", False, "did not raise")
except ValueError as e:
    check("raises ValueError when outro resolves no later than the last item", True)


print("\n" + ("=" * 58))
print(f"FAILED ({len(failures)}): {failures}" if failures else "ALL PASS")
sys.exit(1 if failures else 0)
