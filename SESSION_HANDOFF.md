# Session Handoff — 2026-08-08

## What this session was

Started as a review of the outro-card re-stitch for `Etiolation_S1` (the long-form pipeline's
first listicle project) and turned into a long, adversarial back-and-forth: I'd report a fix,
the user would independently re-verify it, find something I'd gotten wrong or missed, and send
it back — six full rounds of this. Every round is recorded in `CLAUDE.md`'s BACKLOG with full
root-cause detail; this file is the short version for picking the thread back up.

## What got fixed (all closed, all independently verified by the user)

1. **BGM inaudible** — `amix` defaulted to `normalize=1`, silently dividing the configured
   volume by the weight sum. Fixed with `normalize=0` + no `weights=`.
2. **`verify_output.py` built** — the post-stitch QA harness (7 checks: BGM audibility,
   caption sync ×2, stream integrity, duration, black/freeze frames, loudness, overlay
   presence). Went through several redesigns, most significantly the caption-sync check
   splitting into a gating **structural** check (exact, manifest-vs-SRT, no transcription) and
   a never-fails **advisory** check (transcription-based gross-failure detector only).
3. **Real shipped-video defect, root-caused exactly**: every per-scene clip's video ran
   `CLIP_EXTRA` (~0.5s) longer than its own un-padded audio. Across ~123 clips this produced
   (a) a stitched file whose audio `duration_ts` claimed more than was actually decodable by
   any unbounded/sequential reader (`pydub`, `ffprobe -count_frames`, plain `ffmpeg -vn` with
   no `-t`) — a real ingest risk, not cosmetic — and (b) ~123 explicit BGM dropouts to digital
   silence at clip boundaries. Fixed at the source with `-af apad` in
   `build_clip_from_image()`/`build_clip_from_video()`. Re-stitched and confirmed: full
   unbounded decode now reads the real ~603s instead of stopping at 538s; boundary sampling
   shows continuous BGM decay, no more silence gaps.
4. **Watermark gate regression** — introduced *by me* while adding the outro card, caught
   before it shipped. `card_start` was computed from an audio-space accumulator instead of the
   real video-space render, leaving 4.8s of real narration unwatermarked. Fixed with a new
   `ffprobe_duration()` helper; pixel-verified.
5. **Same audio-space/video-space bug, third occurrence**: the item-overlay `total_duration`
   in `main()` had the identical mixing. Not reachable on `Etiolation_S1` today, fixed anyway.
   **`CLAUDE.md` now has a dedicated trap entry generalizing this pattern** — read it before
   adding any new duration-consuming code near the stitch pipeline.
6. **Systemic UTF-8 console guard gap** — 5 of 9 pipeline files had no guard at all (including
   `stitch_video_longform.py`'s fail-soft outro-card warning, which crashed under redirected
   stdout — defeating the exact unattended case it was designed for). Consolidated into a
   shared `console_encoding.py` (`ensure_utf8_console()`), wired into all 9 files.
7. **Test suite integrity**: `golden_output_test.py` renamed to `test_golden_output.py` (the
   old name didn't match `test_*.py`, invisible to glob runners). Then found it had two
   trivial-pass paths — the bare/no-flags run couldn't fail, and a missing corpus reported a
   false "IDENTICAL" — both fixed. **13/13 tests pass, verified under real piped-stdout
   conditions**, not just an interactive console.
8. **CTA guard-rail recorded**: `outro_card.audio` stays `"bgm_only"` — no narration, no extra
   card text. Documented in `CLAUDE.md` so a future edit doesn't silently "fix" this.

## Repo pushed

`C:\Bakcup_Asus\Aeonium_Glow\longform_pipeline\` is now a git repo, pushed to
**https://github.com/ghrao44741/longpipeline** (branch `main`). 50 files, 3.3MB. Before
pushing: confirmed `.env`/credentials excluded, added a `.gitignore` rule for ~24MB of loose
debug PNGs that weren't covered, confirmed the two 100MB+ generated video/audio files were
already excluded, confirmed the remote was empty before pushing (nothing clobbered). This
`SESSION_HANDOFF.md` file itself has **not** been committed/pushed yet — do that in the next
session if wanted.

## What's NOT done — the only real next step

**D-phase (publish) is entirely yours to run, not mine.** Full checklist is in
`PRODUCTION_RUNBOOK.md`'s Phase D section. The one concrete blocker:

- `Etiolation_S1/config_override.json` has no `cta_watch_next_id` / `_title` / `_why` set —
  the description's watch-next tease has nothing real to link to. Pick a real published video,
  add those three flat keys (never nested `cta` — `config_loader.py` will reject that), then
  `upload_youtube.py` can run for real.
- No long-form pinned-comment tool exists yet (`post_update.py` is Shorts-only). Manual for now.
- No long-form tracker exists yet (Shorts has `sync_shorts_tracker.py`; long-form has nothing).

Nothing else is outstanding. Etiolation_S1 itself has no known bugs blocking publish.

## Backlog items on record (not urgent, not started)

- `shorts_pipeline2/local_mp4_analyzer.py` had the identical pydub/frame-count bug as the
  one fixed here — flagged to the user, deliberately not touched (separate pipeline, one edit
  at a time rule there). **Fixed 2026-08-13** in both the shorts copy and the Aeonium Glow root
  copy: duration/levels now come from ffprobe/ffmpeg + windowed reads, matching
  `verify_output.py`'s approach.
- No species-overuse check in the image validator (setting-overuse check exists, species
  doesn't) — see `PRODUCTION_RUNBOOK.md`'s Known Gaps.
- No thumbnail automation.
- Caption/watermark font sizes are untuned placeholders.
- Voice (`en-US-JennyNeural`) was deliberately deferred as a future-videos-only DNA change —
  works for Shorts, untested at 10-minute length.

## How to pick this back up

Read `CLAUDE.md` in full first — it has the complete root-cause history with line numbers and
reasoning for every fix above. This file is the index, not the source of truth.
