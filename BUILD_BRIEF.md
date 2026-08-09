# BUILD BRIEF — `longform_pipeline/` (16:9 long-form sibling to `shorts_pipeline2`)

**Status:** not started. This document is the complete spec. Nothing in this folder exists yet
except this file.

**Audience:** an agent building this from scratch. Everything needed is here; you should not
need to re-derive design decisions. Line references are to files as they existed 2026-08-05.

---

## 0. HARD CONSTRAINT — READ FIRST

`C:\Bakcup_Asus\Aeonium_Glow\shorts_pipeline2\` is **in active production**. It has published
videos, a working test suite, and a documented history of expensive bugs.

**Do not modify anything in it except the single additive change in §4.** Everything else is a
fork. When in doubt, copy rather than edit.

Read `shorts_pipeline2/CLAUDE.md` before starting. It documents traps that will otherwise cost
you a full session — particularly around `--prompts-file` path resolution and WhisperX
hallucination stripping.

---

## 1. WHY A FORK, NOT A `--format` FLAG

An earlier version of this plan threaded a `--config-overlay` flag through four scripts in
`shorts_pipeline2` so both pipelines could share one config. **That approach was rejected.**
Regression risk on a working revenue pipeline outweighs the config-drift it would have saved.

Consequence: **there is no `--config-overlay` mechanism.** `longform_pipeline/` gets its own
full `pipeline_config.json`. If you find yourself adding a flag to a `shorts_pipeline2` file,
stop — you are off-spec.

---

## 2. FOLDER LAYOUT

### Copy from `shorts_pipeline2/` into `longform_pipeline/`
- `generate_script.py`
- `generate_images.py`
- `generate_override_prompts.py`
- `upload_youtube.py`
- `pipeline_config.json`
- `run_pipeline.py` — copy, then heavily trim per §5

### MOVE (not copy)
`shorts_pipeline2/stitch_video_longform.py` → `longform_pipeline/`

This file is a stray from a different project ("The Interested Indian") per its own docstring.
`shorts_pipeline2/CODE_REVIEW.md:186` already flags it for removal. Moving it out is a wanted
side effect, and it is the right starting template: already 1920×1080, already consumes the
same `manifest.json` shape.

### Reference in place — do NOT copy
Drift in these causes real, previously-experienced bugs:
- `shorts_pipeline2/auto_split_scenes.py` — holds `strip_trailing_hallucinations()`, the
  WhisperX artifact fix that cost a full day on 2026-07-29
- `shorts_pipeline2/stamp_manifest.py`
- `shorts_pipeline2/generate_srt.py`

**Import breakage warning.** The moved stitch script does
`from stamp_manifest import stamp_manifest` / `from generate_srt import generate_srt` at
`:77-78`, and its docstring at `:33` requires them in the same folder. After the move,
`_CAPTION_PIPELINE_AVAILABLE` goes False and it `sys.exit(1)`s at `:610` — **after a complete
10-minute render has already happened.** Fix with an explicit
`sys.path.insert(0, <abs path to shorts_pipeline2>)` at the top of the file. Do not leave this
to chance; the failure is silent until step 2 of 4.

---

## 3. CHANGES INSIDE THE FORKED `generate_images.py`

**a) Aspect-phrase parameterisation.** Replace every `"9:16 vertical"` literal with a phrase
derived from `config["image_aspect_ratio"]`. Sites: `:279`, `:337-341`, `:371`, `:489-493`,
`:531`. The first and last are easy to miss.

**b) Real bug at `:907`.** The Gemini provider hardcodes `aspect_ratio="9:16"` while `aspect`
is already computed from config at `:984`. Use `aspect`.

**c) Generalise** `crop_to_9x16()` (`:926-957`) into `crop_to_aspect(image_bytes, ratio_str)`,
parsing `"9:16"` / `"16:9"` rather than hardcoding `9/16`.

**c2) Add a normalisation step — this pipeline has none, and it is the real fix.**

The sibling `interested_indian_pipeline/generate_images_flux.py:256-279` forces every generated
image to a fixed target resolution before saving, regardless of provider. Its pilot images are
consequently all landscape (1280×720 / 1344×768, ratios 1.75–1.83; 1 square out of 91). Aeonium
Glow has no equivalent — `save_image()` (`:960-964`) writes provider bytes through with only an
optional crop.

Port the concept, **fixing two flaws in their implementation:**
1. Their `:273` is a bare `img.resize((1280,720))` with **no crop** — a square input is
   stretched, not cropped. Compose correctly: `crop_to_aspect()` first, *then* resize to target.
2. Their `:277-278` is `except Exception: pass` — the normalisation silently no-ops if PIL is
   missing. Fail loudly instead.

Target resolution is a decision to surface, not assume. Theirs is 1280×720, which the stitch
then upscales to 3840×2160 for Ken Burns headroom — a 3× upscale that shipped acceptably for
graphics-led news content. Aeonium Glow is macro photography with shallow depth of field, which
shows upscaling far more. Recommend **1920×1080 minimum**, and note Flux at 16:9 natively
returns 1344×768, so hitting 1080p may need a larger requested output rather than an upscale.
(That someone already generated 8 images at 2816×1536 in `ep01_v1` suggests this question came
up there too.)

Normalisation matters regardless of provider order, and becomes *more* important with mixed
providers: different providers return different native sizes, so without a single target the
same video gets scenes of visibly different sharpness after the Ken Burns upscale.

**SUPERSEDES (d) below — user-supplied update, 2026-08-05.** xAI/Grok Imagine now supports
native `aspect_ratio` (16:9, 9:16, 3:2, 4:3, 2:1, 20:9, auto) plus a separate resolution
control (1k / 2k). At 2k, 16:9 yields roughly 2048×1152. The comments at
`generate_images.py:864` and `:873` saying no size parameter is supported were accurate when
written and are now stale.

This reverses the provider-order rationale. On output quality xAI is now the **better** primary,
not merely the cheaper one:

| Provider | Native 16:9 | To reach 1920×1080 |
|---|---|---|
| xAI at 2k | ~2048×1152 (2.4 MP) | downscale 0.94× |
| Flux dev (Replicate) | 1344×768 (1.0 MP) | upscale 1.43× |

Set `image_provider_order` to `["xai", "replicate", "gemini"]`, and set xAI's `returns_square`
to `false`.

**Do not reorder without also updating `generate_with_xai()` (`:854-894`).** It currently passes
no size or aspect arguments whatsoever. Reordering alone makes Grok primary while it still
returns its default — silently, on every image. Add the `aspect_ratio` and resolution
arguments, request **2k**, and delete the now-false comments at `:864` and `:873` rather than
leaving them beside contradicting code.

**Verify empirically before committing to the order.** Make one real call, print the returned
image's actual pixel dimensions, and report them. Do not rely on documentation — the whole
reason this section needed rewriting is that a code comment described an API that had since
changed. If 2k 16:9 does not come back at roughly 2048×1152, report the real numbers and stop.

**d) Provider order — this is the important one.**

`:1119-1123` tries **xAI first**, and xAI has no size parameter (see the comments at `:864`
and `:873`). Its square output is centre-cropped. Cropping a 1024² square to 16:9 yields
1024×576 — which `stitch_video_longform.py:252` then upscales to 3840×2160 for Ken Burns
headroom. That is a 3.75× upscale from a 576px source, on the format people watch on a
desktop or TV. The same math was survivable at 9:16 on a phone; it is not here.

**Only Replicate Flux honours `aspect_ratio`** (`:827`). Make provider order config-driven and
set long-form to `["replicate", "gemini", "xai"]`.

While you are there: `is_square` at `:1133` / `:1142` / `:1146-1149` is only assigned inside
branches. Clean it up, or the reordering will trip over it.

**e) Do NOT touch the setting-overuse check.** `:708` computes `ceil(total/3)` with a floor of
2, so it already scales with scene count. It needs no change for longer videos. This was
checked.

**Same aspect-phrase work** in the forked `generate_script.py` (`:101-105`) and
`generate_override_prompts.py` (`:58`, `:133-134`).

---

## 4. THE ONLY `shorts_pipeline2` EDIT — `auto_split_scenes.py`

Add optional `--compute-type` and `--batch-size` flags, **defaulting to today's hardcoded
`float16` / `16`** so Shorts behaviour is byte-for-byte unchanged. Port the implementation from
the sibling `interested_indian_pipeline` script, which already exposes both.

**Why this is not optional:** a 60-second Short transcribes in ~29s on the RTX 4050's 6GB. A
10-minute narration is 10–20× that audio. `shorts_pipeline2/CLAUDE.md` explicitly flags the
hardcoded values as an OOM risk for longer content. **This is the single most likely first-run
failure.**

Run the existing test suite after this change and confirm it passes.

---

## 5. `longform_pipeline/run_pipeline.py`

Trim the copy to a single linear run: `script → voiceover → scenes → images → stitch → upload`.

Delete:
- the `--variants` loop
- the CTA-swap-per-variant block (`:426-453`)
- `copy_images()` (`:260`)

Long-form has no yt/ig fork.

Two fixes while copying:
- `run_voiceover` (`:180-184`) passes the entire script via `--text` on argv. Use edge-tts
  `--file` instead — argv gets fragile past ~20-minute scripts.
- `approval_gate` (`:139`) dumps the whole script to stdout. Unusable at 1500+ words. Default
  to opening the file; the `edit` branch at `:153` already does `os.startfile`.

Add `--format narrative|listicle`, defaulting to `narrative`. See §8.

---

## 6. `longform_pipeline/pipeline_config.json`

Full copy of the Shorts config, with these values changed:

| Key | Value | Why |
|---|---|---|
| `image_aspect_ratio` | `"16:9"` | |
| `image_style_template` | swap `"9:16 vertical."` → `"16:9 widescreen."`, keep palette / species / faceless-hands rules | A dedicated long-form style guide comes later; this is a deliberate placeholder |
| `script_style`, `script_ending` | long-form pacing | drop the 65–75s / 140–160-word cap |
| `max_scene_seconds` | larger than the Shorts default of 10 | |
| `youtube_tags` | **remove `'shorts'`** | `upload_youtube.py:331` reads this straight through; a custom `--description` does not stop the tag shipping |
| `bgm_volume` | decide explicitly | Shorts config says 0.1; `stitch_video_longform.py:86` hardcodes 0.04 and never reads config |
| `watermark_fontsize` | set explicitly | absent from config today, falls back to `stitch_video_complete.py:511-518` defaults. `42` was tuned for a 1080px-wide frame; at 1920 wide it is half the relative size |
| `image_provider_order` | `["replicate","gemini","xai"]` | new key, see §3d |
| `credentials_dir` | path to `shorts_pipeline2` | see below |
| `variants` | **remove the block entirely** | |

**Credentials — do not copy the OAuth token.** The forked `upload_youtube.py` resolves
`client_secrets.json` / `youtube_token.pickle` relative to itself. Two tokens refreshing
independently against one channel causes problems. Add the `credentials_dir` key and read them
from `shorts_pipeline2` instead.

---

## 7. ADAPTING `stitch_video_longform.py`

**Delete — Interested Indian dead weight:**
- Mascot overlay: `load_mascot_config` (`:198`), `apply_mascot_overlay` (`:284`), the config
  docstring (`~:36-64`), and all call sites. *Read `apply_mascot_overlay` before deleting it —
  its `enable='between(t,...)'` pattern at `:298` is the model for the numbered overlay in §8c.*
- CTA path: `find_cta()` (`:175`), the `--no-cta` flag (`:578`), the append block (`:482-490`).
  It reads `{project}/../common/cta/`, which does not exist in this layout.

**Port in from `stitch_video_complete.py`:**
- `add_watermark()` (`:234-282`) — already resolution-agnostic, computes position from ffmpeg
  `w`/`h` vars rather than literals
- `find_bgm_path()` (`:315-337`) — the long-form file hardcodes `{project}/bgm.mp3` at `:413`
  and silently renders music-free at `:553` if absent. Without this you will ship a silent
  video and not notice until playback.

**Adjust:** `burn_srt_captions` `FontSize=28` (`:384`) is the other channel's number. Pick one
for 1920×1080 Aeonium Glow.

---

## 8. THE TWO FORMATS

This pipeline serves two formats and **narrative is the default.** Many videos will have no
list at all — the already-produced *Stop Succulent Rotting Fast* is a narrative video, and that
shape (hook → sections → close) is as much the channel's core as the countdown is.

**Build the shared core first, then the two adapters.** Do not build listicle mode and
retrofit narrative afterwards; narrative is the simpler path and it is the one that must work
by default. A run with `--format narrative` should never load `items.json`, never draw a
numbered overlay, and never apply the listicle species override.

| | `narrative` (default) | `listicle` |
|---|---|---|
| Script shape | hook → sections → close | hook → shared-fix open loop → #N…#1 → full fix → CTA |
| `items.json` | not produced, not read | required; generated from the source doc |
| Scene splitting | WhisperX sentence split, unchanged | same, plus each item must begin a new sentence |
| Numbered overlay | **off** | on, drawtext with `enable=between(t,…)` |
| Species validation | global `approved_species`, exactly as today | item list authoritative, global list as fallback |
| Chapters | from section headings | generated from `items.json` |
| `--dry-run-prompts` | recommended | **mandatory** |
| Retention glue | none | teases at quarters + before #3 |

Everything before the script stage — voiceover, WhisperX, image generation, stitch, watermark,
BGM, captions, upload — is **identical across both formats.** The format flag should touch the
script stage, the manifest stamping, and one optional ffmpeg filter. If it is leaking further
than that, the abstraction is wrong.

`listicle` adds the following.

### a) SPECIES LIST — blocking, do this first

`pipeline_config.json` currently has **9** entries in `approved_species`:

> Echeveria elegans, Graptopetalum paraguayense, Crassula ovata, Aeonium arboreum 'Zwartkop',
> Aeonium 'Sunburst', Echeveria 'Perle von Nurnberg', Haworthia fasciata,
> Sedum rubrotinctum 'Aurora', Sedum morganianum

`generate_images.py:716-719` flags any plant-mentioning prompt that does not name one of them,
and the retry pass at `:800-808` **rewrites the prompt to an approved species.**

On a 15-species listicle this silently swaps the plant in the image away from the plant in the
narration, fifteen times, and the run reports success. This is the highest-severity issue in
this brief.

Required:
1. Expand `approved_species` to 30+, matching the existing `{common, visual}` schema. Nine of
   the fifteen species for the first video are missing — see the source doc, Section E.
2. In listicle mode, treat **the video's own item list as authoritative** for
   `names_species()`, with the global config list as fallback.
3. Add a test: a prompt naming an item-list species must not be flagged.

### b) `items.json` — generated from the source doc, not hand-authored

The source doc's ranked list is the single source of truth. `items.json` is derived from it.
Do not maintain two lists; this project has been bitten repeatedly by duplicated state
(manifest vs. reality, `.srt` vs `.ass`).

```json
{ "rank": 1,
  "species": "Curio rowleyanus",
  "trade_name": "Senecio rowleyanus",
  "common": "String of Pearls",
  "tier": "worst",
  "twist": "<one-clause plant-specific risk>",
  "source_ref": "<anchor into the source doc supporting this rank>" }
```

Constrain `generate_script.py` so **each item begins a new sentence.** Scenes already split on
sentence boundaries, so item → scene index then maps cleanly with no fuzzy matching. Stamp
`item_number` and `item_name` onto the opening scene of each item in `manifest.json`.

Items are emitted in **descending rank** (countdown, 15 → 1).

### c) Numbered overlay — do NOT build a card compositor

Reuse the ffmpeg `drawtext` approach from `add_watermark()`
(`stitch_video_complete.py:234-282`), with an `enable='between(t,start,end)'` clause — the same
pattern as the mascot overlay you deleted in §7. Config-driven font, colour, position.

### d) Retention glue — vary the phrasing

Teases go after items 12, 9, 6, and immediately before #3. Positions derive from item count
(roughly quarters, plus one before the top 3); do not hand-place them per video.

**The tease line must differ at every insertion point and must add new information.** Repeated
identical phrasing on a TTS narration is the primary audible tell of synthetic voiceover —
this was confirmed directly in competitor analysis of a comparable channel, where flat
repetitive cadence across items was the giveaway. Approved copy is in the skill.

### e) Payoff structure

State the shared fix **once near the top as an open loop**; give each item only its specific
twist in one clause; deliver the full fix at #1 before the CTA.

Do not generate 15 separate full fixes (kills pace) and do not withhold all fixes until the end
(that is the catalog-channel pattern this channel is explicitly differentiating from).

---

## 9. FIRST BUILD TARGET

**`10 Succulents That Stretch Without Enough Light`** — updated 2026-08-05. This supersedes the
earlier rot target, which was chosen only because its source doc existed first.

Source doc: `...\Long Videos\Source Docs\light-and-etiolation-source-doc.md` (§G holds the
ranked list).

It wins on every axis:

| | Rot listicle | Etiolation listicle |
|---|---|---|
| Demand | no comparable term | **1.32M head term** ("How to Fix Elongated Succulents"), plus 486K and 314K |
| Items | 15 | **10** — cheaper, faster proving run |
| Source doc | ✅ | ✅ |
| Species already in `subjects` | all 15 | all 10 |
| Overlap with shipped content | partial — the rescue video covers rot | none |

Fewer items also makes it the better *proving* run: find the format's problems on 10 items
rather than 15.

⚠️ **The rot listicle is no longer automatically second — it needs a differentiation call
first.** A live-channel check on 2026-08-07 found eight published long-form videos, one of them
*"Stop Using Regular Potting Soil! (Succulent Soil Mistake)"* with 1K views, a month old. That is
the same axis as the planned rot listicle. Adjacent rather than certainly duplicate — a ranked
species list versus a general mistake — but the call must be made deliberately, by watching that
video, before the listicle is built. See `...\Aeonium Glow\cta_plan.md` for the full catalogue.

**Known risk specific to this topic — read source doc §H.** Etiolation is hard to render. A model
asked for a "stretched succulent" returns a healthy compact one; this is the same prior-collision
class as the cross-section/sliced-fruit failure in Phase 1. Prompts must name the *geometry*
explicitly ("visible bare stem between widely spaced leaves," "rosette opened and flattened,"
"pale green with no red edge colouring") and put the failure in the negatives ("not a tight
compact rosette, no symmetrical dome"). Expect to iterate at the dry-run stage, and budget for it
rather than discovering it mid-run.

Source doc (already written, points to it via `source_doc.path` as usual):
`...\Aeonium Glow\Long Videos\Source Docs\soil-drainage-species-susceptibility-source-doc.md`

**Differentiation constraint.** A long-form rot video already exists and is produced:
*Stop Succulent Rotting Fast: The First 5 Minutes Matter*
(`Aeonium_Glow/H03-2026-08-rotting-first-5-minutes/`). It is a **rescue** video; this is a
**prevention / species-selection** video. The source doc's "HOW TO USE" section defines the
boundary. Do not let the script rebuild rot biology from scratch — summarise in two or three
sentences and cross-reference. This project has previously shipped near-duplicate content by
accident (see CLAUDE.md on `Propagation_S2` vs `short-04`).

**Channel scope: succulents only.** No general houseplants, no tropicals, no foliage plants.
Snake Plant and cacti are both botanically defensible and both deliberately excluded — the
reasoning is in the source doc's "Channel scope" section. Do not let an LLM quietly reintroduce
them to fill a list.

**On the competitor channel that prompted this work:** it was studied for *production
technique only* — that stills + Ken Burns + TTS + numbered overlays holds up over a 25-minute
runtime. Its content model (80-item catalogs across arbitrary houseplant genera) is explicitly
**not** the model here. Do not use its topic list, its item counts, or its genre coverage as
guidance for anything.

If a collector-style catalog is attempted later, cap it at 10–12 items — 20 distinct cultivars
of a single genus is the hardest possible case for image accuracy, and the failure is silent.

---

## 10. COST — SURFACE THIS BEFORE THE FIRST RUN

- **Corrected 2026-08-06, Phase 1.5 — the estimate below was wrong.** Phase 1's WhisperX-at-scale
  test measured real density against the actual rot-rescue narration: **54 shots over 341s
  (5.7 minutes) of real audio — ~9.5 images/minute.** A real 10-15 minute listicle is therefore
  **~95–140 images**, not 30-45 — a 3-4× correction. The original "~15 items × 2-3 scenes =
  30-45 images" estimate undercounted because it only budgeted for the *ranked items themselves*,
  not the hook/mechanism/close sections a real script also needs, and long-form scripts run far
  more scenes per minute than the estimate assumed. Shot grouping (`visual_group_id`) — sharing
  one image across multiple short consecutive scenes — is therefore a real **cost lever** at
  long-form length, not just a variety mechanism as originally framed; it already reduced this
  test's 65 raw scenes to 54 billable shots. Not redesigning grouping here — that's Phase 2's
  job — just recording the real number so image spend can be planned against it accurately.
- More shots means more validator-flagged shots, so more GPT-4o retry passes
  (`generate_images.py:800-808`)
- Render is three full-length passes over a 10-minute 1080p file (concat → BGM → caption burn),
  each after per-scene 4K upscales

State expected spend and wall-clock time to the user before the first real run.
`--dry-run-prompts` and human approval of `prompts_review.json` is **mandatory** for every
listicle, not optional.

---

## 11. VERIFICATION — IN THIS ORDER

1. **Non-regression.** Run the existing `shorts_pipeline2/tests/` suite after the §4 change.
   That is the proof, **not** an expensive re-run of a real project. Note that
   `--start-from images` on an existing project skips every image (`:1107`) and proves nothing,
   while `--force` re-spends real money.
2. **Unit test** the aspect phrase for a 9:16 config vs a 16:9 config. Free, decisive, and
   exactly the "pure logic with documented bug history" scope `tests/README.md` defines.
3. **Species-validator test** per §8a.3.
4. **`--dry-run-prompts` and stop.** Have the user approve `prompts_review.json` before any
   image spend.
5. **Assert every PNG in `images/` is landscape** before stitching. One line; catches the xAI
   problem immediately.
6. **Full stitch on a short test script first** (2–3 minutes, not 10). Verify on an extracted
   frame: 1920×1080, captions readable in the bottom third, watermark present, numbered overlay
   correct, BGM audible.
7. **Do not upload anything.** Stop at stitch and report.
