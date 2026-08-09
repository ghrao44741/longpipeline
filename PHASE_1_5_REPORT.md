# Phase 1.5 Report — channel_dna Layer-2 extraction + subject expansion

**Status: complete through BUILD_BRIEF_PHASE_1_5.md §6**, including the §6.7 portability smoke
test. Reported here before its throwaway artifacts are deleted, per instruction.

---

## Part 1 — Blocking fixes

### 1. WhisperX flags now actually reach `auto_split_scenes.py`

Confirmed by reading `run_pipeline.py`'s `run_scenes()` directly: it never passed
`--compute-type`/`--batch-size` at all, despite Phase 1 adding those flags to
`auto_split_scenes.py`. Every real long-form run would have OOM'd exactly like the first §C
attempt in Phase 1.

Fixed: `pipeline_config.json` now carries `whisper_compute_type: "float16"` and
`whisper_batch_size: 4` (machine settings, not `channel_dna`), and `run_scenes()` passes both
through when set. `shorts_pipeline2` untouched.

**Caveat recorded in config and here, not silently assumed solved:** `batch_size: 4` is proven
only at 5.7 minutes (Phase 1's test). Real listicles run 10-15 minutes — 2-3× that. If a real
production run OOMs again, lowering this further is the expected next step, not a new bug.
Also recorded precisely which stage OOM'd originally: **transcription**
(`whisperx/asr.py`'s `generate_segment_batched()` → `encode()`), not forced alignment.
Alignment ran clean afterward in the successful retry but wasn't independently stress-tested
as a separate pressure point at greater length — flagged as unverified, not proven safe.

### 2. Last-scene frame check

`Longform_Test_Misting`'s last scene (SCENE-025, video-space window 134.01-139.26s) checked at
t=136.5s against the already-fixed captioned video (no re-stitch needed). The full caption
("Misting in the morning, which is when most people do it, is spraying water onto closed
pores.") matched its own correct visual (a misting spray over the succulent) exactly — this is
the point of maximum accumulated pre-fix drift in the test video, and the remap held.

### 3. `BUILD_BRIEF.md` §10 cost estimate corrected

Old estimate: "~15 items × 2-3 scenes = 30-45 images per video." Measured reality from Phase
1's §C run: 54 shots over 341s (5.7 min) of real narration — **~9.5 images/minute**. A real
10-15 minute listicle is therefore **~95-140 images**, a 3-4× correction. Noted that shot
grouping (`visual_group_id`) is a real cost lever at this scale (it already reduced 65 raw
scenes to 54 billable shots in that test), not redesigned here — that's Phase 2's job.

---

## Part 2 — The extraction

### Golden-output test — the whole ballgame, run first and run twice more

Captured baseline stdout from `validate_and_fix_shots()` (imported from **this pipeline's own**
`generate_images.py`, per instruction — not Shorts' copy) over all 12 available real
`prompts_review.json` corpus files (`Misting_S1/S2/S3_yt`, `Myths_S1/S2/S3_yt`,
`Propagation_S1_yt/S2_ig/S3_yt`, `Wrinkled_Leaves_S1/S2/S3_yt`), with `regenerate_fn` stubbed
to a deterministic no-op. Harness: `tests/golden_output_test.py`.

- **After the rule extraction (§1-§4 of the brief): byte-for-byte identical**, all 12 projects.
- **After the subjects expansion (9 → 21 entries): still byte-for-byte identical**, all 12
  projects — expected and unsurprising, since none of the corpus prompts reference any of the
  12 newly-added species names, so the species-flagging outcome couldn't change for this
  specific corpus. Not a weak test — a mis-escaped regex in the *rule* extraction would still
  have shown up here regardless of the subjects change, since detection logic and species data
  are independent code paths.

### Correction found before starting: the `approved_species` → `subjects` rename was already done

The brief's own §1g assumed only the DNA *data* had been renamed in Phase 1, with the *readers*
still needing updating in this phase. Verified before touching anything: `approved_species_list()`
already read `config.get("subjects", {})`, and zero `config.get("approved_species"...)` call
sites remained anywhere in the file. Phase 1's channel_dna-seam work had already done the full
rename. No rename work was needed here — only the five other inventory items moved:
`KNOWN_SETTING_KEYWORDS`, `PLANT_REFERENCE_PATTERN`, `ACTION_CHECKS`, `REVERSAL_CHECKS`,
`HALLUCINATION_CHECKS`, now living in `channel_dna/aeonium_glow.json`'s `"validation"` block.
The rule *engine* (retry loop, `max(2, ceil(total/3))` overuse threshold, matching algorithms)
stays in code, unchanged, per the brief's §2.

### Retry guidance is now targeted, not a kitchen-sink blob

`fix_note` — the text sent back to the model on a violating retry — previously always included
every domain instruction regardless of which rule actually fired. Now composed from only the
`guidance` of rules that fired, plus the subject-independent variety instruction that stays in
code. Verified directly (not just inferred from the golden test, which only captures stdout,
not `fix_note`):
- An isolated nocturnal-lighting violation produces **only** that rule's guidance string — confirmed exact string match, nothing else present.
- A prompt that legitimately triggers two independent rules (dehydration-reversal +
  invented-watering) correctly includes both guidances and excludes the two that didn't fire
  (pest-disease, action-check).

**Four rules are not exercised by the 12-project golden corpus at all: `dehydration-vs-watering`,
`nocturnal-lighting`, `watering-in-progress` (action-mismatch), and setting-overuse.** None of
these strings appear anywhere in `tests/golden_baseline.json`. All four were directly
constructed and confirmed firing correctly (dehydration and nocturnal via the targeted-guidance
tests above; action-mismatch and setting-overuse via separate direct construction) — but this
is a real, standing coverage gap in the corpus itself, not just a historical footnote.
**Recorded explicitly so future changes don't over-trust a byte-identical golden-test result
for these four**: identity is trivially satisfied when a rule never fires in either run. A
regex regression in any of these four would pass the golden test silently. If the corpus ever
gains a project exercising them, that closes the gap for real; until then, treat these four as
requiring the same direct-construction check this phase used, not just the golden diff.

### Subjects expanded 9 → 21, with a structural change beyond the original brief

Backed by a channel-strategy demand-research doc (`succulent_demand_and_subjects.md`) read in
full per instruction, not just the soil-drainage source doc's ranked list. Final list, shown to
and approved by the user before writing, adds 12 new entries (`Sempervivum tectorum`,
`Portulacaria afra`, `Gasteria` [genus-level], `Aloe vera`, `Kalanchoe tomentosa`,
`Kalanchoe blossfeldiana`, plain `Sedum rubrotinctum`, `Lithops` [genus-level],
`Curio rowleyanus`, plain `Aeonium arboreum`, `Haworthia cooperi`, `Ceropegia woodii`) and
restructures the existing `Haworthia fasciata` entry into `Haworthiopsis fasciata` (its current
correct name) with an alias. **Not a padded count** — every entry traces to either the
soil-drainage doc's ranked list or the demand doc's explicit justification (highest-measured-
demand for `Ceropegia woodii`, distinct visual for `Haworthia cooperi`, named explicitly in the
already-produced rot-rescue video for plain `Aeonium arboreum`).

**Structural change, per explicit user amendment mid-phase:** aliases are a field on the
canonical entry (`"aliases": [...]`), never a duplicate dict key — two rows for one plant would
break anything treating `subjects` as a set of distinct species. `names_species()` was extended
to match on canonical name OR any alias, always returning the canonical name regardless of
which one matched — so downstream code never sees two different strings for one plant.
`approved_species_list()` now returns a mix of bare name strings (no-alias entries) and
`(canonical, [aliases])` tuples; `_canonical_name()` extracts the display name from either shape.

New test file `tests/test_species_aliases.py` (11 checks, all passing) covers: alias-bearing
entries becoming tuples, canonical-name-alone matching, alias-alone matching (and returning the
canonical name, not the alias), a no-alias entry still matching normally, an unrelated prompt
matching nothing, and two real end-to-end checks against the actual 21-entry DNA file
(`Haworthia fasciata` → resolves to `Haworthiopsis fasciata`; `Senecio rowleyanus` → resolves to
`Curio rowleyanus`).

**A source-doc inconsistency was found and separately resolved.** The soil-drainage source
doc's naming note originally listed *Dracaena trifasciata* (Snake Plant) as one of "three
reclassified species," despite the same document explicitly excluding Snake Plant from the
channel by scope twenty lines earlier — a real self-contradiction, not a quirk, since that
section feeds script generation directly. Flagged during this phase; the user corrected the
source doc directly (now reads "two species," Snake Plant removed). Confirmed Snake Plant is
not and was never added to `subjects`.

### Lints

Regex compile lint: all 13 patterns in the `validation` block (1 subject-reference, 1
action-check ×2 sub-patterns, 3 reversal-checks ×2, 2 hallucination-checks ×2) compile cleanly.
Schema lint: `subjects` non-empty (21), every subject has a `visual`, `setting_vocabulary`
non-empty (18 keywords), every check has both an `id` and a non-empty `guidance`, no duplicate
ids. All pass.

### Blast-radius grep

Grepped the entire `Aeonium_Glow` tree for `names_species`, `approved_species_list`,
`validate_and_fix_shots`, `PLANT_REFERENCE_PATTERN`, `approved_species`. Nine files matched;
every real consumer confirmed:
- `longform_pipeline/generate_images.py` — the file being modified. Tested directly throughout.
- `longform_pipeline/generate_override_prompts.py` — calls `validate_and_fix_shots()` with its
  own `regenerate_fn`; external signature unchanged, confirmed the exact inline-import pattern
  it uses (`from generate_images import validate_and_fix_shots, load_brand_brief`) still
  resolves cleanly. No code change needed there.
- `longform_pipeline/tests/*.py` — this phase's own new/updated test files, all passing.
- `shorts_pipeline2/.claude/skills/produce-short/scripts/audit_prompts.py` — imports
  `generate_images` from whatever `--pipeline-root` is passed. Confirmed via the skill's own
  `SKILL.md` that every invocation uses `--pipeline-root .`, run from within `shorts_pipeline2/`
  sessions — so in actual practice it only ever imports **Shorts'** own, completely untouched
  `generate_images.py`. Zero practical risk, confirmed rather than assumed.
- `shorts_pipeline2/generate_images.py`, `shorts_pipeline2/generate_override_prompts.py`,
  `shorts_pipeline2/tests/test_generate_images.py` — Shorts' own separate copies, never touched
  by this phase.

### End-to-end re-check

Re-ran `--dry-run-prompts` against `Longform_Test_Misting` (Phase 1's real narrative test
project). Output character consistent with Phase 1's original run — correct `16:9 widescreen`
phrasing throughout, correct species naming, consistent style. No image spend.

### §6.7 Portability smoke test — the actual point of this phase

Built a deliberately unrelated throwaway subject (pocket/outdoor knives) end-to-end:
`channel_dna/_throwaway_portability_test.json` (3 subjects, its own `image_style_template`, and
a full `validation` block with a knife-domain `subject_reference_pattern` and
`setting_vocabulary` — built complete, not relying on any hardcoded fallback in code, since a
silent fallback to a succulent-specific default would have been exactly the kind of incomplete
extraction this test exists to catch), plus a hand-written 3-scene `manifest.json` in a scratch
project (`_portability_test_knives/`, no voiceover/WhisperX needed for a prompts-only test).

Temporarily pointed `pipeline_config.json`'s `channel_dna_file` at the throwaway, ran
`generate_images.py --dry-run-prompts` for real (a real OpenAI call, no image spend), then
restored the pointer immediately and verified restoration (`channel_name: AeoniumGlow`,
`subjects: 21`, confirmed via `config_loader.load_config()`).

**Result: clean pass, zero Python edited.** All three generated prompts are genuinely
knife-domain — "drop-point folding knife," "whetstone," "fixed-blade hunting knife," "wooden
workbench" — with zero succulent/plant vocabulary leakage, correct `16:9 widescreen` phrasing
(inherited from the unrelated machine-level config, as designed), and the validator ran clean
(`no variety-rule violations found`).

**This is the honest measure of whether Phase 1.5 achieved its goal, and it did**: producing
the same format about a different subject required writing one DNA file, nothing else — for
prompt *generation*.

### §6.7 follow-up — retry guidance was NOT covered by the first pass, and it leaked

The first portability run passed with zero violations, which meant no `fix_note` was ever
composed and retry guidance was never actually exercised in the second domain — a gap in the
test, not evidence retry guidance was portable. Guidance is prose, not regex, and prose is
exactly where succulent-shaping was most likely to survive.

Closed properly: added one real knife-domain `action_check` (`sharpening-in-progress`) to the
throwaway DNA, constructed a prompt that violates it (narration says honing is in progress;
image shows no stone contact), and inspected the actual composed `fix_note`.

**`fix_note` itself was completely clean** — contained exactly the knife DNA's own guidance
string ("the image MUST show the blade in contact with the whetstone...") and zero succulent
vocabulary.

**But the console diagnostic print line was not.** `validate_and_fix_shots()`'s `reasons` list
— the human-facing "Validation pass N: ... need fixing — {reasons}" summary — has two
hardcoded, succulent-shaped strings that were never part of the five-item extraction inventory
because they're not rule *data*, they're English prose describing categories of violation:
- `generate_images.py:773` — `"narration describes a water/pour/drainage action not shown in
  the image"`, printed for **any** `action_checks` violation regardless of which rule fired.
  On the knife run this printed literally that line for a sharpening violation — wrong on its
  face for that domain.
- `generate_images.py:770` — `"mentions plant material with no real species named"` — "plant
  material"/"species" wording tied to the succulent domain, not exercised by this specific
  test (the knife prompt already named a species) but found while investigating and worth
  recording in the same pass rather than a separate one.

**This was a real, incomplete extraction — reported first, then fixed** (user opted to close it
same-day rather than leave it in backlog, given the ~15-minute size). Both strings moved into
`channel_dna/aeonium_glow.json` as a `label` field alongside each check's existing `guidance` —
`subject_reference_pattern.label` and `action_checks[].label` — read in code via
`subject_ref_cfg.get("label", ...)` and a per-check `label` element in the `ACTION_CHECKS`
tuple, same pattern as the five items already extracted. Verified with a synthetic config
carrying deliberately distinctive custom labels (`CUSTOM-KNIFE-LABEL`, `CUSTOM-ACTION-LABEL`):
both appeared verbatim in the console output, confirming no hardcoded fallback text remains
reachable. Golden test re-run afterward — still byte-identical across all 12 corpus projects
(unsurprising: the DNA labels are worded identically to the strings they replaced, so console
output for the real corpus is unchanged; the synthetic-label test is what actually proves the
values are DNA-sourced rather than hardcoded).

Throwaway artifacts (`channel_dna/_throwaway_portability_test.json`,
`_portability_test_knives/`) have been deleted after this follow-up check, confirmed removed.
`pipeline_config.json`'s `channel_dna_file` confirmed restored to `channel_dna/aeonium_glow.json`
— **note for the record:** it was left pointed at the throwaway file once, mid-follow-up, and
caught only because the next command failed outright (`channel_dna_file not found`) rather than
silently. Restored and reverified (`channel_name: AeoniumGlow`, `subjects: 21`).

---

## Files changed

- `longform_pipeline/generate_images.py` — extraction, targeted retry guidance, alias-aware
  `names_species()`/`approved_species_list()`.
- `longform_pipeline/channel_dna/aeonium_glow.json` — new `"validation"` block; `subjects`
  expanded 9 → 21 with `aliases` fields.
- `longform_pipeline/pipeline_config.json` — `whisper_compute_type`, `whisper_batch_size` added
  (with caveat comment); temporarily repointed and restored during the portability test.
- `longform_pipeline/run_pipeline.py` — `run_scenes()` now passes the WhisperX flags through.
- `longform_pipeline/BUILD_BRIEF.md` — §10 cost estimate corrected.
- `longform_pipeline/tests/golden_output_test.py`, `tests/golden_baseline.json`,
  `tests/test_species_aliases.py` — new.
- Source doc `soil-drainage-species-susceptibility-source-doc.md` — corrected by the user
  directly (Dracaena trifasciata naming-note self-contradiction removed).

`shorts_pipeline2/` untouched throughout this phase.

---

## Explicitly out of scope, not started

Phase 2 (listicle mode), the forced-alignment change (BACKLOG item from Phase 1), fixing
Shorts' own CC-track drift, fontsize tuning, grouping redesign, any upload.
