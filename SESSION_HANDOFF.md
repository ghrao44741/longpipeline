# Session Handoff — 2026-08-14

> Supersedes the 2026-08-08 handoff below this point in history — that round closed out the
> pipeline's technical/verification bugs (BGM, apad, watermark gating, UTF-8 guards, test
> suite). This round was a **human review pass on the finished Etiolation_S1 video itself**
> (botanical accuracy, narration/image matching, CTA structure, packaging) plus several
> pipeline-capability additions that came out of fixing what the review found. Read
> `CLAUDE.md` in full for complete root-cause detail on every item below — this file is the
> index, not the source of truth.

## Where things stand right now

**Live draft, fully up to date, all fixes included: https://youtu.be/_QgVLiUi4E8**
(private, unlisted-not-yet, `manifest.json`'s `youtube_video_id`/`youtube_privacy_status`
confirm this). `verify_output.py` is 8/8 PASS against the current render.

**Stale drafts that need manual deletion (I don't delete videos — that's a permanent-deletion
action, always left to the human):**
- `youtu.be/DGWfHFgNPc0` — earliest, missing everything since
- `youtu.be/lBZ8oCvL53A` — missing everything since the rot/shrivel/sunburn fix
- `youtu.be/ymV7zByhxdw` — missing the Lithops fix and the final watermark flip
- (`youtu.be/VECRfOj-zC8` was already deleted by the user mid-session — not stale, just gone)

**Thumbnail candidates exist but aren't wired up yet.** A separate commit (`a7fe8b6`, made
outside this conversation) added `Etiolation_S1/thumb_v1.png`, `thumbnail_1280x720.png`, and
three extracted frame candidates in `Etiolation_S1/thumb/`. `upload_youtube.py` only
auto-detects a file literally named `thumbnail.png`/`.jpg`/`.jpeg` in the project root — none
of these match that name yet. Pick one, copy/rename it to `Etiolation_S1/thumbnail.png`, then
either re-upload or attach it directly via Studio.

**Pinned comment not yet posted anywhere** — every attempt so far has correctly been blocked
by YouTube's API (comments can't be created on a private video). Once the video is actually
published (Studio → Public), run `python post_update.py --project Etiolation_S1` — it syncs
live status into the manifest and posts the pipeline-built ranked-index comment automatically,
safely a no-op if run again or if the video is still private.

## What this round found and fixed, in order

All independently re-verified by the user watching the actual finished video — this is the
same adversarial pattern as the 2026-08-08 round, not a rubber stamp.

1. **Wrong closer species** — `Ceropegia woodii` prompt rendered as `Scindapsus pictus`
   (satin pothos) despite being correctly worded. Fixed with the established two-axis prompt
   pattern (anchor distinguishing morphology before framing, name the confused species in
   negatives) — see `CLAUDE.md`'s image-generation trap entries.
2. **Botanical honesty — healthy-as-etiolated heroes.** Items #1 (Echeveria), #4 (pearls), #5
   (jade), #6 (elephant bush) all read as healthy/compact when the narration described
   visible stretch damage. Regenerated with symptom-specific prompts + camera-angle changes
   (a top-down shot was hiding the stretched stem on #1 — angle mattered more than wording).
3. **B-roll drift** — 3 flowering-Kalanchoe shots (blooms undercut an etiolation/neglect
   story) and 2 repetitive Sedum shots rotated to other approved species.
4. **Caption UX** — fontsize 36→28→22 across two passes; `Bold`/`Outline`/`MarginV` made
   `channel_dna`-configurable and lightened (was hardcoded `Bold=1,Outline=2,MarginV=40`).
5. **Watermark position — flip-flopped several times, final state is bottom-right.**
   Sequence: bottom-left (original) → bottom-right (user request) → bottom-left (user's
   separate session, said this was verified correct) → bottom-right (user: "I was wrong
   again"). Current `channel_dna/aeonium_glow.json` value is authoritative; don't re-derive
   intent from git history, the back-and-forth was real, not a bug.
6. **Missing Bensound music credit** — `channel_dna`'s `music_credit` key existed in
   `build_description()` but was never populated. Set, and patched onto the already-uploaded
   video's live description via a direct `videos().update()` call.
7. **Rot/shrivel/sunburn narration-image mismatch (23–33s)** — one B-roll shot held a single
   "looks lush and thriving" image across four narration lines describing three different
   damage types plus the thriving contrast. Root-caused as a general pattern: **a grouped
   shot's held image can be correct for the sentence its prompt keyed off and wrong for every
   other sentence sharing that shot**, invisible to prompt review because the prompt text
   itself is self-consistent. Fixed by ungrouping into per-scene images. Documented in the
   skill (Step 5/6).
8. **Missing spoken CTA** — the script ended on a closing-insight line only, no ask at all,
   against the channel's own documented two-beat-ending design. Backfilled via a standalone
   TTS'd scene appended to the manifest (didn't re-run voiceover for the whole script — that
   would've re-timed everything already fixed). Documented the safe append mechanism in
   `IMPLEMENTATION.md` §4.
9. **CTA placement redesigned mid-session**: originally landed the spoken ask *before* the
   outro card (over the closer plant image); the user clarified the actual intent was the ask
   playing *under* the card itself. Rebuilt as a first-class `outro_card_narration` manifest
   flag — `stitch_video_longform.py`'s `run_stitch()` renders that scene with the card art
   (`force_static`, no Ken Burns) and its narration audio, shrinking the silent card clip by
   the same amount so total on-screen card time still matches `cta.outro_card.seconds`.
   `verify_output.py`'s duration and BGM checks were fixed to not double-count the narrated
   portion. **This exact feature got reimplemented a second time** in the user's own separate
   session (commit `a9cf7f8`) with an almost identical design — not a conflict, just recorded
   here so it isn't a surprise seeing two "add spoken CTA under card" efforts in the log.
10. **Caption/card text collision** — the burned CTA caption visually overlapped the card's
    own "Watch next →" text. Fixed with `write_burn_srt()`: strips that one cue from the
    *burned* captions only (collision), while the real `_captions.srt` (CC track) keeps the
    full transcript.
11. **Item-02 (Lithops) — same grouped-shot mismatch as #7, but in a listicle item.** Narration
    pivots from describing a healthy Lithops to describing one that's elongated/toppled; the
    held image only ever showed healthy. This case had an extra constraint #7 didn't: item
    shots carry the "#N Name" overlay, and `build_item_overlay_windows()` derives that
    overlay's window from every scene sharing the *tagged* scene's `visual_group_id` —
    removing the group id (the #7 fix) would have silently truncated the overlay early. Fixed
    instead by placing per-scene image files directly for the failure-state scenes
    (`find_video_source()` already checks scene-specific files before falling back to the
    group image) — `visual_group_id` never touched, overlay window verified intact afterward.
    Image generated via a standalone `generate_with_xai()`/`save_image()` call, since a scene
    with `visual_group_id` set can never be reached through the normal `--prompts-file` flow.
    Documented in the skill.

## New pipeline capabilities added this round (not bug fixes, new tools)

- **`post_update.py`** (this pipeline's own copy, not `shorts_pipeline2`'s) — syncs live
  YouTube status into the manifest and posts the pinned comment once a video is actually
  public. Closes a gap the skill used to explicitly call out as missing.
- **`channel_dna/aeonium_glow/outro_card_src/render_outro_card.py`** — parameterized outro
  card renderer (`--watch-next-title` etc.), so the card no longer needs hand-edited HTML per
  video. **Its `--out` default writes inside `outro_card_src/`, not the live asset path** — a
  manual copy to `channel_dna/aeonium_glow/outro_card.png` is still required, and there's no
  per-project override for this asset (unlike `bgm_file`), so it's genuinely one shared file
  across every future video. Skill's Step 7 now has the exact command sequence.

## Two new reference docs, written this round

- **`USER_GUIDE.md`** — decision-focused runbook (what to check at each phase, not how the
  code works). Supersedes `PRODUCTION_RUNBOOK.md` as the current guide; that file is now a
  historical draft.
- **`IMPLEMENTATION.md`** — architecture/mechanism reference: the fork/shared split, the
  config seam, the stitch's audio-space-vs-video-space bug class (now three confirmed
  instances), image-prompting patterns that actually work, the silent-substitution bug
  pattern, and the safe-scene-append mechanism.

Both were flagged as deliberately deferred in `CLAUDE.md`'s backlog until a video had shipped
end-to-end — that condition was met this round, hence writing them now.

## Backlog carried over, still not started

- No species-overuse check in the image validator (setting-overuse exists, species doesn't).
- No long-form view/publish tracker (Shorts has `sync_shorts_tracker.py`).
- Chapters only exist for listicle format — narrative videos get no chapter markers yet.
- Caption *line-wrap width* (words per burned line, not font size) still lives in shared
  `generate_srt.py`'s hardcoded `MAX_LINE_CHARS = 55` — deliberately not touched (would be a
  third edit to a shared file; needs an explicit decision, not a reflex).
- Voice (`en-US-JennyNeural`) still deferred as a future-videos-only DNA change.

## How to pick this back up

Read `CLAUDE.md` in full — it has complete root-cause detail with line numbers for every item
above. Then `USER_GUIDE.md` for the next production's workflow, `IMPLEMENTATION.md` if
touching the pipeline's internals. The skill (`.claude/skills/produce-longform/SKILL.md`) is
current as of this handoff — every fix above that changed a documented process also updated
the skill in the same commit.

---

# Session Handoff — 2026-08-08 (prior round, technical/verification fixes)

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
   **Superseded 2026-08-14** — see the round above; the CTA design deliberately evolved to
   allow narration under the card via a scene flagged `outro_card_narration`.

## Repo pushed

`C:\Bakcup_Asus\Aeonium_Glow\longform_pipeline\` is a git repo, pushed to
**https://github.com/ghrao44741/longpipeline** (branch `main`).

## Backlog items from this round (status as of 2026-08-14, see above section for current)

- `shorts_pipeline2/local_mp4_analyzer.py`'s pydub/frame-count bug — **fixed 2026-08-13**.
- No species-overuse check, no thumbnail automation, caption/watermark sizes untuned,
  voice deferred — all **still open**, carried into the current backlog section above.
