"""
stamp_items.py — longform_pipeline, listicle mode (Phase 2)

Re-groups a manifest's scenes by ITEM instead of by WhisperX sentence-adjacency
(auto_split_scenes.py's default grouping, inherited from the narrative path).

Why this exists: at the narrative path's default grouping, a 10-item, ~12-minute
listicle measures ~9.5 images/minute (Phase 1's WhisperX-at-scale test) — 110-120
images. Nobody reviews 110 prompts, so the human --dry-run-prompts checkpoint that
caught the swapped species, the kiwi cross-section, and the diagram overlays in
earlier phases quietly stops working at exactly the format where it matters most.
For a listicle the natural visual unit is the ITEM, not the sentence: one or two
images held with Ken Burns across all of that item's scenes. 10 items -> 10-20
images, not 110 — cheaper AND reviewable, which is the actual point.

Run this AFTER the scenes stage (needs manifest.json with scenes already
WhisperX-split) and BEFORE the images stage (generate_images.py's shot-building
already reads scene["visual_group_id"] generically — this script is the only
thing that needs to change for grouping to become item-keyed; nothing in
generate_images.py or auto_split_scenes.py needs editing).

Per BUILD_BRIEF.md §8: this is one of the only two places the listicle format is
allowed to touch outside the script stage (manifest stamping, and one optional
ffmpeg filter for the overlay) — everything else in the pipeline is identical
between narrative and listicle.

items.json schema (BUILD_BRIEF.md §8b), plus one field this script adds:
    { "rank": 10, "species": "Gasteria", "trade_name": null, "common": "Ox Tongue",
      "tier": "...", "twist": "...", "source_ref": "...",
      "opening_line": "Number ten is Gasteria." }
"rank" is used as the on-screen item number (also the group-key suffix);
"species" is used as the on-screen item name AND stamped onto the opening scene
for listicle-mode species-validation authority (BUILD_BRIEF.md §8a.2 — not wired
into generate_images.py's validator yet, tracked separately). "opening_line" is
the only field this script actually needs — it doesn't exist until script.txt is
real, so items.json's content fields can be authored from the source doc well
before the opening_line matching pass runs for real.

Optional top-level field, sibling to "items": "outro_opening_line" — the verbatim
opening of a closing/"here's the fix" section that comes AFTER the last item.
Without it, the last item's span silently runs through end-of-manifest, so any
such trailing content gets swept into (and mislabeled as) the last item's group
— caught for real on Etiolation_S1 (BUILD_BRIEF.md §8b implementation notes),
whose script has a general fix section after item #1. Symmetric with how
pre-item hook scenes are already left untouched: content after outro_opening_line
is left at its original (sentence-level) grouping too, not swept into any item.
Omit it for a script whose last item's content genuinely runs to the end.

Usage:
    python stamp_items.py --project {Project} --items items.json
"""

import argparse
import json
import os
import sys

from console_encoding import ensure_utf8_console
ensure_utf8_console()


def resolve_boundary_indices(scenes: list, items: list, outro_opening_line: str = None) -> tuple:
    """
    For each item (in narration order, each with an "opening_line" — a verbatim
    prefix of that item's first sentence in script.txt), find the first scene
    whose script text starts with it (case-insensitive, whitespace-normalized).

    Returns (boundaries, outro_index):
      boundaries  — list of dicts {"group_key", "rank", "species",
                    "start_index"}, one per item, in the same order as `items`.
      outro_index — scene index where non-item trailing content starts (the
                    "fix"/outro section after the last item), or None if
                    outro_opening_line wasn't given. Resolved the same way as
                    an item's opening_line, but is NOT itself a group — see
                    assign_item_groups().

    Fails loudly (raises ValueError) on a missing match rather than silently
    skipping an item — a missed match would misgroup every scene from that point
    forward, exactly the kind of silent failure this whole mechanism exists to
    prevent for the species/prompt checks. Also fails loudly on an ambiguous
    match (the same opening_line prefix matching more than one scene), since
    that means the opening_line wasn't a specific enough anchor.
    """
    def norm(s):
        return " ".join(s.split()).lower()

    def find_one(needle_text: str, label: str) -> int:
        needle = norm(needle_text)
        matches = [
            i for i, scene in enumerate(scenes)
            if norm(scene.get("script", "")).startswith(needle)
        ]
        if not matches:
            raise ValueError(
                f"No scene found starting with opening_line for {label}: "
                f"{needle_text!r}. Check items.json's opening_line against the "
                f"real script.txt / manifest.json scene text exactly — WhisperX "
                f"transcription or scene splitting may have altered it slightly."
            )
        if len(matches) > 1:
            raise ValueError(
                f"opening_line for {label} matches {len(matches)} scenes "
                f"({[scenes[i]['id'] for i in matches]}) — not a specific enough "
                f"anchor: {needle_text!r}"
            )
        return matches[0]

    boundaries = []
    for item in items:
        label = f"item #{item.get('rank', '?')} ({item.get('species', '?')})"
        start_index = find_one(item["opening_line"], label)
        boundaries.append({
            "group_key": f"item-{item['rank']:02d}" if item.get("rank") is not None else item["group_key"],
            "rank": item.get("rank"),
            "species": item.get("species"),
            "start_index": start_index,
        })

    # Boundaries must be strictly increasing and in narration order — if they
    # aren't, opening_line matching found something out of sequence, which is
    # itself a sign one of the opening_lines is wrong (too short/generic).
    for i in range(1, len(boundaries)):
        if boundaries[i]["start_index"] <= boundaries[i - 1]["start_index"]:
            raise ValueError(
                f"Item boundaries are not in increasing scene order: "
                f"{boundaries[i - 1]['group_key']} starts at scene index "
                f"{boundaries[i - 1]['start_index']}, but {boundaries[i]['group_key']} "
                f"starts at {boundaries[i]['start_index']} — check opening_line "
                f"specificity and item order in items.json."
            )

    outro_index = None
    if outro_opening_line:
        outro_index = find_one(outro_opening_line, "outro_opening_line")
        if boundaries and outro_index <= boundaries[-1]["start_index"]:
            raise ValueError(
                f"outro_opening_line resolves to scene index {outro_index}, at or "
                f"before the last item's start_index {boundaries[-1]['start_index']} "
                f"({boundaries[-1]['group_key']}) — it must come after every item."
            )

    return boundaries, outro_index


def assign_item_groups(scenes: list, boundaries: list, outro_index: int = None) -> dict:
    """
    Mutates scenes in place: for each boundary, every scene from its start_index
    (inclusive) up to the next boundary's start_index (exclusive) — or up to
    outro_index (exclusive) if given, or the end of the manifest otherwise, for
    the LAST boundary — gets scene["visual_group_id"] set to that boundary's
    group_key, OVERWRITING whatever auto_split_scenes.py's sentence-adjacency
    grouping originally set. "item_number"/"item_name" are stamped only onto
    each boundary's OPENING scene (per BUILD_BRIEF.md §8b) — field names kept
    as item_number/item_name on the manifest scene itself (distinct from
    items.json's rank/species) since that's what a future numbered-overlay/
    chapter-generation consumer will look for on a scene.

    Scenes BEFORE the first boundary (e.g. a hook/intro) and AT-OR-AFTER
    outro_index (e.g. a closing "here's the fix" section that isn't about any
    single item) are left untouched, symmetrically — item-keyed grouping
    applies to the item spans specifically, not the whole video. Without
    outro_index, the last item's span silently swallows any trailing content
    through end-of-manifest; a script with a real outro after its countdown
    needs outro_opening_line set in items.json to avoid that.

    Returns a summary dict for reporting: {group_key: [scene_ids]}.
    """
    summary = {}
    for i, boundary in enumerate(boundaries):
        start = boundary["start_index"]
        if i + 1 < len(boundaries):
            end = boundaries[i + 1]["start_index"]
        elif outro_index is not None:
            end = outro_index
        else:
            end = len(scenes)
        member_ids = []
        for idx in range(start, end):
            scenes[idx]["visual_group_id"] = boundary["group_key"]
            member_ids.append(scenes[idx]["id"])
        if boundary.get("rank") is not None:
            scenes[start]["item_number"] = boundary["rank"]
            scenes[start]["item_name"] = boundary["species"]
        summary[boundary["group_key"]] = member_ids
    return summary


def stamp_items(project_dir: str, items_path: str):
    manifest_path = os.path.join(project_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    with open(items_path, "r", encoding="utf-8") as f:
        items_data = json.load(f)

    scenes = manifest["scenes"]
    items = items_data["items"]
    outro_opening_line = items_data.get("outro_opening_line")

    print(f"Resolving {len(items)} item boundaries against {len(scenes)} scenes...")
    boundaries, outro_index = resolve_boundary_indices(scenes, items, outro_opening_line)
    for b in boundaries:
        label = f"#{b['rank']} {b['species']}" if b.get("rank") is not None else b["group_key"]
        print(f"  {b['group_key']:12s}  starts at scene index {b['start_index']:3d} "
              f"({scenes[b['start_index']]['id']})  -- {label}")
    if outro_index is not None:
        print(f"  {'(outro)':12s}  starts at scene index {outro_index:3d} "
              f"({scenes[outro_index]['id']})  -- trailing content, left ungrouped by item")

    summary = assign_item_groups(scenes, boundaries, outro_index)

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Re-grouped {len(scenes)} scenes into {len(summary)} item-keyed group(s)")
    if outro_index is not None:
        print(f"   (plus pre-item hook scenes and the post-item outro, both left at their original grouping)")
    else:
        print(f"   (plus any pre-item hook scenes, left at their original grouping)")
    for group_key, member_ids in summary.items():
        print(f"   {group_key}: {len(member_ids)} scene(s) -> {member_ids}")
    print(f"\n✅ Manifest updated: {manifest_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-group manifest scenes by item for listicle mode")
    parser.add_argument("--project", required=True, help="Project folder (e.g. Etiolation_S1)")
    parser.add_argument("--items", required=True, help="Path to items.json (absolute, or relative to project dir)")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = (
        args.project if os.path.isabs(args.project)
        else os.path.join(script_dir, args.project)
    )
    if not os.path.isdir(project_dir):
        print(f"❌ Project folder not found: {project_dir}")
        sys.exit(1)

    items_path = (
        args.items if os.path.isabs(args.items)
        else os.path.join(project_dir, args.items)
    )
    if not os.path.exists(items_path):
        print(f"❌ items.json not found: {items_path}")
        sys.exit(1)

    stamp_items(project_dir, items_path)
