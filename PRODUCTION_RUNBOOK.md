# Production Runbook — research to upload

> **STATUS: PHASE A–C VERIFIED. PHASE D STILL DRAFT.**
> Written 2026-08-05, before the first complete long-form video. Phases A through C have now
> run end to end on real content (Etiolation_S1) and been **human-verified** (2026-08-08) — watched
> full video, BGM sits right, pacing fine, numbered overlay lands with the voice. Treat A–C as
> established for future videos, correcting in place only as real discrepancies turn up.
>
> **Phase D is still draft and untouched.** Etiolation_S1 was never uploaded — none of D1–D7 has
> been exercised against real output. Don't treat D's steps as verified just because A–C are.

Vault root referenced below:
`C:\Users\Girir\Documents\Giri Knowledge Base\02-PROJECTS\YouTube\Succulents\Aeonium Glow\`

---

## PHASE A — RESEARCH & TOPIC

**A1. Validate demand.** Check `succulent_demand_and_subjects.md`. Title at **genus** level
using the **common name** — genus beats cultivar by ~18×, common name beats botanical.

**A2. Check for overlap — INCLUDING THE LIVE CHANNEL.** Check `shorts_session.md` Project
Provenance, the `Aeonium_Glow\` package folders, the vault Source Docs list, **and
youtube.com/@aeoniumglow/videos**. Adjacent topics should cross-promote, not re-derive each
other's biology. This project has shipped near-duplicate content by accident before.

**The live-channel check is not optional, and local files are not a substitute.** On 2026-08-07
the channel was found to hold eight published long-form videos — one of them *"Stop Using
Regular Potting Soil!"* (1K views, a month old), the same axis as the then-planned rot listicle.
Nothing local recorded any of them. This is the same staleness class as the 2026-08-04
manifest-versus-API incident: tracked state silently diverges from what is actually published.

Record what you find in `succulent_demand_and_subjects.md` so the next check starts from
something rather than from nothing.

**A3. Identify the counter-intuitive beat.** The instinctive response that makes the problem
worse. **If there isn't one, the topic probably won't carry a video** — stop here and pick
another.

**A4. Does a domain source doc exist for this axis?** Check `domain_source_doc_template.md` §1.
Domain docs are per *axis*, not per video.
- Yes → go to A6.
- No → A5.

**A5. Build the domain source doc.** Follow `domain_source_doc_template.md`. **Verify the
confidence markers yourself** — an LLM assigning its own markers is grading its own homework.
At minimum, verify every claim the video's thesis depends on. Update the template's §1 table.

**A6. Check species against `channel_dna` `subjects`.** Any species named in the doc must be in
the list, or the validator silently swaps it for one that is. Expand the DNA first if needed.

---

## PHASE B — SCRIPT

**B1. Choose the format.** Narrative (hook → sections → close) or listicle (ranked countdown).
A count in the title means listicle.

**B2. Generate the script.** Use `pipeline_script_prompt_template.md` with the domain doc
attached. Output is narration text only — no headings, no visual direction, no metadata.

**B3. Review the script.**
- Read it aloud. Anything written-for-the-eye will sound wrong.
- Word count ≈ target minutes × 60 × 2.2.
- Listicle: every item starts a new sentence; all four teases use different wording.
- Every plant named specifically, from `subjects`.
- States not instructions, except in the fix section.

**B4. Place the files.**
```
{Project}\script.txt          the narration
{Project}\source_doc.path     one line: absolute path to the domain doc
```

---

## PHASE C — PRODUCTION

Run from `longform_pipeline\`, not `shorts_pipeline2\`.

**C1. Voiceover → scenes → dry-run prompts.**
```powershell
python run_pipeline.py --project {Project} --start-from voiceover --dry-run-prompts --skip-upload
```
Do **not** use `--start-from script` — its approval gate needs a real terminal, and the script
is already written.

**C2. HARD STOP — review `prompts_review.json`.** Mandatory, never skipped. Check every prompt:
- names the species that scene is actually about
- shows the **state** the narration describes — never the fix, never the outcome
- is 16:9
- for anything hard to render (cross-sections, etiolation geometry), anchors the subject and
  its morphology **before** the camera framing, and names the failure mode in the negatives

**C3. Generate images.**
```powershell
python run_pipeline.py --project {Project} --start-from images --prompts-file "<ABSOLUTE PATH>" --skip-upload
```
Quote the path. Relative paths hard-fail by design.

**C4. Verify images.** Assert every PNG is exactly 1920×1080. Then build and review a contact
sheet — the `--dry-run-prompts` gate (C2) only reviews prompt TEXT, and a correct-reading prompt
can still render wrong (the kiwi cross-section is the canonical case: nothing between generation
and stitch otherwise looks at an actual pixel).
```powershell
python make_contact_sheet.py --project {Project}
```
Writes `{Project}/output/contact_sheet.png` — every generated image in narration order, labelled
with shot key, item number (listicle), and the species its prompt names, plus an explicit list
of any shot that has a prompt but no image (generation failure). Review the whole sheet, not a
spot-check sample. For anything wrong: delete that PNG, fix `prompts_review.json` if needed, and
re-run C3 — `generate_images.py` skips anything already on disk, so it only regenerates what you
deleted.

**C5. Stitch.**
```powershell
python stitch_video_longform.py --project {Project}
```
Requires Python 3.11 (`mutagen`).

**C6. Verify the render on extracted frames — never on the SRT.**
```powershell
ffmpeg -y -ss 120 -i {Project}/output/{Project}_captioned.mp4 -frames:v 1 check.png
```
Check **mid-scene, not at a boundary**, and check the **last scene** — caption drift is
cumulative, so the end is where a timing bug still shows. Confirm: 1920×1080, captions readable
in the bottom third and matching the visual, watermark present, BGM audible and under the voice,
and (listicle) the correct item number on screen.

**C7. Run the automated post-stitch verification — measures what C6 checks by eye.**
```powershell
C:/Users/Girir/AppData/Local/Programs/Python/Python311/python.exe verify_output.py --project {Project}
```
Requires Python 3.11 (`mutagen`) — same interpreter C5 needs, see `verify_output.py`'s own
docstring for why.

Every real defect caught so far in this phase (caption desync, the item-overlay outro bug, BGM
silently inaudible for every long-form video before 2026-08-07) was found by a human looking at
a frame or listening by ear — this makes those checks measurable instead of a judgment call each
time. Checks:
- **BGM audibility** — RMS in the guaranteed-speech-free tail of every clip.
- **Caption sync (structural, gating)** — re-derives each scene's expected SRT entries from the
  manifest's own `video_start`/`video_end` (via `generate_srt.py`'s own chunking function, not a
  reimplementation) and asserts the SRT file on disk matches to within ~50ms. This is the real
  desync-detection check: exact, instant, no transcription. It catches the SRT-built-from-stale-
  timestamps bug class, but not `video_start` itself being wrong (both sides would agree).
- **Caption sync (advisory, never fails)** — an independent WhisperX/Whisper transcription smoke
  test, the one check that CAN catch `video_start` itself being wrong. Has a real, bounded noise
  floor (several seconds mean, ~15s ceiling) from comparing against coarse multi-word SRT entries
  rather than word-level ground truth — confirmed via seven direct frame extractions that its
  "worst offset" reports do not indicate real desync. **A large number from this check alone is
  not proof of a problem — cross-check with a direct frame extraction before concluding anything
  is wrong.** Never raise its threshold to chase a "pass" and never treat it as gating; see
  `CLAUDE.md`'s caption-sync trap entry for the full history.
- **Stream integrity** (resolution/fps/codec/audio), **duration vs. the manifest's expected
  total**, **black/freeze frames**, **integrated loudness (LUFS)**, and — best-effort, reported
  not failed — **watermark and item-overlay pixel presence**.

Writes `{Project}/output/verify_report.txt` and exits non-zero on any GATING failure (the
structural caption-sync check counts; the advisory one never does). The advisory check is also
the slowest (full transcription); `--skip-caption-sync-advisory` to skip it when iterating
quickly, but run the full check at least once before publishing.

---

## PHASE D — PUBLISH

Steps D1–D2 and D4–D6 are **manual**; only D3 is automated.

**D1. Thumbnail.** No automated path. Extract a frame or build one separately.

**D2. Title, description, chapters, tags.** Genus-level title, common name. Chapters from
`items.json` (listicle) or section headings (narrative). **Never tag `#shorts`.**

**D3. Upload.**
```powershell
python upload_youtube.py --project {Project} --title "..." --description "..."
```
Lands as a **private draft**. Uploads the SRT as a subtitle track.

**D4. Publish.** Studio → add thumbnail → confirm title → set Public. Manual.

**D5. Pinned comment — CORRECTED, verified against the real file tree.** `post_update.py` does
**not exist in `longform_pipeline/`** — it's a Shorts-only tool (`shorts_pipeline2/post_update.py`),
never copied or forked here. There is currently **no long-form equivalent**; see D7/BACKLOG.
YouTube's API rejects comments on private videos regardless, so any future version of this step
must come after D4.

**D6. Pin the comment.** Studio → Comments → ⋮ → Pin to top. The API cannot do this.

**D7. Update tracking.** Whatever the long-form equivalent of `sync_shorts_tracker.py` turns out
to be — **does not exist yet.** See BACKLOG.

---

## KNOWN GAPS AT TIME OF WRITING

- **C1's WhisperX settings (`--compute-type float16 --batch-size 4`) are now proven to 10:28** —
  Etiolation_S1's real scene-split (2026-08-06) completed clean at nearly 2x the original 5.7-minute
  test, no OOM. If a future run goes meaningfully longer than ~10-11 minutes and OOMs, that is still
  expected, not a new bug — lower `--batch-size` further.
- **Image count, corrected**: the ~9.5 images/minute estimate was pre-item-keyed-grouping. With
  grouping (Phase 2, `stamp_items.py`), a real 10-item, ~10.5-minute listicle (Etiolation_S1) measured
  **46 shots**, not the originally-hoped 10-20 — item spans themselves cut to 10 groups as designed,
  but the hook/explainer/outro sections around the countdown are still sentence-level grouped and
  account for 36 of the 46. That is defensible pacing for explainer-heavy content, but budget review
  time and image spend for ~46 prompts per listicle, not 10-20.
- **No species-overuse check.** The validator has a setting-overuse check
  (`ceil(total/3)`, `generate_images.py:708`) but no species equivalent — variety across shots
  relies on prose instruction only. On Etiolation_S1's first real dry-run, one species (Echeveria
  elegans — coincidentally also item #1's own species) was auto-picked for ~24 of 36 generic
  shots, with nothing flagging it; caught only by manual human review at the `--dry-run-prompts`
  checkpoint, then fixed by hand via `override_prompt`. A programmatic check mirroring the setting
  one is the obvious fix — see `longform_pipeline/CLAUDE.md` BACKLOG for the fuller writeup.
- **No long-form tracker** exists. Shorts has `sync_shorts_tracker.py`; long-form has nothing.
- **No thumbnail automation.**
- **Caption and watermark font sizes are untuned placeholders.**
