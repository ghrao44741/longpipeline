# BUILD BRIEF — Phase 1.5: `channel_dna` Layer-2 extraction + subject expansion

**Prerequisite:** Phase 1 complete and verified (core pipeline + narrative format, the
`channel_dna` seam established, `config_loader.py` merging DNA over config).

**Blocks:** Phase 2 (listicle mode). Do this first — Phase 2 adds new domain rules, and they
should land on the correct side of the seam rather than be moved later.

**Goal in one sentence:** make the pipeline subject-portable, so producing the same *format*
about a different *subject* — orchids, bonsai, aquarium plants, espresso gear, knives — is a
matter of writing a new `channel_dna.json`, not editing Python.

---

## 0. SCOPE

**In scope:** lifting the succulent-specific vocabulary still hardcoded in
`generate_images.py` into `channel_dna`, and expanding `subjects` to 30+ entries.

**Out of scope:**
- Genericising the *rule engine*. The check logic — the `evidence_must_be_absent` semantics,
  the retry loop, the `ceil(total/3)` overuse threshold at `:708` — is already
  subject-independent. Do not touch it.
- Any change to `shorts_pipeline2`. Phase 1's one sanctioned edit is done; this phase touches
  only the fork.
- Building a second channel's DNA file. This phase proves the mechanism with one.

**The governing principle:** *generic engine, specific DNA.* If you find yourself adding a
`style_intensity: 0.7`-shaped knob, stop — you have gone past the goal. The DNA file holds
complete, hand-written, opinionated content per channel. It is not a parameterisation of a
shared template.

---

## 1. WHAT MOVES — INVENTORY

All line references are to `generate_images.py` as of 2026-08-05. Verify before editing; Phase
1 may have shifted them.

### 1a. `KNOWN_SETTING_KEYWORDS` — `:554-563`

An **ordered** list of location keywords. Feeds `_extract_setting()` (`:566-581`), which
returns the *first* match — so ordering is load-bearing, and the comment at `:552-553` says so
explicitly.

Two things must survive the move:
- **Order.** JSON arrays preserve it. Document in the DNA file that the list is ordered
  most-specific-first and must not be alphabetised.
- **The `:557-560` comment.** It records that bare forms (`"windowsill"`, `"potting bench"`)
  were added because without them `_extract_setting` returned `""` for nearly every real prompt
  and the overuse check *silently never fired*. That is hard-won knowledge about a bug that
  produced no error. It must not be lost to a format that has no comments — see §3.

### 1b. `PLANT_REFERENCE_PATTERN` — `:623-626`

Detects whether a prompt describes subject material at all, so plant-free shots (soil
cross-sections, drainage-hole close-ups — see the comment at `:619-622`) are never force-fed an
irrelevant species name.

Rename on extraction: this is the **subject-reference pattern**. For a knife channel it would
match `blade|edge|bolster|scales`. Same role, different vocabulary.

### 1c. `ACTION_CHECKS` — `:652-658`

2-tuples: `(narration_pattern, required_evidence_pattern)`. Entirely about watering.

### 1d. `REVERSAL_CHECKS` — `:665-683`

4-tuples: `(narration_pat, evidence_pat, reason, evidence_must_be_absent)`. Three rules —
dehydration, pests/disease, nocturnal behaviour. The `reason` string is user-facing and
succulent-specific.

### 1e. `HALLUCINATION_CHECKS` — `:688-697`

3-tuples: `(narration_must_lack_pat, prompt_evidence_pat, reason)`. Two rules — invented
pests, invented watering.

### 1f. The retry-guidance prose — `:770-798`

**This is the subtle one; read §4 before touching it.** `reversal_detail`, `species_detail`,
and `fix_note` are hardcoded English containing real domain instruction:

> "If narration says 'dry/puckered/dehydrated', show that exact physical state — do NOT add
> watering, drainage water, or any action that would fix the problem."

and

> "do not substitute a preparatory gesture like 'hands about to water' or 'checking for
> drainage'."

That text is what actually corrects a violating prompt. Moving the regexes but leaving this
prose behind produces a pipeline that *detects* violations generically and *explains* them in
succulent terms — which for any other subject means the retry guidance is nonsense and the fix
silently stops working.

### 1g. `approved_species` → `subjects`

`approved_species_list()` (`:584-600`) and `names_species()` (`:603-616`) read the config key
directly. Phase 1 renamed the data to `subjects` in the DNA file; this phase updates the
readers. Keep the defensive dict/list-of-str/list-of-dict handling at `:592-599` — it exists
for a reason.

**`names_species()` matches on the first two name-words** (`:613`), so cultivar punctuation
never affects the match. That heuristic is succulent-shaped ("Echeveria 'Perle von Nurnberg'")
but generalises fine to any `Genus specific` or `Brand Model` naming. Keep it; make the
word-count configurable only if a real second channel needs it.

---

## 2. WHAT STAYS IN CODE

Do not move these. They are the engine.

- `validate_and_fix_shots()` control flow, including the retry loop and `max_retries`
- The overuse threshold `max(2, -(-total // 3))` at `:708` — already scales with scene count,
  already verified, subject-independent
- `_extract_setting()`'s matching *logic* and its `Setting:\s*(...)` fallback at `:580`
- `names_species()`'s first-two-words matching algorithm
- The four violation categories and how they compose into `violating_keys` at `:747`

---

## 3. SCHEMA — the `validation` block

Extends the DNA file Phase 1 created.

**Note on assets.** Channel-specific binaries live in `channel_dna/<name>/`, adjacent to
`channel_dna/<name>.json` — established during the Phase 1 closeout, starting with `bgm.mp3`.
DNA keys naming an asset (`bgm_file`, and later any watermark logo, sting, or font) hold a bare
filename resolved against that directory. Do not reorganise this; do not move assets back to
the pipeline root. If this phase adds any asset-bearing key, follow the same convention.

Suggested shape for the new block:

```json
{
  "validation": {
    "subject_reference_pattern": {
      "pattern": "\\b(plants?|succulents?|leaf|leaves|rosettes?|stems?|fronds?|foliage|petals?)\\b",
      "note": "Only require a named subject when the prompt describes subject material. Plant-free soil/pot/mechanism shots are a real recurring pattern (Myths_S2_yt: soil cross-section, drainage-hole close-up) and must never be force-fed an irrelevant species."
    },
    "setting_vocabulary": {
      "ordered": true,
      "note": "ORDER IS LOAD-BEARING — _extract_setting returns the FIRST match, so multi-word forms must precede the bare words they contain. Do not alphabetise. Bare forms were added after the overuse check silently never fired for months.",
      "keywords": ["home windowsill", "backyard garden", "...", "windowsill", "potting bench", "..."]
    },
    "action_checks": [
      { "id": "watering-in-progress",
        "narration": "...", "evidence": "...",
        "guidance": "If the narration explicitly describes water pouring, soaking, or draining, the image MUST show that action actually happening — visible water flowing, wet soil, water dripping from a drainage hole. Do not substitute a preparatory gesture like 'hands about to water'." }
    ],
    "reversal_checks": [
      { "id": "dehydration-vs-watering",
        "narration": "...", "evidence": "...",
        "evidence_must_be_absent": true,
        "reason": "narration describes dehydration/dryness but prompt shows active watering",
        "guidance": "If narration says dry, puckered, or dehydrated, show that exact physical state. Do NOT add watering, drainage water, or any action that would fix the problem." }
    ],
    "hallucination_checks": [ { "id": "...", "narration_must_lack": "...", "evidence": "...", "reason": "...", "guidance": "..." } ]
  }
}
```

### Migration mechanics — three real gotchas

1. **Regex escaping.** Every `\b` becomes `\\b` in JSON. Getting this wrong produces a regex
   that compiles but matches nothing — a check that silently never fires, which is exactly the
   `KNOWN_SETTING_KEYWORDS` bug repeating itself. §6's golden test is the defence.
2. **Comments become `note` fields.** JSON has none. Every explanatory comment in the current
   source carries bug history; port each one as a `note` on the rule it belongs to. Do not drop
   them because they are "just comments" — they document failures that produced no error
   message.
3. **Every rule gets a stable `id`.** The current tuples are positional. Named ids make the
   retry guidance in §4 addressable, and make a failure report readable.

---

## 4. THE RETRY GUIDANCE — do not lose its teeth

This is the part most likely to be done lazily, and the part where laziness is invisible until
a whole video is wrong.

**Current behaviour:** when shots violate, `:787-798` assembles one `fix_note` containing
*every* domain instruction, hardcoded, whether or not it is relevant to the violation.

**Required behaviour after extraction:** each rule carries its own `guidance` string, and
`fix_note` is composed from **only the guidance of the rules that actually fired**, plus the
generic variety instruction that stays in code.

This is strictly better than today — the model receives targeted correction instead of a wall
of mostly-irrelevant rules — and it is what makes the guidance portable, since a knife channel's
DNA supplies knife guidance for knife rules.

**Preserve the emphasis.** The current prose uses CRITICAL, capitalised MUST, and explicit
"do NOT" framing. That register survived because milder phrasing did not hold — CLAUDE.md
records semantic reversals slipping through plain prose instructions across three rounds of
tuning. Carry the strength of the language into the `guidance` fields verbatim where possible.
Do not paraphrase it into something politer.

---

## 5. SUBJECTS EXPANSION — 30+ entries

Bundled here deliberately: this is the data that belongs in `channel_dna`, so expanding it
before the extraction would mean writing it into the wrong file and moving it immediately.

- Expand `subjects` from 9 to 30+, same `{common, visual}` schema
- Every one of the 15 species in
  `...\Long Videos\Source Docs\soil-drainage-species-susceptibility-source-doc.md` §C must be
  present, including the taxonomy aliases in §E (`Curio rowleyanus` / `Senecio rowleyanus`,
  `Haworthiopsis fasciata` / `Haworthia fasciata`) — **both forms must satisfy
  `names_species()`**, since narration uses the current name and viewers know the trade name
- Succulents only. See the source doc's "Channel scope" section: Snake Plant and cacti are
  botanically defensible and deliberately excluded. Do not let list-filling reintroduce them
- `visual` descriptions must be specific enough to disambiguate — "pale grey-green compact
  rosette" is the standard set by the existing entries. A vague description makes the
  validator's species check pass while the image is still wrong

**Show the expanded list to the user before committing it.** This is horticultural authoring,
it is the config the brand validator enforces on every future video, and it is not an
agent-judgment call.

---

## 6. VERIFICATION

**Step 1 is the whole ballgame. Do it first and do not skip it.**

1. **Golden-output test — behaviour preservation.**
   Before changing anything, capture the current validator's output over a fixed corpus:
   collect the `prompts_review.json` files from several existing completed projects
   (`Myths_S2_yt`, `Misting_S1_yt`, `Propagation_S1_yt` and similar), run
   `validate_and_fix_shots()` against them with `regenerate_fn` stubbed to a no-op, and record
   which shot keys are flagged in which category.

   After extraction, re-run and assert the flagged sets are **identical**. Any difference is a
   regression, most likely a mis-escaped regex.

   This is the only check that can prove a silent-no-op didn't get introduced, because a regex
   that matches nothing raises no error and fails no other test.

2. **Regex compile lint.** Every pattern in the DNA file compiles, and every one matches at
   least one string in the golden corpus. A pattern matching nothing anywhere is almost
   certainly an escaping bug, not a genuinely unused rule.

3. **Schema lint.** `subjects` non-empty and every entry has a `visual`; `setting_vocabulary`
   non-empty; every check has an `id` and a `guidance`; no duplicate ids.

4. **Targeted-guidance test.** Construct a prompt that violates exactly one rule; assert the
   generated `fix_note` contains that rule's guidance and **not** the others'. This is what
   proves §4 was done properly rather than by concatenating everything.

5. **Blast-radius check.** At least two other files consume this module:
   - `.claude/skills/produce-short/scripts/audit_prompts.py` imports `names_species` — the
     comment at `:608` says explicitly that it does so to stop the two copies drifting. If the
     signature changes, this breaks, and it belongs to the **Shorts** skill.
   - `generate_override_prompts.py` runs the same brand validation (per CLAUDE.md) and passes
     its own `regenerate_fn`.

   Grep the whole repo for `names_species`, `approved_species_list`,
   `validate_and_fix_shots`, `PLANT_REFERENCE_PATTERN`, and `approved_species` before changing
   any signature. Report every consumer found.

6. **End-to-end.** Re-run Phase 1's narrative test through `--dry-run-prompts` and confirm the
   prompts are equivalent in character to Phase 1's output. No image spend needed.

7. **Portability smoke test — the actual point of this phase.** Hand-write a deliberately
   minimal second DNA file for an unrelated subject (a dozen entries is plenty; it is throwaway).
   Run `--dry-run-prompts` against a short scratch script in that subject. Confirm the prompts
   come out in that subject's vocabulary with **no Python edited**.

   If this requires touching code, the extraction is incomplete — report exactly what was
   missing rather than patching around it. Delete the throwaway DNA afterwards.

---

## 7. REPORTING

State explicitly in the final report:
- The golden-test result — flagged-set identical, or the precise diff and why
- Every consumer found by the §6.5 grep, and whether each still works
- Anything that could not be extracted without touching engine logic, and why
- Whether the §6.7 portability test needed any code change — this is the honest measure of
  whether Phase 1.5 achieved its goal

Do not report success on the strength of the pipeline still working for succulents. It working
for succulents is the *precondition*; it working for a throwaway second subject with zero code
edits is the deliverable.
