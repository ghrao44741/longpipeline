# Phase 1 Report — longform_pipeline (16:9 core + narrative)

**Status: Phase 1 complete**, including the closeout pass (caption-desync fix, channel-scoped
assets, documentation). Verified end-to-end with a real test project. Two items are still
genuinely open — see §5.

---

## 1. What was built

A full sibling pipeline to `shorts_pipeline2/`, forked (not a `--format` flag), producing
1920×1080 landscape video instead of 1080×1920 vertical Shorts. See `longform_pipeline/CLAUDE.md`
for the fork/shared-file split, stage order, and traps — this report covers *what happened*
building and verifying it, not the reference documentation.

**Forked and adapted:** `generate_script.py`, `generate_images.py`,
`generate_override_prompts.py`, `upload_youtube.py`, `run_pipeline.py` (trimmed to a single
linear run, no yt/ig variant fork), `pipeline_config.json`, and `stitch_video_longform.py`
(moved from a stray copy of a different project's file, adapted: mascot overlay and CTA-card
logic removed, watermark and BGM-lookup ported in from `stitch_video_complete.py`).

**Shared, referenced in place (not forked):** `auto_split_scenes.py`, `stamp_manifest.py`,
`generate_srt.py` — imported cross-directory from `shorts_pipeline2/` so future fixes to these
land once, not twice.

**New in this pipeline:** `config_loader.py` (the channel_dna merge seam) and
`channel_dna/aeonium_glow.json` (+ `channel_dna/aeonium_glow/` for channel-scoped binary
assets — see §4).

---

## 2. Aspect-ratio and image-provider fixes

- Every hardcoded `"9:16 vertical"` prompt-template literal replaced with a
  `config["image_aspect_ratio"]`-derived phrase (`orientation_phrase()`/`camera_descriptor_block()`
  in `generate_images.py`). Verified via a dedicated unit test
  (`tests/test_aspect_phrase.py`) and in all real generated prompts.
- **Real bug fixed:** the Gemini image provider hardcoded `aspect_ratio="9:16"`, ignoring
  config entirely.
- **`crop_to_9x16()` generalized** to `crop_to_aspect(image_bytes, ratio_str)`.
- **Normalization added** (`normalize_image()`): every generated image is cropped-then-resized
  to `image_target_resolution` (1920×1080) regardless of provider — this is what actually
  guarantees correct output, not provider choice.
- **Image provider order made config-driven** (`image_provider_order` in `pipeline_config.json`),
  replacing a hardcoded xAI-first/name-string-matching scheme.
- **xAI/Grok fix, and a corrected assumption:** earlier drafting assumed xAI was locked to a
  1024×1024 square requiring crop-then-upscale. Corrected mid-build: xAI supports native
  `aspect_ratio` + `resolution` via `extra_body` (not a standard OpenAI Images API field).
  **Confirmed via direct API probe, not documentation**: a real call with
  `aspect_ratio="16:9", resolution="2k"` returned **2816×1584** — true native landscape, and
  actually *higher resolution* than Replicate Flux's 16:9 output (~1344×768). This validates
  making xAI primary as a genuine quality win, not just a preference call.
- **Concurrent image generation** ported from `interested_indian_pipeline/generate_images_flux.py`'s
  `ThreadPoolExecutor` pattern (`--workers`, default 4) — replaces one-request-plus-`sleep(11)`
  sequential generation.

---

## 3. Content-quality finding: cross-section prompts collide with a fruit prior

During real-prompt review for the test video, a "succulent stem cross-section" prompt rendered
as what looked like a sliced kiwi fruit — "photorealistic macro cross-section, green, radial"
is evidently a very strong training prior toward fruit imagery. Confirmed reproducible on a
direct retry with the same prompt.

**Fix (confirmed working on regeneration):** two-axis prompt rewrite —
1. Anchor the subject and its distinguishing morphology *before* camera framing ("a cut stem of
   *Echeveria elegans*, dense uniform fleshy interior, no segments or seeds, thick waxy outer
   skin..." — not "a cross-section of...").
2. Name the specific failure mode in the negatives ("no fruit, no seeds, no radial segmented
   pattern"), not just generic negatives.

This is documented as a standing trap in `longform_pipeline/CLAUDE.md` since cross-sections are
a real recurring need for this channel's content (rot-diagnosis videos want stem and soil
cross-sections).

---

## 4. Caption/video desync — found, root-caused, and fixed

**Found during Phase 1 end-to-end verification**, not anticipated in the original build brief.

**Root cause:** `stamp_manifest.py`'s cursor sums raw audio duration per scene
(`cursor += duration`), but `stitch_video_longform.py`'s actual rendered clips are each
`audio_duration + 0.5s` longer (render padding). `generate_srt.py` read the un-padded stamped
timestamps directly, so captions drifted out of sync with the video, worse in later scenes —
confirmed at ~6.5s off by scene 21 of 25 in the test video, using a mid-scene frame check (not
a boundary-adjacent frame, to rule out seek-precision artifacts).

**Not a new problem:** `shorts_pipeline2/generate_ass.py` already solves this identical bug for
Shorts' karaoke `.ass` captions (`build_video_timeline()`/`remap_time()`, `CLIP_EXTRA = 0.5`).
Long-form's plain-SRT caption path just didn't have the equivalent remap step yet. **This
closeout ported the existing fix, rather than designing a new one:**

1. `build_video_timeline()`/`remap_time()` ported verbatim into `stitch_video_longform.py`.
2. New `write_video_timeline(project_dir)` writes `video_start`/`video_end` onto each scene
   (alongside, not replacing, the existing audio-space `start`/`end`), run as a new step between
   stamping and SRT generation. Scenes missing `whisperx_start`/`whisperx_end` are skipped
   entirely (never written as `null`) rather than writing an invalid value.
3. **One additive edit to `shorts_pipeline2/generate_srt.py`** (the second and last sanctioned
   touch to that repo): prefers `video_start`/`video_end` per-scene when both are present and
   non-`None`, falling back to `start`/`end` otherwise. Shorts writes neither field, so its
   output is unchanged — confirmed via the full `shorts_pipeline2/tests/` suite passing,
   including new test cases added specifically for this: a no-`video_start` manifest producing
   identical output, a fully-remapped manifest using the new fields, a **mixed** manifest
   (some scenes remapped, some not) degrading cleanly per-scene rather than interleaving two
   timelines, and a partial-field (`video_start` present, `video_end` missing) manifest falling
   back safely instead of crashing.

**Verified fixed** by re-stitching the test video and re-extracting the same mid-scene frame
(t=94.5s) that previously showed the mismatch: the caption now reads "Fungi like Fusarium..."
correctly matching the on-screen fungal-soil visual (previously showed a mismatched
CAM-photosynthesis caption over that same visual). An early-video frame (t=45s, SCENE-008) was
re-checked to confirm no regression — still correctly synced.

**Byproduct — a known Shorts issue is now unblocked, not fixed.** Shorts' own uploaded SRT
subtitle tracks have this identical drift (documented separately in
`shorts_pipeline2/CLAUDE.md`'s BACKLOG, pre-existing, found while building this pipeline).
`generate_srt.py` already prefers `video_start`/`video_end`; fixing Shorts now just means
`stitch_video_complete.py` starting to write those two fields, using the remap
`generate_ass.py` already performs. **Not done in this pass** — it's a human content decision
(11 already-published videos would need re-upload to actually benefit), not a code call.

---

## 5. Open items

### Partially closed: WhisperX at real long-form scale

No raw narration `.wav` existed for the already-produced rot-rescue video — only finished
`.mp4` files. Extracted the audio track (341s / 5.7 minutes — genuine long-form length, though
only about half a typical 10-15 minute listicle target) and ran `auto_split_scenes.py`'s
scene-split stage alone (no image spend, no stitch) via the transcription venv.

**Result: the new flags exist for a real reason.** At the unchanged defaults
(`--compute-type` unset → `float16`, `--batch-size 16`), the run **failed with CUDA OOM**
partway through transcription. Retried with `--batch-size 4`: **succeeded**, correctly
producing 65 scenes ending at 341.295s (matching the source video's real duration exactly).

This is genuinely useful: it proves the flags work as designed and that they're *necessary*,
not just optional headroom — the pipeline's previous hardcoded defaults would not have survived
a real long-form video on this hardware. **Reported as partial closure, not full closure**,
because: (a) 5.7 minutes is still short of a real 10-15 minute listicle target, and (b) the
extracted audio track was the final *mixed* audio (narration + BGM) — fine for this OOM/load
check, but not a clean narration-only transcription-accuracy test.

### Genuinely open (tracked in `longform_pipeline/CLAUDE.md`'s BACKLOG)

- `subjects` (renamed from `approved_species`) still has only 9 entries — the highest-severity
  item for Phase 2, since the validator silently rewrites any unlisted species on retry.
  Scoped into Phase 1.5 (`BUILD_BRIEF_PHASE_1_5.md` §5), not started.
- Caption fontsize (36) and watermark fontsize (75) are untuned placeholders — reasonable
  starting points, never visually validated against real published content.
- The WhisperX mis-transcription bug class (this run: "Crassulacean" → "Crassulation";
  previously on Shorts: "mist" → "missed") has a structural fix available — feed the known
  `script.txt` as the alignment input instead of an ASR guess of it. Scoped as a future pass
  touching shared `auto_split_scenes.py`; not started.
- Phase 1.5 (`channel_dna` Layer-2 extraction + subject expansion) and Phase 2 (listicle mode)
  — specced, not started, Phase 1.5 blocks Phase 2.

---

## 6. Channel-scoped assets (added this closeout)

Design change, general beyond just BGM: channel-specific binaries now live in
`channel_dna/<name>/`, adjacent to `channel_dna/<name>.json` — a watermark logo, intro/outro
stings, and custom fonts will follow the same convention.

- Created `channel_dna/aeonium_glow/`, **moved** (not copied) `bgm.mp3` into it from the
  pipeline root.
- `config_loader.channel_assets_dir()` derives the assets directory from the already-resolved
  `channel_dna_file` path — no new config key.
- `stitch_video_longform.resolve_channel_asset()` is the general-purpose resolver; `find_bgm_path()`
  composes it with project-override and legacy-root fallback: `{project_dir}/{bgm_file}` →
  `{channel assets dir}/{bgm_file}` → `{scripts_dir}/{bgm_file}` (legacy, prints a loud
  deprecation warning if hit).
- **Fails loudly, not silently**, if `bgm_file` is declared in the DNA but resolves nowhere —
  raises `FileNotFoundError` listing every candidate path tried. The pipeline's prior behavior
  (inherited from the moved stitch script) rendered silently music-free instead; adding a third
  resolution candidate made silent failure more likely, not less, so this tightened rather than
  preserved that contract.
- **Verified via the re-stitched test project**: BGM resolved from
  `channel_dna/aeonium_glow/bgm.mp3` — confirmed directly via function call
  (`find_bgm_path()` returned the new path) and confirmed the legacy-root deprecation warning
  did **not** fire. Also directly tested the fail-loud path with a deliberately-missing
  filename — raised `FileNotFoundError` listing all three candidate paths, as designed.

Scope: long-form only. `shorts_pipeline2` is untouched — its stitch keeps its existing
root-relative BGM lookup; the two pipelines diverging here is expected, not a bug.

---

## 7. Documentation

- `longform_pipeline/CLAUDE.md` — new. This pipeline is a sibling of `shorts_pipeline2/`, not a
  child, so it inherited no project instructions until now. Covers the fork/shared-file split,
  the channel_dna seam, stage order, the two sanctioned `shorts_pipeline2` edits, carried-over
  and long-form-specific traps, and a BACKLOG seeded from this report's open items. Long-form
  sessions should run from here going forward.
- `shorts_pipeline2/CLAUDE.md` — the long-form "specced, not built" BACKLOG entry removed
  entirely (superseded by the new doc above); the `approved_species` expansion warning it
  contained was carried over into `longform_pipeline/CLAUDE.md`'s BACKLOG rather than lost. A
  new short entry records the two sanctioned edits (with an explicit note that the
  `generate_srt.py` branch is live long-form code, not dead code — no Shorts test covers it).
  The pre-existing drifted-CC-track entry is kept, with its "fix is easy" paragraph reworded to
  describe the mechanism (already built) rather than referring to this pass as future work.
- `.claude/skills/produce-longform/` — single copy, not duplicated into `shorts_pipeline2/`.

---

## 8. Test artifacts

Left in place for inspection, not cleaned up:
- `Longform_Test_Misting/` — the real end-to-end test project (18 images, stitched + captioned
  1920×1080 video, both pre-fix and post-fix manifests).
- `_whisperx_scale_test/` — scratch project from §5's WhisperX scale test (manifest only, no
  images/video — scene-split was the only stage run).
- `_probe_raw_scene001*.png`, `_check_frame_*.png` — raw provider-dimension probes and
  extracted verification frames from this report.

Nothing was uploaded at any point in Phase 1.
