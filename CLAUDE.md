# Aeonium Glow — Long-form (16:9) Pipeline (Claude Code Context)

**Channel:** @aeoniumglow — science-backed succulent care, long-form videos
**Pipeline root:** `C:\Bakcup_Asus\Aeonium_Glow\longform_pipeline\`
**This is a FORK of `../shorts_pipeline2/`**, not a `--format` flag on it. Read the next
section before touching any file here — the fork/shared-file split is load-bearing.

Sessions doing long-form work should run from **this** directory, not `shorts_pipeline2/` —
this file is the one they'll actually load.

**Full technical spec:** `BUILD_BRIEF.md` (Phase 1 — core + narrative, built) and
`BUILD_BRIEF_PHASE_1_5.md` (channel_dna extraction + subject expansion, not started).
**Phase 1 build + verification findings:** `PHASE_1_REPORT.md`.
**To produce a video:** `.claude/skills/produce-longform/` — the one and only copy; do not
duplicate it into `shorts_pipeline2/`.

---

## Fork vs shared — which files are which, and why

| File | Status |
|---|---|
| `generate_script.py`, `generate_images.py`, `generate_override_prompts.py`, `upload_youtube.py`, `run_pipeline.py`, `pipeline_config.json`, `stitch_video_longform.py` | **Forked.** Copied from `shorts_pipeline2/` (or, for the stitch script, moved from a stray copy of a different project's file) and diverge freely. |
| `auto_split_scenes.py`, `stamp_manifest.py`, `generate_srt.py` | **Shared — referenced in place, never copied.** `run_pipeline.py`/`stitch_video_longform.py` invoke/import these across directories from `../shorts_pipeline2/`. |

**Why the second group stays shared:** forking them means a future fix lands in one pipeline
only. `auto_split_scenes.py` holds `strip_trailing_hallucinations()` (the WhisperX
trailing-artifact fix — see Shorts' `CLAUDE.md`); a copy here would silently drift out of sync
with fixes made there. Same reasoning for `stamp_manifest.py` and `generate_srt.py`.

Only **two** edits have ever been made to `shorts_pipeline2/` for this pipeline's sake, both
additive/backward-compatible (see below) — if you find yourself editing anything else in
`shorts_pipeline2/`, stop; that's off-spec.

---

## The channel_dna seam

Two files, two concerns — every forked script imports `config_loader.load_config()` instead of
reading either file directly:

```
pipeline_config.json        HOW THE MACHINE RUNS (subject-agnostic)
                             aspect ratio, provider order, scene timing, venv paths,
                             credentials_dir, channel_dna_file (which DNA to load)

C:\Bakcup_Asus\shared-tools\channel_dna\<name>.json
                            WHAT THE CHANNEL IS (subject-specific, brand)
                             voice, script style, visual style, watermark, YouTube
                             metadata, the approved subject list ("subjects", renamed
                             from Shorts' "approved_species")
```

⚠️ **`channel_dna/` moved OUT of this repo on 2026-08-14** — it is now at
`C:\Bakcup_Asus\shared-tools\channel_dna\`, beside the shared WhisperX venv. The `Merge_videos`
composer became a second consumer of the same DNA and the same `bgm.mp3` / `outro_card.png`;
whichever project held them the other had to reach across into its folder, and two copies drift.
Same reasoning and same destination as the WhisperX venv relocation, so no single project's folder
appears to own something two projects depend on.

**The move needed exactly one line of change** — `pipeline_config.json`'s `channel_dna_file`, kept
relative (`../../shared-tools/channel_dna/aeonium_glow.json`) so the whole `C:\Bakcup_Asus` tree
stays relocatable. Nothing else: `_resolve_dna_path()` already honoured absolute paths and joined
relative ones against `scripts_dir`, and `channel_assets_dir()` **derives** the assets folder from
that pointer, so `bgm_file` and `cta.outro_card.asset` (bare filenames) followed automatically.
All 13 tests pass after the move — note 4 of them need Python 3.11 for `mutagen`.

**The shared folder is not a git repo**, so the DNA is no longer versioned by this pipeline's
history. Worth `git init`-ing there if the DNA starts changing often.

**Rule of thumb: if a viewer would notice the change, it belongs in DNA.** `config_loader.py`
shallow-merges the DNA dict over the base config (DNA wins on collision) and returns one flat
dict — every `config.get("some_key")` call site is unchanged regardless of which file the
value actually lives in.

**Channel-scoped assets** (binaries, not JSON) live in `<channel_dna>/<name>/`, adjacent to
`<channel_dna>/<name>.json` — e.g. `.../channel_dna/aeonium_glow/bgm.mp3`. A DNA key naming an asset
(`bgm_file`) holds a bare filename resolved against that directory via
`config_loader.channel_assets_dir()` / `stitch_video_longform.resolve_channel_asset()`. Don't
move assets back to the pipeline root — a per-project override still works
(`{project_dir}/{bgm_file}`), and a legacy root fallback exists but prints a loud deprecation
warning if hit. A declared-but-unresolvable asset **fails loudly** (raises), not a silent
music-free render — this was a real, previously-shipped failure mode (see `PHASE_1_REPORT.md`).

If you're extracting more brand rules into DNA (Phase 1.5's job — see
`BUILD_BRIEF_PHASE_1_5.md`), this is the seam they land on: **generic engine, specific DNA.**

---

## Stage order

```
script → voiceover → scenes → images → stitch → upload
```

No `--variants` fork (unlike Shorts — long-form has no yt/ig split) and no `--format` flag yet
(narrative vs listicle — deliberately not built until Phase 2). `--start-from` runs that stage
and everything after; there's no way to run a single stage via `run_pipeline.py` — call the
stage's own script directly:

```powershell
python run_pipeline.py --project MyVideo --start-from images --skip-upload
python stitch_video_longform.py --project MyVideo
python generate_images.py --project MyVideo
```

⚠️ **Stitching requires Python 3.11** (the only interpreter here with `mutagen`):
`C:\Users\Girir\AppData\Local\Programs\Python\Python311\python.exe`

⚠️ **`generate_script.py`'s approval gate uses `input()`** — needs a real terminal, same as
Shorts.

---

## The two sanctioned edits to `shorts_pipeline2/`

Both additive; Shorts behavior is unchanged either way.

1. **`auto_split_scenes.py`** gained optional `--compute-type` / `--batch-size` flags,
   defaults unchanged (`float16` / `16`). A 10+ minute long-form narration is far more
   transcription load than a 60-90s Short.
2. **`generate_srt.py`** prefers `scene["video_start"]`/`["video_end"]` over
   `scene["start"]`/`["end"]` when both are present and non-`None`, falling back per-scene
   otherwise. Shorts writes neither field, so it always hits the fallback — **this branch is
   not dead code**, long-form's stitch depends on it to keep captions in sync (see next
   section). No Shorts test covers it; don't remove it as unreachable without checking here
   first.

---

## Long-form-specific traps found in Phase 1

**Captions come from plain SRT here, not the karaoke `.ass` path Shorts uses.**
`stitch_video_longform.py` burns bottom-third SRT captions (`Alignment=2, MarginV=40`), not
Shorts' 4-word-flash centered karaoke style.

**The caption/video desync bug — found and fixed in Phase 1 Closeout.** `stamp_manifest.py`'s
cursor sums raw audio duration; the actual rendered video clips are each `+0.5s` longer
(render padding, `CLIP_EXTRA`). Uncorrected, captions drift out of sync with the video,
worse in later scenes (confirmed ~6.5s off by scene 21 of 25 in testing). Fixed by porting
`build_video_timeline()`/`remap_time()` from `shorts_pipeline2/generate_ass.py` (which already
solved this identical problem for Shorts' karaoke captions) into
`stitch_video_longform.write_video_timeline()`, which writes `video_start`/`video_end` onto
each scene after stamping, consumed by the `generate_srt.py` edit above. If you ever see
captions drifting again, check this chain first before assuming a new bug — it's an easy
mechanism to accidentally bypass (e.g. by calling `generate_srt.py` before the remap step runs).

**Image-generation content trap: subject/framing collisions with strong training priors.**
A "succulent stem cross-section" prompt rendered as a sliced-kiwi-fruit cross-section on first
try — "photorealistic macro cross-section, green, radial" is a very strong prior toward fruit.
Fixed by (1) anchoring the subject and its distinguishing morphology *before* the camera
framing in the prompt ("a cut stem of *<species>*, dense uniform fleshy interior, no segments
or seeds..." — not "a cross-section of..."), and (2) naming the specific failure mode in the
negatives ("no fruit, no seeds, no radial segmented pattern"), not just generic negatives.
Cross-sections/cutaways are a standing need for this channel (rot-diagnosis content wants
stem and soil cross-sections), so this will recur — apply the same two-axis fix whenever a
prompt uses cross-section/cutaway framing.

**BGM was inaudible in every long-form video shipped before 2026-08-07 — `amix`'s default
`normalize=1` silently divides by the weight sum.** `mix_background_music()` came in with this
file from the Interested Indian project's own stitch script and was never reconciled against
Shorts' already-correct formula. With `weights=4 1` and no `normalize=0`, `amix` divides every
input by 4+1=5 on top of `bgm_volume` — a configured `0.1` (-20 dB) actually renders at
`0.1/5 ≈ 0.02` (-34 dB), inaudible under -14 LUFS narration. `bgm_volume` was never the bug; the
mix formula was. Fixed by dropping `weights=` and adding `normalize=0`, matching
`shorts_pipeline2/stitch_video_complete.py`'s formula (verified identical, confirmed audible
there at the same 0.1 volume). Caught only because `verify_output.py`'s RMS-in-the-silent-tail
check made "under the voice" vs. "silently absent" measurable instead of a by-ear judgment call.
If BGM ever sounds too quiet again, check for `normalize=1` (the default) creeping back in
before assuming `bgm_volume` needs raising.

**Same function, second bug found the same day: `mix_background_music()`'s output declared an
unusual 96000Hz sample rate with no explicit `-ar` anywhere in the chain, even though both real
inputs (`narration.wav`, `bgm.mp3`) are 44100Hz — `loudnorm`'s internal true-peak oversampling
leaves the output rate unspecified, and ffmpeg let 96000Hz through.** This did NOT break real
playback — the container's own video/audio stream durations stayed self-consistent (~584.03s vs
~584.09s, no meaningful mismatch), and four separately extracted frames at real timestamps
throughout the video all showed correct caption sync. But it did badly confuse
`verify_output.py`'s Whisper-based caption-sync check: Whisper's own audio decode/timing
(unrelated to WhisperX's forced alignment, which this pipeline uses elsewhere) got thrown off by
the unusual rate and reported a spurious, steadily GROWING "desync" — up to 40+ seconds by
mid-video — that contradicted every direct-frame check. Confirmed as a measurement artifact, not
a real defect, only by extracting an actual frame at one of Whisper's claimed mismatch timestamps
and finding the burned caption exactly where the real narration order says it should be. Fixed by
adding an explicit `-ar 44100 -ac 2` to `mix_background_music()`'s output, matching
`shorts_pipeline2/stitch_video_complete.py`'s `mix_background_music()`, which already forces this
— the same "long-form's copy hadn't caught up to Shorts' already-correct version" pattern as the
`normalize=0` bug just above. If `verify_output.py`'s caption-sync check ever reports a large,
smoothly-growing (not sudden) offset again, check the audio stream's sample rate for something
non-standard before assuming the remap logic broke — a real desync from the original bug class
(`stamp_manifest.py`'s cursor vs. `CLIP_EXTRA` render padding) shows up as a jump correlated with
scene boundaries, not a smooth ramp uncorrelated with them.

**`verify_output.py`'s caption-sync check was redesigned into two checks (2026-08-08) after the
single transcription-based check proved structurally unable to hit its own accuracy target — the
fix was choosing the right ground truth, not tuning the matching algorithm further.** The
original design compared an independent transcription (Whisper, then WhisperX forced alignment)
against the burned SRT and had a real, bounded noise floor even at its best — several seconds
mean, ~8-15s worst-case — that did NOT indicate real desync: Etiolation_S1's actual video was
independently, manually confirmed correctly synced at **seven** separate direct-frame
extractions, including at every "worst offset" timestamp the check ever reported across three
different matching-algorithm iterations. Raising the threshold to stop the noise was explicitly
rejected — a 15-20s threshold would have passed the *original, real* ~6.5s desync bug this whole
effort exists to catch, making the check blind to its own motivating case.

The actual insight: **the ground truth for caption sync is the manifest, not a transcript.**
`stitch_video_longform.py` placed every clip using `video_start`/`video_end`; whether the SRT on
disk reflects those CURRENT values is exact, arithmetic, and requires no transcription at all.
Split into:
- **`check_caption_structural()` — gating.** Re-derives each scene's expected SRT entries via
  `generate_srt.py`'s own `split_caption_entries()` (imported from `shorts_pipeline2`, not
  reimplemented) against the manifest's current `video_start`/`video_end`, and asserts the SRT
  file on disk matches to ~50ms. Instant, no GPU. Catches the SRT-built-from-stale-timestamps bug
  class and the "`generate_srt.py` run before the remap step" ordering bypass exactly. Requires
  Python 3.11 (`generate_srt.py` imports `mutagen` at module level even though
  `split_caption_entries()` itself never touches it) — same interpreter `stitch_video_longform.py`
  already requires.

  Importing the real function rather than reimplementing it was deliberate: it isolates what's
  under test (which timestamps `generate_srt.py` actually chose) from what's shared (how a scene
  subdivides into caption entries) — a reimplementation would throw false failures the moment the
  two drifted apart, for no real bug. The tradeoff is a narrow, known tautology blind spot: a bug
  *inside* `split_caption_entries()` itself would make "expected" and "actual" agree (both sides
  derive from the same function) and this check would pass regardless. That gap is covered from
  the other direction, not this one — `shorts_pipeline2/tests/test_generate_srt.py` exercises
  `split_caption_entries()` directly and independently.
- **`check_caption_sync_advisory()` — never fails the run, and is not a fine-grained check.**
  The transcription-based check, relabeled and demoted to a **GROSS-FAILURE DETECTOR**. Its own
  measured noise floor on Etiolation_S1 (4.2s mean, 15.3s worst-case, even with WhisperX forced
  alignment) is too coarse to reliably surface a real `video_start` error small enough to be
  plausible — such an error would be buried in the noise, not a demotion from usefulness, just an
  honest statement of what this check can and can't resolve. Read it as sensitive above roughly
  25-30s, where a real problem stands clearly outside the noise floor — exactly the regime that
  caught the 96kHz sample-rate bug at 40+ seconds. Reports its number (informational threshold
  15s) but never gates.

**Root cause of the transcription check's noise floor, recorded so nobody retunes it expecting a
different result: SEGMENTATION MISALIGNMENT, not intra-entry interpolation error.**
`split_caption_entries()` chunks each scene by WORD COUNT (fixed-width wrapped lines); a
transcriber chunks by where it hears actual pauses in SPEECH. SRT entry #K and transcript segment
#K are answering different questions about where to draw a boundary, so even a perfectly-synced,
word-for-word-correct transcript pairs up with the wrong SRT entry as soon as the two chunking
schemes diverge — which happens quickly. This is a mismatch between two *segmentation schemes*,
not a timing error, and no amount of matching-heuristic tuning closes it.

If `verify_output.py`'s advisory check ever reports a large, smoothly-growing (not sudden) offset,
also check the audio stream's sample rate for something non-standard (see the `-ar 44100` trap
above) before assuming anything about timing — a real desync from the original bug class
(`stamp_manifest.py`'s cursor vs. `CLIP_EXTRA` render padding) would show up as the STRUCTURAL
check failing outright, not as a smooth ramp in the advisory one.

**New trap, the pattern behind both audio bugs above: when porting an ffmpeg filter chain between
pipelines, diff it against the Shorts equivalent filter by filter, not just eyeball it.** Two
bugs this session had the identical shape — an ffmpeg filter silently defaulting to something
unexpected (`amix` normalizing by the weight sum; `loudnorm` leaking a 96kHz internal rate upward
with no explicit `-ar` to pin it), both invisible in normal playback, both inherited unmodified
from the Interested Indian stitch script this file was adapted from, and in **both** cases
Shorts' `stitch_video_complete.py` already had the correct form for the identical operation. That
is twice now the Shorts version was right and the ported one wasn't. The next time an ffmpeg
chain gets ported into this file (or any new one), diff it against Shorts' equivalent function
line by line before trusting it.

**Trap: audio-space vs. video-space is not the same timeline, and confusing them has now
caused three separate bugs (2026-08-08) — check any new one against this list first.**
`sum(audio_duration + CLIP_EXTRA)` — the running total every per-scene loop in this codebase
naturally reaches for — is NOT the real rendered video length. It's audio-space: a sum of
narration durations plus a fixed per-clip pad. The REAL video timeline is whatever
`video_start`/`video_end` (written by `write_video_timeline()`) or a direct `ffprobe` of the
actual render says, and the two drift apart by `CLIP_EXTRA` plus frame-quantization, per
clip, cumulatively — small on a short project, seconds on a long one. Three bugs, same shape:

1. **The original caption desync** (Phase 1 Closeout) — `stamp_manifest.py`'s cursor was
   audio-space; captions need video-space. Fixed by `write_video_timeline()`'s remap.
2. **The watermark gate's `card_start`** (2026-08-08) — computed from `run_stitch()`'s
   audio-space `total_duration` accumulator instead of the real render; left 4.8s of real
   narration video unwatermarked before the outro card on Etiolation_S1. Fixed by ffprobing
   `pre_watermark.mp4`'s actual duration (`ffprobe_duration()`, `stitch_video_longform.py`)
   instead of reusing the accumulator.
3. **The item-overlay `total_duration`** (2026-08-08, caught while fixing #2) — `main()`
   summed `get_audio_duration() + CLIP_EXTRA` and handed it to
   `build_item_overlay_windows()`, which compares it against video-space `video_start` values
   for a trailing item's window end. Not reachable on Etiolation_S1 (its trailing content
   isn't itself the last listicle item), but fixed the same way before it became reachable and
   silently truncated a real item's overlay window on some future project.

**The rule going forward: any accumulator built from `sum(audio_duration + CLIP_EXTRA)` (or
`get_audio_duration()` alone) is audio-space and must never be compared against, or
substituted for, a real rendered timeline value.** If code needs the real video length, get it
from `ffprobe` (`ffprobe_duration()` already exists in `stitch_video_longform.py`, reuse it)
or from `video_start`/`video_end` on a scene already written by `write_video_timeline()` — not
from re-summing audio durations. This is worth checking any time a new duration-consuming
calculation is added near the stitch pipeline, not just waiting for the fourth instance to
surface on its own.

---

## Carried-over traps (same as Shorts — still apply here)

- **`--dry-run-prompts` OVERWRITES `prompts_review.json`.** Not a read-only probe. Back up
  hand-written `override_prompt` values first.
- **`--prompts-file` needs an absolute path.** A relative path gets joined onto the project
  dir and won't resolve. A bad path now hard-fails instead of silently falling back to
  fresh (unreviewed) auto-generated prompts.
- **Quote Windows paths in Git Bash** — unquoted backslashes get mangled by shell escaping.

---

## BACKLOG

- **New bug class, root-caused and closed same-day: `edge-tts --file` inserts a real ~1.1s
  pause at ANY newline in the input text, including one that lands mid-sentence from pure
  human-readable word-wrapping — not just at paragraph breaks (2026-08-15, Gravel_S1).**
  Found from a real, repeated "the video feels like it's pausing" complaint that survived a
  full re-diagnosis of `CLIP_EXTRA`/scene-cut-density (that diagnosis was real and correctly
  explained the *finished-video* pacing question it was asked about, but was not the cause
  of *this* complaint — see below) and a second cause the user correctly suspected but I'd
  initially dismissed: the *raw, unstitched* narration audio itself, before any of the
  pipeline's own scene-splitting or `CLIP_EXTRA` logic ever touches it.

  **Isolated with a controlled before/after TTS test, not inferred:** `"The person who\npotted
  it was being careful."` (embedded newline, from Gravel_S1's actual `script.txt`, itself
  copied from a ~90-char-wrapped vault markdown doc) rendered with a genuine, measured 1.08s
  silence between "who" (ends 5.874s) and "potted" (starts 7.035s) — confirmed both via
  `ffmpeg silencedetect` on the real per-scene mp3 and via WhisperX's own word-level
  timestamps. The identical text with the newline removed (`"The person who potted it was
  being careful."`, one line) rendered 1.2s shorter with zero internal gap. Scaled across the
  whole script: Gravel_S1's `script.txt` had 77 mid-sentence line-wraps (lines not ending in
  `.?!` immediately followed by another non-blank line within the same paragraph); removing
  all of them shortened the raw narration from 657.7s to 567.4s — a 90.3s reduction, matching
  77 × ~1.17s almost exactly. **Etiolation_S1's `script.txt` has zero mid-sentence wraps**
  (whichever way it happened to be authored, not from any check that existed at the time) —
  this is the actual, sole reason it never showed this problem, not sentence length, not
  scene count, not `CLIP_EXTRA`. A prior attempt to fix Gravel_S1's pausing by rewriting to
  shorter sentences made the *unrelated* `CLIP_EXTRA`-density problem worse (more, more
  frequent scene cuts) while doing nothing for this bug, because the short-sentence rewrite
  carried the same word-wrapping habit and still had 72 mid-sentence wraps of its own.

  **These are two distinct, independently-real bug classes that happened to surface in the
  same session on the same project — do not collapse them into one fix or assume closing one
  closes the other:**
  1. `CLIP_EXTRA` render-padding density (existing, documented above in this file) — affects
     only the *finished, stitched* video's pacing, scales with scene-cut frequency, and has
     nothing to do with raw narration audio.
  2. This newline bug — affects the *raw narration audio itself*, upstream of every later
     pipeline stage, entirely independent of scene count or `CLIP_EXTRA`. A perfectly-tuned
     `CLIP_EXTRA` value cannot fix a pause that's already baked into the TTS output.

  **Also worth recording: an audio-only preview (narration + BGM mixed, real `CLIP_EXTRA` gap
  timing, zero images/video) is a legitimate, fast, free way to sanity-check pacing before
  spending on image generation** — built ad hoc this session (concat each scene's mp3 padded
  with `apad=pad_dur=0.5` via one `ffmpeg -filter_complex`, then mixed under BGM with the
  exact same `loudnorm`/`amix normalize=0` formula `mix_background_music()` uses, just mapped
  to audio-only output instead of `-map 0:v:0`). This is also what actually surfaced bug #2
  above — the raw narration by itself (no BGM) made the pause obvious; the BGM-mixed preview
  confirmed it was still audible even under music, which is what made clear this wasn't a
  masking/perception question and needed a real fix, not a `CLIP_EXTRA` retune.

  **Fixed at the source, not just patched on Gravel_S1:** `check_script.py` (new, forked file,
  this pipeline only) checks any project's `script.txt` for (a) mid-sentence line wraps and
  (b) the pipeline's own existing "no markdown/parentheses/symbols in spoken text" constraint
  (em/en dash, semicolon, colon — auto-fixed to a plain sentence break; markdown/brackets —
  flagged only, needs a human decision). `--fix` backs up the original to
  `script.txt.pre_check_backup` before rewriting in place. Wired into `run_pipeline.py`'s
  `run_voiceover()` as a hard gate — a script with unresolved issues fails loud before
  `edge-tts` ever runs, rather than silently shipping another ~90s of dead air; catching this
  before generation is what makes it cheap (`edge-tts` is free/local) instead of something a
  human has to catch by ear in a finished video. Verified the gate itself doesn't introduce a
  new failure: the subprocess call capturing `check_script.py`'s own stdout needed an explicit
  `encoding="utf-8", errors="replace"` — the same Windows-cp1252-default class of bug
  `console_encoding.py` exists to prevent for direct printing, just manifesting instead as a
  `subprocess.run(text=True)` decode failure on captured child-process output containing the
  emoji status glyphs (✅/❌/⚠️) this codebase prints everywhere. Confirmed both directions: a
  script with real issues blocks with a clear fix command, a clean script passes straight
  through to `edge-tts` with no false block.

- **Test suite is 13 files, all passing, all in `tests/test_*.py` — this is the authoritative
  count (2026-08-08).** Third different number given for this in the same thread (12, then
  13-maybe, now confirmed 13) — the earlier undercounts were `golden_output_test.py` not
  matching the `test_*.py` glob, so it was invisible to any glob-based run. Renamed to
  `tests/test_golden_output.py`; nothing else changed in it. `tests/` has no separate
  `README.md` inventory to also update — this line is the count.

  **UTF-8 console guard was missing from 5 of 9 pipeline files, not one** — found because
  `test_outro_card.py`, `test_build_prompt_map.py`, and `test_golden_output.py` (then still
  `golden_output_test.py`) all crashed with `UnicodeEncodeError` under **redirected stdout**
  (a pipe, a file, any CI/script runner) despite passing fine in an interactive console. Four
  files had already picked up an inline copy of the guard one at a time, each only after
  something crashed on it (`run_pipeline.py`, `verify_output.py`, `make_contact_sheet.py`,
  `upload_youtube.py`) — the other five (`stitch_video_longform.py`, `generate_images.py`,
  `generate_script.py`, `stamp_items.py`, `config_loader.py`) had none at all. Priority case:
  `stitch_video_longform.py`'s `resolve_outro_card()` — its missing-asset path is documented
  elsewhere in this file as deliberately fail-**soft** (warn and proceed, unlike
  `find_bgm_path()`'s fail-loud contract), specifically so an unattended run degrades instead
  of stopping — but without the guard, it crashed on its own warning under redirected stdout,
  defeating that design in exactly the unattended case it exists for.

  Consolidated into a shared `console_encoding.py` (`ensure_utf8_console()`) instead of a
  fifth copy-paste, and wired into all 9 files — the four with inline copies now import the
  shared helper too, so there's one place to fix if this needs to change again. Verified with
  stdout actually piped to a file (not `-X utf8`, not `PYTHONIOENCODING` set — the real
  condition an automated runner hits): all 13 tests pass, and `resolve_outro_card()`'s warning
  prints and degrades correctly instead of crashing. Any new pipeline file should import
  `console_encoding.ensure_utf8_console()` and call it near the top, before any print with a
  status glyph — that's now the pattern, not a per-file decision.

  **Golden comparison re-run after the guard rollout, since `generate_images.py` was one of
  the 9 files touched: ✅ IDENTICAL, all 12 corpus projects match byte-for-byte
  (`tests/test_golden_output.py`).** Confirms `ensure_utf8_console()` is genuinely a
  print-only change with zero effect on prompt generation or validation output — the
  evidence, not just an assumption, that touching 9 files for this changed no behavior.

  **`test_golden_output.py` had two trivial-pass paths, closed 2026-08-08 the same day the
  rename made the file actually reachable by the suite.** (1) Its bare/no-flags path — what
  any glob-based runner invokes — hit neither `--save` nor `--compare`, printed a dump, and
  exited 0 unconditionally: it could not fail, so it reported green while asserting nothing.
  Now defaults to `--compare tests/golden_baseline.json` (the committed baseline); the old
  unconditional-dump behavior is still available, but only via an explicit `--dump` flag that
  says what it does. (2) A missing or moved `CORPUS_ROOT` skipped every project, left
  `results` empty, and `--compare` printed `"IDENTICAL — all 0 project(s) match"` — a broken
  corpus path read as a pass. Now fails loudly (exit 1, names the missing projects) whenever
  `len(results) < len(CORPUS_PROJECTS)`. Same shape as the tautology blind spot already
  documented for `check_caption_structural()` — a check that cannot fail isn't measuring
  anything; this one is cheap to close now that it's actually in the suite.

- **Stitched containers write an inconsistent audio `duration_ts` — fixed in
  `verify_output.py`'s sampling, root-caused 2026-08-08, still open as a publish-blocking risk
  investigation below.** Found verifying the outro card against Etiolation_S1's real 602.6s
  render: `pydub.AudioSegment.from_file()` on the full captioned video returned only
  **537.983s** of audio against a container that reports 602.55s.

  **Corrected root cause (2026-08-08 — the first write-up of this was wrong and has been
  retracted; see `tests/test_window_dbfs.py`'s docstring and `verify_output.py`'s
  `_window_dbfs()` docstring for the current, verified explanation).** This is not a generic
  `pydub` length limit — a synthetic 600s 44100Hz stereo AAC fixture does not truncate, pydub
  reads it in full. `ffprobe -count_frames` on the real file finds exactly 23169 AAC frames
  (=538.0s) while the same audio stream's `duration_ts` claims 602.55s — the container's own
  metadata is internally inconsistent. Traced by direct reproduction with the real pipeline
  code (both a 6-clip small-scale rebuild and cross-checks against the full Etiolation_S1
  output) to `concatenate_clips()`: every per-scene clip from `build_clip_from_image()` /
  `build_clip_from_video()` renders its **video** for `audio_duration + CLIP_EXTRA` seconds but
  leaves its **audio** input unpadded, so each clip's real audio is `CLIP_EXTRA` (~0.5s)
  shorter than its own video — confirmed directly on one real clip (SCENE-006: video=3.633s,
  audio=3.141s, no padding). Concatenating ~120+ such mismatched clips via ffmpeg's concat
  demuxer + re-encode writes an audio `duration_ts` that doesn't match the real decoded sample
  count. Exactly where inside the demuxer's duration bookkeeping this gets miscomputed was not
  isolated further — bounding the symptom was enough for `verify_output.py`'s own needs, but
  the mechanism inside ffmpeg's concat demuxer remains an open detail.

  **Critical distinction, confirmed directly on the real file:** the audio is not actually
  missing. A **bounded** read (`ffmpeg` with an explicit `-t`, regardless of whether `-ss` is
  placed before or after `-i`) retrieves real, correct audio throughout the full 602.55s,
  including windows well past the 538s mark (verified: real non-silent signal at t=590-595s,
  identical whether extracted via `-ss` before or after `-i`). Only **unbounded** decode-to-EOF
  reads — `pydub`'s whole-file load, plain `ffmpeg -i ... -vn out.wav` with no `-t`, `ffprobe
  -count_frames` — stop early at the same real point (537.983s exactly, confirmed via a full
  unbounded decode of the real file). `check_bgm_audibility()`'s outro window used `len(audio)`
  from a full `pydub` load as if it were the true total duration, so it silently sampled a
  point ~64s *before* the real outro; its per-clip-tail loop had the same exposure. Every prior
  BGM-audibility run on a video this long had likely been silently under-sampling its last
  stretch, with no error or warning either way.

  Fixed by never loading the whole file unbounded: `_window_dbfs()` now extracts each needed
  window (at most ~18s, the outro card) directly via a **bounded** `ffmpeg -t` call into a
  small temp WAV first, then hands only that short clip to `pydub` — the same "extract a small
  piece via ffmpeg, only then hand it to a Python library" pattern `_crop_std()` already used
  for frame extraction. Total window duration comes from `audio_duration()` (ffprobe-based,
  already proven accurate throughout this file), never from a full-file `pydub` load.

  **Retracted:** an earlier version of this entry read Etiolation_S1's outro card as
  **-37.8 dBFS**, called it "noticeably quieter than the rest of the video's ~-19 dBFS mean,"
  and attributed that to "the looping `bgm.mp3` track's own dynamics." Both the comparison and
  the conclusion were wrong — -19 dBFS is the whole-video, narration-dominated mean, not the
  right baseline for a narration-free window. The correct comparison is against
  `verify_output.py`'s own BGM-only sample mean, **-34.1 dBFS**: the outro's -37.8 dBFS is only
  3.7 dB below that — normal variation across BGM-only windows, not evidence of anything. Do
  not re-derive "looped bgm.mp3 dynamics" from this data; there's nothing here that supports it.
  `verify_output.py`'s own "expect ~-20 to -30 dBFS" comment was similarly stale (assumed
  narration was mixed into the sampled windows, which by design it never is) and has been
  recalibrated to the real measured band.

  **Publish-blocking risk, root-caused exactly and fixed at the source (2026-08-08).** The
  arithmetic closes precisely: 2781 missing AAC frames × 1024 ÷ 44100 = 64.575s against a
  measured gap of 64.583s (Etiolation_S1's first captioned render); 64.575s ÷ 123 clips =
  0.525s/clip, matching `CLIP_EXTRA` (0.5s) plus frame-quantization. A full unbounded decode
  of the original file compressed the timeline rather than rendering the gap as silence —
  `ffmpeg -i captioned.mp4 -vn -c:a pcm_s16le full.wav` produced 537.983s of *concatenated*
  audio for a 602.5s video, i.e. a real, growing audio/video desync for any consumer that
  decodes straight through rather than seeking. Seeking (`-ss`) honors PTS and lands
  correctly, which is why bounded reads and normal playback looked fine — but that made this
  a genuine ingest risk, not a speculative one, since it's exactly what `ffmpeg` itself does
  by default on a straight-through decode.

  **Fixed at the source, not just bounded around:** `build_clip_from_image()` and
  `build_clip_from_video()` now pass `-af apad` alongside their existing `-t
  {audio_duration + CLIP_EXTRA}`, padding each clip's finite narration audio with silence out
  to its own video length instead of leaving it `CLIP_EXTRA` short. Confirmed on real
  Etiolation_S1 assets before the fix (SCENE-006: video=3.633s, audio=3.141s, unpadded) and
  after (video=3.633s, audio=3.641s, apad rounds to fill `-t`). Re-verified on a small-scale
  6-real-clip rebuild through the real `concatenate_clips()`: pre-fix, declared audio duration
  (18.25s) diverged sharply from actual decoded content (15.77s) against a 18.70s video;
  post-fix, all three converge to within ~85ms. **Re-stitched the full Etiolation_S1 on this
  fix (2026-08-08):** a full unbounded decode of the new captioned output now reads 604.09s —
  matching the real video length, not stopping early. `apad` did not need a remux/re-transcode
  band-aid afterward — because it pads each clip's audio to its own video length *before*
  concatenation, clip lengths (and therefore `video_start`/`video_end`, captions, chapters,
  item overlays) are completely unchanged; only `concatenate_clips()`'s input changed. This
  also incidentally tightened the caption-sync advisory check's own noise on the re-stitch
  (mean/worst offset dropped from 4.2s/15.3s to 1.0s/2.2s) — consistent with WhisperX
  previously being fed the same corrupted-duration file every other unbounded reader choked
  on; not a change to the check itself.

  **A second, distinct defect shared the same root cause: BGM silently cut to explicit digital
  silence (not just absence) at every clip boundary — ~123 dropouts across the video.**
  Probing around a real boundary (SCENE-041→042, `video_end≈180.28`) in 0.15s windows found
  narration-level audio, then BGM-only levels, then **no samples at all**, then BGM resuming —
  the packet gap itself, not a level drop. `mix_background_music()`'s `amix` inherits gaps from
  its narration input; with no narration packets during the per-clip gap, there was nothing for
  BGM to be mixed against and the output went to explicit silence there instead of continuing.
  The same `apad` fix closes this too, since it's the same underlying gap: with narration now
  continuous (silence-padded, not gapped), `amix` has BGM to carry through every pad. Re-verified
  on the re-stitch: the SCENE-041→042 boundary now transitions narration → BGM decay smoothly
  (-19.3 → -26.5 → -37.6 → -38.9 → -40.1 dBFS) with no drop to silence.

  `check_bgm_audibility()`'s clip-tail window assumed "guaranteed speech-free = BGM only,"
  which was false before this fix (the window could land inside the packet gap, reading
  explicit silence indistinguishable from "no BGM") and is genuinely true after it. Its
  expectation band was re-measured post-fix at ~-24.7 dBFS mean (was ~-34.1 pre-fix, dragged
  down by the gap-silence outliers).

  **This band was still wrong the first two times it was rewritten (2026-08-08) — third
  attempt, now fixed by not collapsing it at all.** Both earlier versions stated a single
  "typical" range for `samples`, but `samples` pools two genuinely different populations:
  clip-tail windows (right after a narration decay/room-tone tail, reads louder, ~-25 dBFS
  mean) and the outro card (the one point in the video that's BGM completely alone, reads
  quieter, ~-38 dBFS). A combined band either mismatched whichever population it was actually
  describing, or was too wide to mean anything. The code comment and the printed `detail`
  string in `check_bgm_audibility()` now state both bands separately instead of merging them —
  don't try to collapse this back into one range; that's exactly what produced the wrong
  number each previous time.

  **Same bug confirmed in `shorts_pipeline2/local_mp4_analyzer.py:46` — flagged to the user,
  deliberately not fixed at the time** (one-sanctioned-edit-at-a-time rule for that shared,
  separate production pipeline). **Fixed 2026-08-13**: both `shorts_pipeline2/local_mp4_analyzer.py`
  and the Aeonium Glow root `local_mp4_analyzer.py` now measure duration/levels via
  ffprobe/ffmpeg and windowed reads, exactly like this file's `_window_dbfs()`. This write-up
  remains the reference for the real root cause — don't let it get re-diagnosed as a generic
  pydub limit a second time.
  `apad` is a `stitch_video_longform.py`-only fix; nothing in `shorts_pipeline2/` was touched.

  **Watermark gate had a related audio-space/video-space bug of its own, caught before the
  re-stitch shipped it.** The outro-card watermark gate (`card_start`, added alongside the
  outro card itself) was originally computed from `run_stitch()`'s `total_duration`
  accumulator — `sum(audio_duration + CLIP_EXTRA)` per clip, i.e. audio-space — while the real
  render is video-space and drifts from that sum by frame-quantization on top of the
  `CLIP_EXTRA`-per-clip gap above. On Etiolation_S1 this put `card_start` 4.8s early,
  unwatermarking the last 4.8s of real narration video before the card. This is the exact
  audio-space-vs-video-space split already on record for the caption-desync fix, reappearing
  in a new spot. Fixed by ffprobing `pre_watermark.mp4`'s real duration instead of reusing the
  accumulator (`ffprobe_duration()`, new small helper in `stitch_video_longform.py`) — exact,
  no drift modeling needed. The same latent mixing existed in `main()`'s item-overlay
  `total_duration` (compared against video-space `video_start` values from
  `build_item_overlay_windows()`) — not reachable on Etiolation_S1 (its trailing content isn't
  itself part of the last listicle item), but fixed the same way while in this code, before it
  became reachable on a future project and failed silently there too.

  **Benign side effect, record so it isn't re-diagnosed: `avg_frame_rate` now reads a
  non-integer 29.975 (`542280/18091`) on the re-stitched output.** `r_frame_rate` is still a
  clean `30/1` — the encode is genuinely CFR 30, nothing wrong with the video stream itself.
  The video stream is 18076 frames = 602.53s while the container runs 603.05s, a ~0.5s gap —
  `apad` on the final clip overshoots slightly (it pads to fill `-t`'s duration and rounds up,
  same as the ~8ms-per-clip overshoot already noted on SCENE-006 above), so the audio is now
  marginally *longer* than the video — the mirror image of the original bug, at 1/100th the
  scale (0.5s vs 64.6s) and in the opposite direction. Invisible in playback, not
  publish-blocking, not worth fixing. `verify_output.py`'s stream-integrity check will report
  this non-integer fps on every future long-form render from now on — that's expected, not a
  new regression, don't spend time investigating it again.

  Regression coverage: `tests/test_window_dbfs.py` (added 2026-08-08) pins `_window_dbfs()`'s
  bounded-read behavior against a synthetic fixture reproducing the >538s condition. No
  synthetic test covers the `concatenate_clips()` metadata bug or the BGM-dropout bug directly
  (both need real multi-clip concatenation through the actual pipeline code to reproduce) —
  verified instead by direct reproduction against real Etiolation_S1 assets (documented above)
  and by the full re-stitch's own numbers. Worth a synthetic regression test if this code path
  changes again.
- **Phase 3 (CTA infrastructure) complete (2026-08-08)** — spec: vault `cta_plan.md`, decisions
  resolved 2026-08-07. Built, not yet exercised on a real upload (Etiolation_S1 ships with
  hand-written CTAs per the plan; video two is the first real test of this machinery):
  - **Outro card** — `stitch_video_longform.py`'s `resolve_outro_card()` / `build_outro_card_clip()`.
    DNA-gated (`cta.outro_card.enabled`), resolved via the same `resolve_channel_asset()`
    convention as `bgm.mp3`. Deliberately does NOT use `find_bgm_path()`'s fail-loud contract —
    the asset didn't exist yet when this was built (generated separately via the
    `aeonium-glow-brand` skill), so a missing file prints a visible warning and the stitch
    proceeds without a card, rather than blocking. Appended as an extra clip after all real
    scene clips, with a silent (not absent) audio track, so the later BGM mix pass is the only
    audio audible during it — "BGM only, no narration" by construction, not a special case.
    Confirmed it does NOT interact with the item-overlay window calculation (that step computes
    its own `total_duration` from real scene audio only) or with captions (no SRT entries exist
    for it, so none burn during it) — both correct by construction, verified by reading the code
    paths, not yet by a real render (no asset exists yet to render with).

    **CTA decision, evolved 2026-08-14 (do not change without asking):** the outro card's
    *visual* stays `cta.outro_card.audio = "bgm_only"` — the held card itself still carries
    no narration of its own. BUT the spoken ask (the two-beat ending's beat 2) now plays
    UNDER the card: a scene flagged `"outro_card_narration": true` in the manifest renders
    the card art as its visual (`force_static`, no Ken Burns) with its narration audio, and
    the silent card clip's hold is reduced by the narration length so the card's total
    on-screen time still matches `cta.outro_card.seconds`. `stitch_video_longform.py`'s
    `run_stitch()` handles the render; `write_burn_srt()` strips that scene's caption cue
    from the burned-in SRT (it would collide with the card's own on-screen text) while the
    CC-track `_captions.srt` keeps the full transcript. `subscribe` stays a
    description-surface item and is deliberately not spoken. If a future fix or feature
    seems to need more narration, audio, or new text on the outro card, that's a signal to
    flag it to the user, not to add it — this is the same kind of unstated assumption the
    `config_loader.py` nested-`cta` guard exists to protect against (below): something a
    nearby edit could silently overwrite without anyone deciding it should.

    **Trap — `outro_card_narration` scenes REQUIRE the outro card (2026-08-14):**
    `run_stitch()`'s `is_outro_narration = bool(scene.get("outro_card_narration")) and
    bool(outro_image)`. If the card is ever disabled in DNA (`cta.outro_card.enabled:
    false`) or its asset goes missing, the fallback is normal scene sourcing — but narrated
    scenes typically have no generated image (Etiolation_S1's SCENE-123 has no
    `visual_group_id` and no image file; its manifest `prompt` is a placeholder note), so
    the stitch fails with "missing sources". Fail-loud is the right shape; just know that
    turning the card off breaks any project using narrated scenes, and `verify_output.py`
    mirrors the subtraction in both its duration and BGM checks (see `narrated_card_seconds`).
  - **`build_description()`, `build_chapters()`, `build_pinned_comment()`** — `upload_youtube.py`
    was an unmodified Shorts copy before this (hardcoded `#shorts`, no chapters, no watch-next).
    Rewritten per `cta_plan.md`'s surface map: hook + watch-next above the fold, then chapters
    from `items.json`/`video_start` (listicle) or none (narrative), then links, subscribe line,
    tags (never `#shorts`). Pinned comment auto-generates the full ranked list with timestamps
    for listicles (`cta.pinned_comment_mode == "ranked_index"`), falls back to the DNA's generic
    prompt otherwise. Found and fixed in passing: `upload_to_youtube()` was calling
    `load_config(scripts_dir)` without `project_dir` — every per-video flat `cta_*` key would
    have silently resolved to `""` regardless of what a project's `config_override.json` set.
  - **`config_loader.py` rejects a nested `"cta"` object in a project override** — raises
    `ValueError` naming the flat-key convention, rather than letting the shallow merge silently
    replace the DNA's entire `cta` block. This is the fourth time this project has needed a guard
    against exactly this failure shape (prompts-file path mangling, the validator's
    species-rewrite, `build_prompt_map`'s missing `auto_prompt` fallback) — this one was caught
    before it ever produced a real bug, by building the guard proactively instead of after.
  - **In-script ask** — added as beat 2 of a two-beat ending (closing insight, then the ask) to
    the vault's `Workflows/pipeline_script_prompt_template.md`, and wired the same pattern into
    `generate_script.py`'s own prompt (which now reads the ask from `cta.comment_prompt_pattern`
    — a description of HOW to write a comment prompt, not a literal string). The old top-level
    `script_ending` ("Your plant will thank you.") is removed from `channel_dna` and now lives as
    its own field, `cta.narrative_signoff` — **correction, 2026-08-08**: this doc originally said
    it was "folded into `cta.comment_prompt_pattern`", which would have been a category error
    (guidance-on-how-to-write-a-prompt and a literal sign-off sentence are different kinds of
    thing); the actual DNA edit never did that, `comment_prompt_pattern`'s value was always the
    real pattern text, but the description here was wrong and has been corrected along with
    giving the sign-off its own key rather than leaving the wording ambiguous.
  - Also fixed while accounting for the outro card's extra duration (2026-08-08):
    `verify_output.py`'s duration and BGM checks now know about `cta.outro_card` —
    `check_duration_vs_manifest()` adds its resolved seconds to the expected total (an enabled
    card would otherwise fail a passing stitch by exactly its own length), and
    `check_bgm_audibility()` samples the card's whole span as a high-confidence data point
    alongside the per-clip-tail samples, since it's narration-free by construction for its
    entire duration rather than just a ~0.4s tail. Regression test:
    `tests/test_duration_outro_card.py`.
  - Regression tests: `tests/test_outro_card.py`, `tests/test_youtube_cta.py`,
    `tests/test_config_cta_guard.py`, `tests/test_duration_outro_card.py`.
- **`generate_script.py` is a near-unmodified Shorts copy — `--start-from script` now fails
  loudly instead of silently running it (2026-08-08).** Its docstring, defaults, and hardcoded
  instructions are still 100% Shorts-shaped: "AeoniumGlow Shorts Pipeline", "65–75 seconds when
  spoken", "140–165 words total", "short and punchy for Shorts pacing" — none of that matches a
  10-minute long-form script. `PRODUCTION_RUNBOOK.md` has warned against `--start-from script`
  since it was written, but nothing enforced it — and "script" is also that flag's own DEFAULT,
  so simply omitting `--start-from` silently ran the Shorts generator against a long-form
  project (a trap, not dead code). `run_pipeline.py`'s `main()` now exits immediately with a
  message pointing at the real supported path (`Workflows/pipeline_script_prompt_template.md` +
  `--start-from voiceover`) whenever `args.start_from == "script"` — cheaper and safer than
  adapting the generator, per explicit decision. The underlying file itself (`generate_script.py`)
  is still untouched and still Shorts-shaped; this guard makes that fact impossible to hit by
  accident rather than fixing the file. Found and fixed in passing: this surfaced that
  `run_pipeline.py` had no UTF-8 stdout guard at all (unlike `make_contact_sheet.py` and
  `verify_output.py`), so the fail-loud message's own `❌` crashed with `UnicodeEncodeError` on
  Windows' default console before ever printing — added the same `sys.stdout.reconfigure()`
  guard those two files already use. Regression test: `tests/test_start_from_script_guard.py`.
- **Voice — current choice works for Shorts, not for 10-minute long-form. Deferred by explicit
  decision after watching Etiolation_S1 end to end (2026-08-08), not an oversight.** The current
  voice (`en-US-JennyNeural` at `-10%`) was inherited unchanged from Shorts. It's fine for a
  60-second Short; synthetic prosody has limited variation, and listeners notice that
  progressively more with exposure — fatiguing across ten minutes in a way a Short never gives it
  time to become. Do NOT pick a replacement or change voice settings without a separate,
  deliberate decision. For whoever picks this up later:
  - `voice`/`voice_rate` already live in `channel_dna`, so this is a **DNA change, not a code
    change** — no pipeline work implied, just a values swap plus re-listening to confirm the
    replacement holds up across a full 10-minute video, not just a sample line.
  - Switching applies to **future videos only** — re-recording is required, so anything already
    produced (Etiolation_S1, and any narrative/listicle shipped before the switch) keeps the old
    voice. That creates a channel voice split at whatever point the switch happens; decide then
    whether that's acceptable or whether a re-record pass is warranted.
  - The switch may also change WhisperX transcription accuracy, in either direction — a different
    voice's pronunciation/pacing interacts with the mis-transcription backlog item above (species
    names being the highest-value words at risk). Re-verify that class of bug isn't made worse
    by whatever voice gets chosen.
- **Small, deliberately-not-done: `verify_output.py` requires Python 3.11 only because of an
  unused import in `generate_srt.py`.** `check_caption_structural()`'s Python-3.11 requirement
  traces entirely to `generate_srt.py` importing `mutagen` at module level, for
  `get_mp3_duration()`'s fallback path — which `split_caption_entries()` (the only function the
  structural check actually calls) never touches. Moving that import inside the function that
  uses it would decouple this verification tool from an audio library it doesn't need. **Do not
  do this** — it would be a third edit to a shared `shorts_pipeline2/` file, and the one-edit-at-
  a-time discipline for that file exists for a reason. Logged for whenever that file's next
  legitimate edit happens to land nearby.
- **User document + implementation document — deliberately deferred until one video ships.**
  A draft end-to-end checklist exists at `PRODUCTION_RUNBOOK.md` (research → topic → domain doc
  → script → production → publish). It is **marked DRAFT because steps C–D were assembled from
  Phase 1 verification, not from a real production run.** Use it as the guide for video one and
  correct it in place as things turn out differently.

  Only after a complete video has shipped, split it into two documents:
  - **User doc** — the runbook a human follows. Non-technical, decision points and manual steps.
  - **Implementation doc** — architecture: fork/shared split, the channel_dna seam, what calls
    what, where state lives, which failures are silent.

  *Why wait:* documentation written before the process runs records the *intended* process.
  Shorts' `CLAUDE.md` status table did exactly this and went stale silently until an API check
  caught it on 2026-08-04. Phase 1 alone surfaced three unpredicted failures (kiwi prior
  collision, caption desync, WhisperX OOM at real length); a production run will surface more,
  and those surprises are the most valuable content the docs can carry.

  Also record in the eventual docs the gaps listed at the end of `PRODUCTION_RUNBOOK.md`,
  notably: **no long-form tracker exists** (Shorts has `sync_shorts_tracker.py`; long-form has
  nothing), and there is no thumbnail automation.
- **WhisperX-at-scale: partially verified, not fully closed.** Tested against a real 5.7-minute
  narration (extracted from the audio track of the already-produced rot-rescue video) — see
  `PHASE_1_REPORT.md` for the result. 5.7 minutes is real long-form length but only about half
  a typical listicle target (10-15 min); the extracted track was final mixed audio (narration +
  BGM), fine for an OOM/load check but not a clean transcription-accuracy test. Close fully
  against a real 10-15 minute clean-narration run before treating this as settled.
- **Caption fontsize (36) and watermark fontsize (75) are untuned placeholders**, picked as
  reasonable starting points, never visually validated against real published content. Worth a
  deliberate pass once real long-form videos exist to judge against.
- **Fixing Shorts' own drifted CC-track upload is a known, tracked issue — but lives in
  `shorts_pipeline2/CLAUDE.md`, not here.** It's a Shorts defect (affects Shorts' uploaded
  subtitle tracks, not anything long-form produces), with a human content-decision gate before
  fixing (11 already-published videos would need re-upload to benefit).
- **The WhisperX mis-transcription class of bug — new real-world evidence, reprioritized above
  the forced-alignment idea below.** Phase 2's first real production run (Etiolation_S1,
  2026-08-06) hit it twice in one manifest: "Aeonium arboreum" transcribed as "Ionium Arborium"
  (SCENE-050, and persisted into SCENE-052's "Ioniums"), and "Curio rowleyanus"/"Senecio
  rowleyanus" as "Curio Raulianus"/"Senecio Raulianus" (SCENE-079) — species names are this
  channel's highest-value words, and both cases would have caused real damage left unfixed:
  `generate_srt.py:145` burns `scene["script"]` directly into captions (so the finished video's
  CC track would have shown the garbled name), and `generate_images.py:438` feeds the same text
  into prompt generation, where an unrecognised "species" fails `names_species()` and the
  validator's retry pass silently rewrites the shot to a different, wrong, approved species —
  the exact silent-swap failure class this whole validator exists to prevent, just triggered
  upstream by ASR instead of the model. Caught only by manual review before `--dry-run-prompts`;
  hand-corrected directly in `manifest.json` (confirmed sufficient — long-form's caption path
  reads only `scene["script"]`, never `source_audio/narration_words.json`, unlike Shorts' ASS
  path, so this is a one-file fix here, not the two-file repair Shorts' CLAUDE.md warns about).
  (this phase, previously: "Crassulacean" → "Crassulation"; previously on Shorts: "mist" →
  "missed".)

  **A cheaper fix than full re-alignment exists and should land first.** The full structural fix
  (below) is the correct end state but bigger than it looks — `whisperx.align()` needs segments
  with timing, so using the known script means fuzzy-matching script text onto ASR output, not a
  simple input swap. A **known-vocabulary correction pass** is much cheaper and catches the
  actual damage: `channel_dna` `subjects` already holds all 21 species names plus aliases —
  after transcription, fuzzy-match transcript tokens against that list and correct near-misses
  ("Ionium Arborium" → "Aeonium arboreum" is mechanical given the vocabulary is known in
  advance). Species names are the highest-value words in this channel's content; a targeted
  vocabulary fix is sufficient, a general ASR fix is not needed. Not started.

  Full structural fix, unchanged, lower priority: narration is TTS'd from a known `script.txt`,
  then `auto_split_scenes.py` runs `whisperx.align()` on an ASR *guess* of that same text rather
  than the text itself. Feeding the known script as the alignment input would eliminate this
  whole bug class. Scoped as its own future pass — touches shared `auto_split_scenes.py`, not
  started.
- **No species-overuse check — real damage on the first listicle dry-run.** The validator has a
  programmatic setting-overuse check (`ceil(total/3)`, `generate_images.py:708`) but no species
  equivalent; variety across shots is prose instruction only, and it did not hold. On
  Etiolation_S1's first `--dry-run-prompts` (46 shots), the auto-generator picked Echeveria
  elegans for ~24 of the 36 non-item (hook/explainer/outro) shots, with nothing flagging it —
  worse, Echeveria elegans is also item #1's own species, so the finale reveal ("the most widely
  owned rosette succulent... it has the most to lose") would have landed after viewers had
  already seen that exact species carrying most of the video's generic content. Caught only by
  manual human review at the mandatory `--dry-run-prompts` checkpoint, then hand-fixed via 32
  `override_prompt` entries rotating in 8 other `subjects` species. A programmatic check
  mirroring the setting-overuse one (flag when one species exceeds some threshold share of
  non-item shots) is the obvious fix — not started.

  Related, found while building the fix: `names_species()`'s first-two-words matching (by
  design, to survive cultivar punctuation — see its docstring) can't distinguish a cultivar from
  its parent species when the cultivar name is a strict prefix extension, e.g. "Sedum
  rubrotinctum" vs "Sedum rubrotinctum Aurora", or "Aeonium arboreum" vs "Aeonium arboreum
  Zwartkop" — a prompt naming the *plain* species gets attributed to whichever of the two
  canonical entries appears first in `subjects` (currently the cultivar, since it's listed
  first). Doesn't affect actual prompt/image content (the written prompt text is unambiguous),
  only any species-counting tooling built on `names_species()` — relevant to whatever
  species-overuse check gets built here, so noting it now rather than rediscovering it later.
- **Phase 1.5 complete** — see `PHASE_1_5_REPORT.md`. `channel_dna/aeonium_glow.json` now
  carries a `"validation"` block (setting vocabulary, subject-reference pattern, action/
  reversal/hallucination checks — all subject-specific rule *data*; the rule *engine* stays in
  `generate_images.py`, subject-independent) and `subjects` expanded 9 → 21 entries, backed by
  `succulent_demand_and_subjects.md`. Aliases are a field on the canonical entry
  (`"aliases": [...]`), not a duplicate row — `names_species()` matches canonical OR alias,
  always returns canonical. Golden-output test (`tests/test_golden_output.py`, renamed
  2026-08-08 from `golden_output_test.py` — the old name didn't match `test_*.py`, so
  glob-based test runners silently skipped it) proved the
  extraction byte-identical against 12 real corpus projects; the §6.7 portability smoke test
  (a throwaway knife-domain DNA file) proved the pipeline genuinely subject-portable with zero
  Python edited for prompt *generation*. **Phase 2** (listicle mode) is now unblocked — specced
  in `BUILD_BRIEF.md` §8-§10, not started.
- ~~Retry-guidance diagnostic print text still has succulent-shaped strings~~ **Fixed.** Found
  in the §6.7 portability follow-up (`fix_note`, what's actually sent to the model, was already
  DNA-driven and clean — but the console-facing `reasons` summary hardcoded English describing
  violation *categories*, e.g. always printing "water/pour/drainage action" for any
  `action_checks` violation regardless of which rule fired). Closed same-day: both strings
  moved into the DNA as a `label` field alongside each check's existing `guidance`
  (`subject_reference_pattern.label`, `action_checks[].label`), read via
  `subject_ref_cfg.get("label", ...)` / per-check `label` in the `ACTION_CHECKS` tuples.
  Verified with a synthetic config carrying custom labels (`CUSTOM-KNIFE-LABEL`,
  `CUSTOM-ACTION-LABEL`) — both appeared verbatim in the console output, confirming no
  hardcoded fallback text leaks through. Golden test re-confirmed byte-identical afterward.
- **Four validation rules are not exercised anywhere in the 12-project golden corpus**:
  `dehydration-vs-watering`, `nocturnal-lighting`, `watering-in-progress` (action-mismatch), and
  setting-overuse. All four verified separately by direct construction (see
  `PHASE_1_5_REPORT.md`), but a byte-identical golden-test result never actually exercises them
  — identity is trivially satisfied when a rule never fires in either run. Treat these four as
  needing the same direct-construction check this phase used for any future regex/engine change,
  not just a clean golden diff. Closes for real only if the corpus gains a project that
  naturally exercises them.
- ~~`build_prompt_map()`'s `by_scene_id` silently dropped every un-overridden shot~~ **Fixed
  same-day.** Found on Etiolation_S1's first real image-generation run (2026-08-06), via the new
  `make_contact_sheet.py` pixel check (see below) — a bug this serious survived
  `--dry-run-prompts` review because that gate only ever looks at prompt *text*, and the text in
  `prompts_review.json` was correct throughout; the corruption happened downstream, when
  `generate_images.py` consumed its own file. The dict comprehension at `build_prompt_map()`
  fell back straight from `override_prompt` to a legacy `"prompt"` key that `prompts_review.json`
  entries don't have (they use `"auto_prompt"`) — so every shot a human correctly left
  un-overridden (the file's own documented normal case) fell out of `by_scene_id` entirely,
  silently triggering a second, independent, unreviewed OpenAI auto-generation call instead of
  using the approved prompt sitting right there in the file. On Etiolation_S1 this corrupted all
  10 item shots plus 4 others (14/46) — the fresh batch call cross-contaminated content between
  shots in a consistent "-3 position" shift (item-10 got item-07's real content, item-09 got
  item-06's, etc.), a second, separate bug inside whatever batch-JSON-matching logic
  `auto_generate_prompts_batch()`/`validate_and_fix_shots()` use for a `missing_shots` fallback
  pass — never isolated, since the fix at the `by_scene_id` layer made it unreachable; worth
  isolating if it resurfaces elsewhere. Fixed by adding the missing `auto_prompt` check to the
  fallback chain, matching `make_contact_sheet.py`'s own `pick()` (which already had it right).
  Regression test: `tests/test_build_prompt_map.py`.

  **`shorts_pipeline2/generate_images.py` has the byte-identical bug, unfixed.** It's a forked,
  not shared, file (per this doc's fork/shared table) — the two copies inherited this
  independently from a common ancestor, so the longform fix does not reach Shorts. Every prior
  Shorts project that ran `--prompts-file` with any scene's `override_prompt` intentionally left
  blank (the normal, documented case) could have silently regenerated that scene's prompt instead
  of using the reviewed one — scope and blast radius on real Shorts output not yet assessed. Per
  the one-sanctioned-edit-at-a-time rule for `shorts_pipeline2/`, **not fixed here** — flagged for
  the user to decide scope and priority.
- **`make_contact_sheet.py` added (2026-08-06)** — closes the gap `--dry-run-prompts` always had:
  that gate reviews prompt *text*, never a rendered pixel, so a prompt can read perfectly and
  still render wrong (the kiwi cross-section) or, as above, never even reach the model the human
  approved. Montages every generated PNG in narration order with shot key/item number/species
  label; flags any shot with a prompt but no image. `PRODUCTION_RUNBOOK.md` step C4 now requires
  it in place of "spot-check several visually." Also fixed a bug in its own `load_prompt_map()`
  the same day it was added — it didn't recognize this pipeline's actual `prompts_review.json`
  shape (`{"image_prompts": [...]}`), only a `{"shots": [...]}` shape it never actually has here,
  so every label read "no prompt found" and one shot falsely flagged missing.
- **Shape/geometry negatives in image prompts actively backfire — use positive-only description,
  and change shot type before escalating language.** Found and fixed on Gasteria (item #10,
  Etiolation_S1, 2026-08-06) — full writeup in `light-and-etiolation-source-doc.md` §H, since it's
  a prompt-craft finding rather than a code one. Short version: "not a radiating rosette, no
  pointed leaves" still puts ROSETTE and POINTED LEAVES in the model's conditioning and made the
  render worse; dropping the priming words entirely ("rosette," "succulent") and describing the
  correct geometry positively fixed most of it; switching a still-failing whole-plant shot to an
  extreme macro of the distinctive leaf texture closed the rest. Colour negatives are unaffected
  by this and still work normally. Apply this to any future hard-to-render species before reaching
  for more negatives — Lithops and Haworthiopsis fasciata are named in the source doc as other
  species with non-rosette geometry a generic succulent prior could similarly overwrite (both
  rendered correctly on this run, not yet a proven failure — just flagged as the next place to
  watch).
- ~~Item overlay's last window ran to `total_duration`, mislabeling the outro~~ **Fixed
  same-day.** Found verifying Etiolation_S1's stitched output (2026-08-06): "#1 Echeveria elegans"
  stayed on screen 120+ seconds into the closing "here's the fix" section — `stamp_items.py`'s
  `outro_opening_line` boundary (added earlier the same day, see task #35/#39) correctly kept the
  outro's scenes out of item-01's `visual_group_id`, but `build_item_overlay_windows()` never knew
  that boundary existed — it computed the last item's end as `total_duration` unconditionally.
  Fixed by having the function derive each item's true end from the last scene actually sharing
  its `visual_group_id`, not from "the next tagged scene's start" — this also correctly handles
  non-item content *between* items (not just after the last one), which the old logic would have
  mislabeled too had any project had it. Regression test extended in `tests/test_item_overlay.py`
  to cover the outro-boundary case directly. Caught only because Task #40's verification pass
  extracted a real last-frame — a mid-video frame check alone would have missed this, same lesson
  as the original caption-desync fix.
- **`config_loader.load_config()` gained an optional per-project override layer (2026-08-06)** —
  `{project_dir}/config_override.json`, shallow-merged with highest priority (wins over both
  `pipeline_config.json` and channel_dna). Needed for real when Etiolation_S1 had to flip
  `item_overlay_enabled` on without changing that default for every other (narrative) project —
  several existing config keys' own doc comments already claimed this layer existed ("flip it on
  in the project's own config, not here"); it didn't, until now. `stitch_video_longform.py`'s three
  `load_config()` call sites all pass `project_dir` through. Backward compatible — the parameter is
  optional and every existing caller that omits it is unaffected. Regression test:
  `tests/test_config_override.py`.
- **Highest-value item in this backlog: assert the approved prompt is what actually shipped, per
  shot, automatically.** Three separate bugs so far have all produced the same failure shape — the
  pipeline runs successfully while quietly using content the human never approved: a mangled
  `--prompts-file` path silently falling back to fresh auto-generation (fixed 2026-08-04, the
  hard-fail in `build_prompt_map()`), the validator's retry pass silently rewriting a shot to a
  different species on a mis-transcribed name (found on Etiolation_S1, 2026-08-06), and
  `by_scene_id`'s missing `auto_prompt` fallback silently re-generating 14/46 shots from scratch
  (found and fixed the same day). Each was caught by a human noticing something looked wrong, not
  by anything the pipeline itself checks.

  The fix: one assertion, run right after image generation, before the contact sheet or stitch —
  for every shot, the prompt actually recorded in `manifest.json` (what `generate_images.py`
  wrote back per shot, see `run_generation`'s "write the shared prompt back to every member
  scene" comment) must match what `prompts_review.json` says was approved for that shot
  (`override_prompt` if set, else `auto_prompt`). Any mismatch fails loudly, naming every
  affected shot — this would have caught all three bugs above retroactively, and the next one
  like it prospectively, without needing a human to eyeball 46 images or read 46 prompt strings.

  This is `verify_output.py`'s sibling, not a duplicate of it: `verify_output.py` (added
  2026-08-07, see `PRODUCTION_RUNBOOK.md` step C7) answers "did the finished VIDEO match what was
  approved" (audio, captions, overlays, stream integrity); this answers the same question one
  stage earlier, "did the generated IMAGES match what was approved" (prompt content only, no
  ffmpeg/whisper involved — a fast, cheap check that could run on every `generate_images.py`
  invocation, not just at verification time). Keep the naming and PASS/FAIL reporting style
  consistent with `verify_output.py` when this gets built.

  Not started — Etiolation_S1's images are already contact-sheet-verified by hand for this run,
  so this is prospective, not blocking anything currently in flight.

- **Parameterize the outro-card HTML so the watch-next line isn't baked into the PNG
  (2026-08-14, from the CTA-card v2 design session) — DONE 2026-08-14.** The card source
  lives at `channel_dna/aeonium_glow/outro_card_src/` (HTML template + AIBMM Aeonium
  background + renderer). `render_outro_card.py` now takes `--watch-next-title` (+ optional
  ask/sub/label overrides) and renders a 1920×1080 PNG via headless Chrome — the watch-next
  line is no longer hand-edited per video; video two's card is a one-command job. The v3
  card (Etiolation_S1) was built with it. AIBMM session for the background:
  `64a9063e-b3b5-4267-a9ae-350789064773` (GPT Image 2, adhoc-1786728498101.png).

- **Long-form post-update routine (2026-08-14, flagged at Etiolation_S1 upload).** Shorts has
  `post_update.py`; long-form has nothing. After a long-form video goes public the pinned
  comment cannot be set at upload time (YouTube rejects pinning on private drafts — confirmed
  2026-08-14), so it must be posted post-publish. Build a small script (or extend
  `upload_youtube.py`) that takes a public video ID + the pipeline-built pinned comment
  (see `build_pinned_comment()`) and pins it. Manual for now: copy the text from the upload
  log and pin in Studio. Low priority — only needed at publish time.

- **Batch generation (2026-08-14, user idea).** Apply batch-generation patterns to more of the
  pipeline, not just images: e.g. batch-render/regen image fixes for a project (review-fix
  regens today are per-image one-off prompts), batch voiceover re-runs, batch SRT re-burns, or
  batch card/CTA regens across episodes. Etiolation_S1's review-fix images were handled
  per-image; a small script that replays a list of (scene_id, prompt) fixes through
  `generate_images.py`'s provider chain would make the next review round faster and more
  repeatable. Low priority — idea only, nothing in flight.
