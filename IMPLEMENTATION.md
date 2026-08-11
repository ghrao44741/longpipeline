# Implementation Guide — `longform_pipeline/`

> Audience: whoever next needs to modify, debug, or extend this pipeline. Assumes you can
> read Python and don't need "what is ffmpeg" explained, but does need "why is this file
> shaped this way" explained. For "what do I click/run and when," see `USER_GUIDE.md`
> instead — that document covers decisions; this one covers mechanism.
>
> Written 2026-08-11, after the first complete video (Etiolation_S1) shipped end-to-end.
> Supersedes scattered notes in `CLAUDE.md`, `BUILD_BRIEF.md`, `BUILD_BRIEF_PHASE_1_5.md`,
> `PHASE_1_REPORT.md`, `PHASE_1_5_REPORT.md` — those remain as historical build logs (what
> was decided and why, at the time); this document is the current-state map. If the two
> disagree, trust the code first, this document second, the historical logs last.

---

## 1. What this is, in one paragraph

A pipeline that turns a written narration script into a finished, captioned, watermarked
16:9 YouTube video for the `@aeoniumglow` succulent-care channel: text → TTS voiceover →
WhisperX-aligned scene splitting → AI-generated 16:9 images per scene (brand-validated
against a per-species visual style) → ffmpeg stitch with Ken Burns motion, background music,
burned captions, watermark, and optional per-item countdown overlay → automated verification
→ YouTube upload as a private draft. Two content **formats** (narrative, listicle) share
100% of this pipeline except the script-writing stage and one manifest-stamping step.

---

## 2. Repository relationship: a fork, not a flag

This directory is a **fork** of the sibling `../shorts_pipeline2/` project (a 60–90s Shorts
pipeline for the same channel), not a `--format` flag bolted onto it. That decision is
load-bearing for how files are organized here — see `CLAUDE.md`'s "Fork vs shared" table for
the authoritative, currently-accurate list, but the shape is:

- **Forked (diverge freely):** `generate_script.py`, `generate_images.py`,
  `generate_override_prompts.py`, `upload_youtube.py`, `run_pipeline.py`,
  `pipeline_config.json`, `stitch_video_longform.py`. Copied once, then edited independently.
- **Shared (imported/invoked cross-directory, never copied):** `auto_split_scenes.py`,
  `stamp_manifest.py`, `generate_srt.py`, all still living in `shorts_pipeline2/`. A fix
  there benefits both pipelines automatically; a fix here would silently drift.
- **Two sanctioned edits ever made to the shared files**, both additive/backward-compatible:
  `auto_split_scenes.py` gained optional `--compute-type`/`--batch-size` flags (defaults
  unchanged); `generate_srt.py` prefers `scene["video_start"]`/`["video_end"]` over
  `scene["start"]`/`["end"]` when both exist (Shorts never sets those fields, so it always
  falls through to the old behavior). Any further edit to a shared file needs a deliberate
  decision, not a reflex — see §9.

**Why this matters for you:** if you're chasing a bug in scene-splitting, WhisperX alignment,
or SRT generation, the code you need is in `shorts_pipeline2/`, not here, even though this
pipeline calls it. If you're chasing a bug in image generation, prompting, stitching, or
upload, it's here and only here.

---

## 3. The config seam: `pipeline_config.json` + `channel_dna/`

Every forked script calls `config_loader.load_config()` instead of reading either file
directly. Two files, two concerns, one flat merged dict at the end:

```
pipeline_config.json          HOW THE MACHINE RUNS (subject-agnostic)
                               aspect ratio, provider order, scene timing, venv paths,
                               credentials_dir, channel_dna_file (which DNA to load)

channel_dna/<name>.json       WHAT THE CHANNEL IS (subject-specific, brand)
                               voice, script style, visual style, watermark, YouTube
                               metadata, the approved subject list ("subjects")
```

**Rule of thumb: if a viewer would notice the change, it belongs in DNA.** Watermark
position, caption font size, and the Bensound music credit line are all `channel_dna` keys
for exactly this reason — they're brand decisions, not engine parameters, even though
mechanically they're just `config.get(...)` calls like anything else.

`config_loader.load_config(scripts_dir, project_dir=None)`:
1. Reads `pipeline_config.json`.
2. Resolves `channel_dna_file` and shallow-merges that dict over it — **DNA wins on key
   collision.**
3. If `project_dir` is given and `{project_dir}/config_override.json` exists, shallow-merges
   that on top of everything — **highest priority, wins over both.** This is the per-project
   escape hatch (e.g. `Etiolation_S1/config_override.json` flips `item_overlay_enabled` on
   without changing that default for every other, narrative, project).
4. **Guard:** a project override may not contain a nested `"cta"` key — that would silently
   replace the DNA's entire CTA block (ask pattern, outro card config, subscribe line) instead
   of merging into it. Per-video CTA specifics use flat `cta_*` keys instead
   (`cta_watch_next_title`, `cta_comment_prompt`, etc.), which merge additively. This guard
   exists because three earlier bugs in this project all had the identical silent-
   substitution shape (see §9) — it was built proactively, not after a fourth incident.

Every `config.get("some_key")` call site in every forked script is unaware of which of the
three layers the value actually came from. That's the point — one flat dict, one call
convention, three files of increasing priority behind it.

**Channel-scoped binary assets** (not JSON) live in `channel_dna/<name>/`, adjacent to
`channel_dna/<name>.json` — e.g. `channel_dna/aeonium_glow/bgm.mp3`,
`channel_dna/aeonium_glow/outro_card.png`. A DNA key naming an asset (`bgm_file`,
`cta.outro_card.asset`) holds a bare filename, resolved against that directory via
`config_loader.channel_assets_dir()`. A per-project override still works
(`{project_dir}/{bgm_file}` is checked first), and a legacy pipeline-root fallback exists but
prints a loud deprecation warning if hit. **A declared-but-unresolvable asset fails loudly
(raises), not a silent asset-free render** — this was a real, previously-shipped failure mode
(BGM silently absent from every long-form video before 2026-08-07 had a different root cause,
but the "fail loud, not silent" design principle for assets predates and survives that bug).

---

## 4. Stage pipeline and data flow

```
script.txt  ──(TTS)──>  audio/*.mp3  ──(WhisperX align)──>  manifest.json (scenes, timings)
                                                                     │
                                              (listicle only) stamp_items.py
                                                       regroups scenes by item, not sentence
                                                                     │
                                                                     v
                                              generate_images.py (prompts -> images/*.png)
                                                                     │
                                                                     v
                                    stitch_video_longform.py (Ken Burns, BGM, captions, watermark)
                                                                     │
                                                                     v
                                         verify_output.py (automated checks, non-gating advisory)
                                                                     │
                                                                     v
                                              upload_youtube.py (private draft + metadata)
```

`run_pipeline.py` is the orchestrator — `--start-from {stage}` runs that stage and everything
after it; there is **no way to run a single isolated stage through it** (call that stage's own
script directly instead, as `USER_GUIDE.md`'s command reference does). Stages, in order:
`script → voiceover → scenes → images → stitch → upload`. `--start-from script` is
deliberately blocked (see §9) — long-form scripts are hand-approved and placed directly, this
pipeline never generates them programmatically end-to-end the way Shorts does.

### `manifest.json` — the single source of truth for a project

One JSON file per project (`{Project}/manifest.json`), holding an ordered list of `scenes`,
each with (at minimum) `id`, `image`, `audio`, `script` (the narration text for that scene),
and, once WhisperX has run, `whisperx_start`/`whisperx_end`. As the pipeline progresses, more
fields accumulate on each scene:

| Field | Written by | Meaning |
|---|---|---|
| `visual_group_id` | `auto_split_scenes.py` (narrative) or `stamp_items.py` (listicle) | Scenes sharing this value share **one** generated image |
| `prompt` | `generate_images.py` | The exact prompt text used for that scene's image (written back after generation — the thing `USER_GUIDE.md`'s "assert approved == shipped" backlog item wants auto-checked) |
| `item_number`, `item_name` | `stamp_items.py` (listicle only) | Which countdown rank this scene belongs to |
| `start`, `end`, `duration` | `stamp_manifest.py` (shared, `shorts_pipeline2/`) | **Audio-space** timing — narration duration only |
| `video_start`, `video_end` | `stitch_video_longform.py`'s `write_video_timeline()` | **Video-space** timing — the real rendered position, always `>=` the audio-space value (see §6) |

`manifest["title"]` is the real YouTube title once set (falls back to the project name if
never set — the trap `CLAUDE.md` flags as "packaging still project-named").
`manifest["youtube_video_id"]`/`["youtube_video_url"]` get written by `upload_youtube.py`
after a successful upload.

---

## 5. The two formats, mechanically

Narrative and listicle are **the same pipeline** with two deliberately small differences —
per `BUILD_BRIEF.md` §8, this is an explicit constraint, not an accident of how it turned
out:

1. **Script stage** — a listicle's `items.json` is generated from the source doc's ranked
   list (never hand-maintained as a second copy of the truth); a narrative script has no
   equivalent structured artifact.
2. **Manifest stamping** — `stamp_items.py` runs (listicle only) between the scenes stage and
   the images stage. It re-groups scenes by **item** instead of by WhisperX sentence-
   adjacency, which is the narrative path's default. Why this exists: at sentence-level
   grouping, a 10-item ~12-minute listicle measures ~9.5 images/minute — 110-120 images,
   which nobody reviews, silently defeating the `--dry-run-prompts` human checkpoint at
   exactly the format where the species-validator hazard (§6) matters most. Item-level
   grouping cuts a real 10-item project to **46 shots** (10 item groups + 36 sentence-level
   hook/explainer/outro shots around them) — reviewable, and dramatically cheaper.
3. **One optional ffmpeg overlay** — `stitch_video_longform.py`'s
   `add_item_number_overlay()`, gated by `item_overlay_enabled` (off by default in
   `pipeline_config.json`, flipped on per-project via `config_override.json`). Burns
   `#{n}  {name}` top-left for the duration of each item's on-screen window.

Everything else — `generate_images.py`'s prompt building, the stitch's Ken Burns/BGM/caption
logic, `verify_output.py`'s checks, `upload_youtube.py`'s upload mechanics — is identical
code for both formats. `build_chapters()`/`build_item_overlay_windows()` both detect format
by checking whether any scene carries `item_number`; `None`/empty means "narrative, no
listicle-specific behavior," treated as a normal case, not an error.

### The species-validator hazard (listicle-specific)

`generate_images.py` checks every plant-mentioning prompt against `channel_dna`'s `subjects`
list (`names_species()`, matching canonical name or any listed alias) and **rewrites** any
prompt naming an unrecognized species to an approved one, on a retry pass. For narrative
content this is the guardrail working as designed. For a listicle, where each item's species
*is* the content, an unrecognized name (most often from an ASR mis-transcription — see §9)
silently substitutes a **different** plant into that item's image, with no error printed. The
human `--dry-run-prompts` review step exists specifically to catch this before it becomes a
finished video; `USER_GUIDE.md`'s Phase C2 spells out what to check.

---

## 6. The stitch: `stitch_video_longform.py`

The most structurally important file to understand, because it's where three separate,
easy-to-reintroduce bug classes live.

### 6a. Audio-space vs. video-space timing — the recurring bug class

`sum(audio_duration + CLIP_EXTRA)` — the running total every per-scene loop naturally reaches
for — is **not** the real rendered video length. Every clip's video track holds for
`audio_duration + CLIP_EXTRA` seconds (a fixed per-clip pad, `CLIP_EXTRA ≈ 0.5s`), so the
video-space timeline drifts from the audio-space sum by `CLIP_EXTRA` plus frame-quantization,
**cumulatively, per clip** — negligible on a short project, seconds on a 120-clip long-form
one. This has caused three independent, identically-shaped bugs:

1. **Caption desync** (original) — `stamp_manifest.py`'s cursor (shared file, audio-space) fed
   straight into captions, which need video-space. **Fixed** by porting
   `build_video_timeline()`/`remap_time()` from Shorts' `generate_ass.py` (which solved the
   identical problem there) into `write_video_timeline()`, which writes `video_start`/
   `video_end` onto every scene after the real render. `generate_srt.py`'s one sanctioned
   edit (§2) makes it prefer these fields when present.
2. **Watermark outro-card gate** — `card_start` was computed from the audio-space
   accumulator, leaving ~4.8s of real narration video unwatermarked before the outro card.
   **Fixed** by ffprobing `pre_watermark.mp4`'s actual duration instead
   (`ffprobe_duration()`).
3. **Item-overlay window end** — same shape, caught while fixing #2, fixed the same way
   before it became reachable.

**The rule:** any accumulator built from `sum(audio_duration + CLIP_EXTRA)`, or
`get_audio_duration()` alone, is audio-space and must never be compared against or
substituted for a real rendered timeline value. Need the real video length? `ffprobe_duration()`
already exists — reuse it, or read `video_start`/`video_end` off a scene already stamped by
`write_video_timeline()`.

### 6b. ffmpeg filter chains — diff against Shorts, don't eyeball

Two separate bugs, identical shape: an ffmpeg filter silently defaulting to something
unexpected, invisible in normal playback, both inherited unmodified from a different project
this file was originally adapted from, and in **both** cases Shorts' `stitch_video_complete.py`
already had the correct form for the identical operation:

- **`mix_background_music()`'s `amix` filter** — `weights=4 1` with no `normalize=0` meant
  `amix` divided every input by the weight sum (5) *on top of* `bgm_volume`, making a
  configured `0.1` (-20dB) actually render at ≈-34dB — inaudible under narration. Fixed by
  dropping `weights=` and adding `normalize=0`, matching Shorts' formula exactly.
- **Same function, sample rate** — no explicit `-ar` meant `loudnorm`'s internal true-peak
  oversampling left the output at an unusual 96kHz despite both real inputs being 44100Hz.
  Didn't break playback, but badly confused `verify_output.py`'s Whisper-based sync check
  (Whisper's own decode got thrown off, reporting a spurious, steadily *growing* desync).
  Fixed by adding explicit `-ar 44100 -ac 2`, again matching Shorts' already-correct version.

**Any new ffmpeg chain ported into this file should be diffed against Shorts' equivalent
function line by line**, not just read for apparent correctness — that's twice now Shorts was
right and the ported version wasn't.

### 6c. Per-clip audio padding (`apad`) — fixes a real, if rarely visible, corruption

Every clip's video renders for `audio_duration + CLIP_EXTRA`, but originally left its audio
input unpadded — each clip's real audio was `CLIP_EXTRA` shorter than its own video.
Concatenating ~120 such mismatched clips wrote a container whose audio `duration_ts` metadata
didn't match its real decoded sample count: a **bounded** read (explicit `ffmpeg -t`, or
normal seeking playback) was unaffected, but an **unbounded** decode-to-EOF read (a plain
`pydub` whole-file load, `ffmpeg -i ... -vn out.wav` with no `-t`) silently compressed the
timeline and stopped early. Confirmed as a real, if narrow, ingest risk: a straight-through
decode (what `ffmpeg` does by default without seeking) is exactly this failure mode. Fixed at
the source — `build_clip_from_image()`/`build_clip_from_video()` now pass `-af apad`
alongside their existing `-t {audio_duration + CLIP_EXTRA}`, padding each clip's audio with
silence out to its own video length before concatenation. This incidentally also fixed a
second bug sharing the same root cause: BGM dropping to **explicit digital silence** (not
just a level drop) at every clip boundary, because `amix` had no BGM to mix against during
the audio gap.

**If you touch `concatenate_clips()`, `build_clip_from_image()`, or
`build_clip_from_video()`,** re-verify this — `tests/test_window_dbfs.py` pins the bounded-
read behavior, but the concat-metadata and BGM-dropout bugs themselves need real multi-clip
concatenation to reproduce and have no synthetic regression test.

### 6d. Caption and watermark rendering

`burn_srt_captions()` — bottom-third position (`Alignment=2, MarginV=40`), plain SRT (not
Shorts' karaoke `.ass` path). Font size is a `channel_dna` value (`caption_fontsize`, 28 as
of 2026-08-11, lowered from an untuned 36 placeholder after review found it too dominant on a
10-minute video). **Line-wrap width and words-per-caption are not independently
configurable** — they come from `generate_srt.py`'s `split_caption_entries()` (shared file,
hardcoded `MAX_LINE_CHARS = 55`, tuned for Shorts' 1080px-wide format). Changing that would be
a third edit to a shared file — deliberately not done without an explicit decision (§9).

`add_watermark()` — `drawtext`, position from a 4-way map (`bottom-left`/`bottom-right`/
`top-left`/`top-right`), resolution-agnostic (computed from ffmpeg's own `w`/`h` vars). Takes
an optional `card_start` that gates the drawtext off past that timestamp
(`enable='lt(t,card_start)'`) — used to stop the pipeline watermark before the outro card,
which already bakes its own `@aeoniumglow` credit into the asset (avoids a redundant double
watermark).

---

## 7. Image generation: `generate_images.py`

### 7a. Shot building — the grouping abstraction

Scenes sharing a `visual_group_id` (or, absent one, each scene's own `id`) collapse into one
**shot** — one generated image, shared across every member scene. This is what makes both
sentence-level grouping (narrative default, `auto_split_scenes.py`) and item-level grouping
(listicle, `stamp_items.py`) work through the identical downstream code: nothing past the
shot-building step knows or cares which grouping strategy produced the groups.

### 7b. Prompt resolution priority

`build_prompt_map()` resolves, per shot, in order: `override_prompt` (from
`--prompts-file`/`prompts_review.json`) → `auto_prompt` (same file) → a legacy `"prompt"` key
→ OpenAI auto-generation (batch call across every shot missing a prompt, for cross-scene
variety awareness, then a per-shot individual retry for anything the batch call dropped).
**A missing `auto_prompt` fallback in this chain was a real, serious bug** (see §9) — the
fallback chain order matters and should not be "simplified."

### 7c. Validation and retry

`validate_and_fix_shots()` runs a programmatic pass over every auto-generated (not
human-override) prompt: species-name validation (`names_species()`, swaps unrecognized names
to an approved subject — the listicle hazard from §5), a setting-overuse check
(`ceil(total/3)`, flags one physical setting dominating too many shots), and DNA-driven
`validation` rules (subject-reference pattern, action/reversal/hallucination checks — all
rule *data* in `channel_dna`, the rule *engine* itself is subject-independent Python, proven
portable by a throwaway knife-domain DNA smoke test that needed zero prompt-generation code
changes). **No species-overuse equivalent exists** — one species can dominate 60%+ of B-roll
shots with nothing flagging it; this has happened for real twice on Etiolation_S1 (once at
the original dry-run: Echeveria elegans ~24/36 shots; again during the later review pass:
flowering Kalanchoe blossfeldiana and repeated Sedum rubrotinctum). Caught by human review
both times, not by the pipeline.

### 7d. Prompt-craft patterns worth knowing, not just reading once

- **Cross-sections/cutaways have a strong training prior toward food** — "a cross-section of
  [species]" reliably renders as fruit (a kiwi, once, literally). Fix: anchor the subject and
  its distinguishing morphology **before** framing ("a cut stem of *<species>*, dense uniform
  fleshy interior, no segments or seeds" — not "a cross-section of..."), and name the specific
  failure mode in the negatives, not just generic ones.
- **Shape/geometry negatives can backfire** — "not a radiating rosette, no pointed leaves"
  still primes the model on ROSETTE and POINTED LEAVES and can make a render worse.
  Positive-only description of the correct geometry works better; if a shot still fails,
  changing the **shot type** (whole-plant → extreme macro on the distinguishing texture) is a
  more reliable fix than escalating negative language further.
- **Species/genus visual confusion is real and fixable the same way.** Ceropegia woodii
  (String of Hearts, small thick succulent leaves) rendered as Scindapsus pictus (satin
  pothos, larger thin papery leaves) on a correctly-worded prompt — houseplant training data
  likely conflates "heart-shaped leaf vine with silver marbling" toward the far more common
  pothos. Fixed with the same two-axis pattern: anchor distinguishing morphology first
  ("small, thick, plump, jellybean-thick... never large, thin, or papery"), name the specific
  confused species in the negatives ("not Scindapsus pictus, not satin pothos").
- **A shot angle can hide the very thing the shot needs to show.** A top-down framing of an
  etiolated (stretched) plant hides the elongated stem behind the pot rim — the single
  biggest fix for several "reads as healthy, not stretched" shots was switching to a low
  three-quarter side angle that shows the plant's full height, not stronger stretch-related
  wording.

---

## 8. Verification: `verify_output.py`

Two different caption-sync checks, deliberately not one — this split exists because a single
transcription-based check proved structurally unable to hit its own accuracy target, and the
fix was choosing better ground truth, not tuning the matching algorithm further.

- **`check_caption_structural()` — gating, fast, exact.** Re-derives each scene's expected SRT
  entries by calling `generate_srt.py`'s real `split_caption_entries()` (imported, never
  reimplemented — a reimplementation would throw false failures the moment the two drifted
  apart) against the manifest's current `video_start`/`video_end`, and asserts the SRT file on
  disk matches to ~50ms. Instant, no GPU, no transcription. Catches "SRT built from stale
  timestamps" and "`generate_srt.py` run before the remap step" exactly. **Known blind spot:**
  a bug *inside* `split_caption_entries()` itself would make both sides of the comparison
  agree and this check would pass regardless — covered from the other direction by
  `shorts_pipeline2/tests/test_generate_srt.py`, which exercises that function directly.
- **`check_caption_sync_advisory()` — never fails the run, coarse by design.** An independent
  WhisperX transcription smoke test — the only check that can catch `video_start` itself
  being wrong (the structural check can't, since both its sides derive from the same
  timestamps). Has a real, bounded, and *not fixable by better matching* noise floor
  (confirmed: 4.2s mean / 15.3s worst-case even with forced alignment, on a video
  independently confirmed correctly synced at seven separate direct-frame extractions). Root
  cause: `split_caption_entries()` chunks by fixed word count; a transcriber chunks by where
  it hears actual speech pauses — two different segmentation schemes answering different
  questions about where to draw a boundary, so even a perfect transcript pairs with the wrong
  SRT entry as soon as the schemes diverge, which happens quickly. **This is a mismatch
  between segmentation schemes, not a timing error — no amount of matching-heuristic tuning
  closes it.** Read a number from this check as sensitive only above ~25-30s (where it caught
  a real 96kHz-sample-rate bug at 40+ seconds), never as proof of a small real desync.

Other checks: BGM audibility (bounded-window RMS sampling — see §6c for why unbounded reads
are unreliable here), stream integrity, duration-vs-manifest (accounting for the outro card's
extra seconds), black/freeze frames (Ken Burns motion is filtered out of the freeze-frame
count via an 85%-of-clip-duration threshold), integrated loudness, and best-effort watermark/
item-overlay pixel presence (reports, doesn't fail).

---

## 9. Silent-substitution bugs — a pattern worth recognizing on sight

Four separate, independently-discovered bugs in this project share one shape: **the pipeline
runs successfully while quietly using content nobody approved**, with no error printed either
time:

1. A mangled `--prompts-file` path (unquoted Windows backslash) silently fell back to fresh,
   unreviewed auto-generation. Now hard-fails instead.
2. The species validator's retry pass silently rewrote a mis-transcribed species name to a
   *different* approved species (§5's listicle hazard) — not fixed at the code level (the
   validator is working as designed for narrative content), mitigated by mandatory human
   review at `--dry-run-prompts`.
3. `build_prompt_map()`'s fallback chain was missing an `auto_prompt` check, so every shot a
   human correctly left un-overridden silently re-triggered a second, independent,
   unreviewed OpenAI generation call — which had its own separate batch-matching bug that
   cross-contaminated content between shots. Fixed by completing the fallback chain (§7b).
4. `config_loader.py`'s nested-`"cta"` guard (§3) exists to prevent a fourth instance
   proactively, before it happened for real.

**If you're adding a new fallback chain, a new config-merge layer, or a new "generate content
unless X is already provided" code path anywhere in this pipeline, ask explicitly: what
happens if the thing that's supposed to prevent regeneration is spelled slightly wrong, uses
a different key name, or is present but empty?** That question is what would have caught all
three of the concrete bugs above before they shipped.

---

## 10. Where each script fits (reference table)

| File | Role |
|---|---|
| `run_pipeline.py` | Orchestrator. `--start-from {stage}` runs that stage onward; `script` stage is blocked (guard added 2026-08-08 — long-form scripts are hand-written and approved, not generated by this pipeline's own generator, which is still Shorts-shaped underneath) |
| `config_loader.py` | The config seam — see §3 |
| `console_encoding.py` | `ensure_utf8_console()` — UTF-8 stdout guard, needed because status-glyph prints (✅/⚠️/❌) crash with `UnicodeEncodeError` under redirected stdout (a pipe, a file, any non-interactive runner) on Windows' default console encoding. Imported by all 9 pipeline entry points as of 2026-08-08. |
| `generate_script.py` | **Not used for long-form scripting** — a near-unmodified Shorts copy, still Shorts-shaped in its docstring/prompt/length targets. Kept only because `run_pipeline.py`'s `--start-from script` guard needs something to exist to block; scripts are written by hand against `pipeline_script_prompt_template.md` instead. |
| `generate_override_prompts.py` | Standalone OpenAI-based prompt rewriter for an existing `prompts_review.json` — a manual tool, not part of the default `run_pipeline.py` flow |
| `generate_images.py` | Shot building, prompt resolution/generation, species/setting validation, actual image-provider calls (xAI → Replicate → Gemini, configurable order), normalization to 1920×1080 — see §7 |
| `make_contact_sheet.py` | Builds `{Project}/output/contact_sheet.png` — every generated image in narration order, labelled, with missing-image detection. The pixel-level check `--dry-run-prompts` (text-only) can't provide. |
| `stitch_video_longform.py` | Ken Burns per-clip render, concat, BGM mix, caption burn, watermark, item-number overlay, outro card — see §6. Requires Python 3.11 (`mutagen`). |
| `verify_output.py` | Automated post-stitch checks — see §8. Requires Python 3.11. |
| `upload_youtube.py` | YouTube upload (private draft), subtitle upload, optional thumbnail, description/chapters/pinned-comment generation (`build_description()`, `build_chapters()`, `build_pinned_comment()`) — see `USER_GUIDE.md` Phase D |
| `whisperx_transcribe_helper.py` | Tiny single-purpose subprocess script, run inside a *separate* venv (`transcription-tools/.venv`, GPU/WhisperX-dependent) by `verify_output.py`'s advisory check — kept separate because the main pipeline's Python environment has `openai-whisper`/`pydub`/`PIL` but not `whisperx` |
| `stamp_items.py` | Listicle-only manifest re-grouping by item — see §5 |
| *(shared, `shorts_pipeline2/`)* `auto_split_scenes.py` | WhisperX scene-splitting, sentence-adjacency grouping (narrative default), `strip_trailing_hallucinations()` |
| *(shared)* `stamp_manifest.py` | Writes audio-space `start`/`end`/`duration` onto scenes |
| *(shared)* `generate_srt.py` | SRT generation, `split_caption_entries()` word-wrap/chunking — see §6d, §8 |

---

## 11. Test suite

13 files, all in `tests/test_*.py` (note: glob-based test runners will silently skip a file
that doesn't match this pattern — this happened for real with a file originally named
`golden_output_test.py`, renamed 2026-08-08). Notable ones beyond the obvious per-feature
unit tests:

- **`test_golden_output.py`** — regenerates prompts for 12 real corpus projects and asserts
  byte-identical output against a committed baseline (`tests/golden_baseline.json`). Defaults
  to `--compare` against that baseline (an earlier version had a trivial-pass bug: the
  no-flags path asserted nothing and always exited 0 — fixed). Also fails loudly if the
  corpus itself can't be found, rather than silently comparing zero projects and reporting
  "identical."
- **`test_window_dbfs.py`** — pins `verify_output.py`'s bounded-read audio sampling behavior
  against a synthetic fixture reproducing the >538s unbounded-decode-truncation condition
  (§6c). Does **not** cover the concat-metadata or BGM-dropout bugs themselves — those need
  real multi-clip concatenation to reproduce and were verified by direct reproduction against
  real project assets instead.
- **`test_config_cta_guard.py`** — the nested-`"cta"` rejection (§3, §9).
- **`test_build_prompt_map.py`** — the `auto_prompt` fallback chain (§7b, §9).
- **`test_start_from_script_guard.py`** — the `--start-from script` block (§10).

Four validation rules in `generate_images.py` (`dehydration-vs-watering`,
`nocturnal-lighting`, `watering-in-progress`, setting-overuse) are **not exercised by any
project in the golden corpus** — verified separately by direct construction, but a
byte-identical golden-test pass doesn't actually exercise them (identity is trivially
satisfied when a rule never fires in either run). Treat these as needing a direct-
construction check for any future change to the validation engine, not a clean golden diff.

---

## 12. If you're about to touch a shared `shorts_pipeline2/` file

Don't, until you've re-read `CLAUDE.md`'s "two sanctioned edits" section and confirmed with
whoever owns this project that a third edit is warranted. The rule exists because a fix
landed only here silently stops benefiting Shorts (or vice versa), and because Shorts has an
independent test suite and production history this pipeline's changes don't get checked
against. If the edit is genuinely additive and backward-compatible (new optional parameter,
new fallback branch that only activates on a field long-form sets and Shorts never does), that's
the bar the first two sanctioned edits cleared — match it, don't lower it.
