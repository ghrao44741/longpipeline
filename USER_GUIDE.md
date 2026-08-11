# User Guide — Producing an Aeonium Glow Long-Form Video

> Audience: the human running the `/produce-longform` skill (or its underlying scripts by
> hand). Non-technical, decision-focused. For "how the machine works," see
> `IMPLEMENTATION.md` instead — this document only covers what you decide and what you check.
>
> Status: written 2026-08-11, **after** the first complete video (Etiolation_S1) shipped
> end-to-end — script → images → stitch → verify → YouTube upload. Phases A–D below are no
> longer draft; every step has now run at least once against real output. Correct this
> document in place as future videos surface new discrepancies, the same way
> `PRODUCTION_RUNBOOK.md` (its predecessor, now superseded by this file) was corrected after
> Etiolation_S1's Phase A–C run.

---

## The one-sentence version

Say what you want ("make the long-form video about root rot," "do the etiolation
countdown") and the `produce-longform` skill runs the whole pipeline, stopping at **three
hard gates** for your approval: the structure, the script, and the image prompts. Nothing
expensive or irreversible happens without you seeing it first.

---

## Before you start: two formats

| | **Narrative** (default) | **Listicle** |
|---|---|---|
| Shape | hook → sections → close | ranked countdown, #N → #1 |
| Pick when | topic is a process, diagnosis, rescue, explanation | topic has a count ("10 succulents that…") |
| Extra artifact | none | `items.json` (generated from the source doc's ranked list) |
| Extra guardrail | none | species validator is a **live hazard** — see Phase C below |

The choice is made from the topic and is **not reversible after scripting** — the skill will
ask if it's ambiguous. If you already know, just say so.

**Scope: succulents only.** No general houseplants, no tropicals, no cacti (botanically
close but deliberately excluded). If a script draft reaches for one, that's a bug to flag,
not scope creep to wave through.

---

## Phase A — Research & topic

1. **Check demand.** `succulent_demand_and_subjects.md` in the vault. Title at genus level
   using the common name (genus beats cultivar by ~18×; common name beats botanical name).
2. **Check for overlap — including the live channel, not just local files.** Local trackers
   have gone stale before (the channel had eight published long-form videos, one of them the
   exact axis of a then-planned rot listicle, and nothing local recorded any of them). Check
   youtube.com/@aeoniumglow/videos directly, every time.
3. **Find the counter-intuitive beat** — the instinctive response that makes the problem
   worse. If there isn't one, the topic probably won't carry a video. Pick another.
4. **Confirm a domain source document exists** for this axis (one soil/drainage doc backs
   several soil videos — check before writing a new one). If not, build one from
   `domain_source_doc_template.md` and **verify the confidence markers yourself** — an LLM
   grading its own claims is grading its own homework.
5. **Check every species the doc names against `channel_dna/aeonium_glow.json`'s
   `subjects` list.** Anything missing gets silently swapped by the validator later. Fix
   this now, not after scripting.

---

## Phase B — Script, then HARD STOP 1 and HARD STOP 2

**HARD STOP 1 — the structure**, before any prose is written:
- Narrative: the section outline, every heading, one line each. Is the arc right? Anything
  redundant against an existing video?
- Listicle: the **full ranked list**, in countdown order, with a one-line justification per
  rank. Not a count — the actual list. Check specifically:
  - Is anything ranked wrong?
  - Is anything missing that a viewer would expect to see?
  - **Is #1 actually the highest risk × ownership, not just the most dramatic outlier?** The
    dramatic outlier usually belongs at #2, where it makes #1 land harder.

Ranking rule for any listicle on this channel:

> Rank by **severity on the video's problem axis × how many people own the plant.**

A plant that fails instantly but that almost nobody owns ranks *below* one that fails
slowly in ten thousand homes.

Once the structure is approved, the script gets written (`pipeline_script_prompt_template.md`
+ the domain doc). **HARD STOP 2 — the full script text**, not a summary:
- Does any claim exceed what the source doc's confidence markers allow?
- Does it re-derive a companion video's biology instead of pointing at it?
- Does it end on a concrete next action?
- Listicle only: does each item start a new sentence (so scene-splitting lands cleanly)? Does
  each item carry exactly one twist clause, not a full fix? Do the retention teases (roughly
  every quarter, plus one before #3) all use different wording? Repeated identical phrasing
  is the clearest audible tell of synthetic narration.

Files land at:
```
{Project}\script.txt          the narration, nothing else
{Project}\source_doc.path     one line: absolute path to the domain doc
```

Word count sanity check: target minutes × 60 × 2.2.

---

## Phase C — Production

Run everything from `longform_pipeline\`, **not** `shorts_pipeline2\`.

### C1. Voiceover → scenes → dry-run prompts
```powershell
python run_pipeline.py --project {Project} --start-from voiceover --dry-run-prompts --skip-upload
```
Never use `--start-from script` — it's guarded and will refuse. It exists for a different,
Shorts-shaped generator; your script is already written and approved.

### C2. HARD STOP 3 — review `prompts_review.json`, mandatory, never skipped

For every prompt:
- Names the species that scene is actually about.
- Shows the **state** the narration describes — never the fix, never the outcome. (In a
  listicle, the fix only ever appears once, at #1.)
- Is 16:9, not 9:16.
- For anything hard to render (cross-sections, stretched/etiolated geometry, any shot where a
  strong "healthy stock photo" training prior fights the intended visual): anchors the
  subject and its distinguishing morphology **before** the camera framing, and names the
  specific failure mode in the negatives (e.g. "not Scindapsus pictus, not satin pothos" —
  not just generic negatives). Changing the **shot angle** (top-down hides a stretched stem;
  a low three-quarter angle shows it) is often the fix before escalating wording further.

**Listicle only — species validation is a live hazard, not a formality.** Every item's
species must be in `channel_dna`'s `subjects` (canonical name or listed alias). On a 10–15
item list, an unrecognized name gets **silently rewritten to a different approved species**
by the retry pass — the exact silent-substitution failure this whole review step exists to
catch. This has happened for real: a mis-transcribed "Curio rowleyanus" became "Curio
Raulianus," which the validator then quietly swapped to a different plant. Read every prompt;
don't trust that "no error was printed" means nothing swapped.

### C3. Generate images
```powershell
python run_pipeline.py --project {Project} --start-from images --prompts-file "<ABSOLUTE PATH>" --skip-upload
```
**Quote the path, and make it absolute.** A relative `--prompts-file` path silently mangles
onto the project dir and — used to — fell back to fresh, unreviewed auto-generated prompts.
It now hard-fails instead, but quote it anyway.

Budget: a real 10-item, ~10.5-minute listicle measures **~46–50 shots**, not the ~10–20 you
might expect from item count alone — the hook/explainer/outro sections around the countdown
are grouped at sentence level and account for most of that. The exact count can grow a little
past the initial auto-split if a review pass later splits a grouped shot apart (see C4/C7's
narration-mismatch check below) — that's a correctness fix, not a budget overrun to avoid.

### C4. Verify images — pixels, not just prompt text

`--dry-run-prompts` (C2) only reviewed the *text*; a correctly-worded prompt can still render
wrong (a "succulent stem cross-section" prompt rendered as sliced kiwi fruit on first try —
strong training priors on certain framings are real). Build and review a contact sheet:
```powershell
python make_contact_sheet.py --project {Project}
```
Writes `{Project}/output/contact_sheet.png` — every image in narration order, labelled with
shot key, item number, and the species its prompt names, plus an explicit list of any shot
with a prompt but no image. **Review the whole sheet**, not a sample. To fix a bad shot:
delete that PNG, adjust the prompt if needed, re-run C3 — it only regenerates what's missing,
everything else is left alone.

### C5. Stitch
```powershell
C:\Users\Girir\AppData\Local\Programs\Python\Python311\python.exe stitch_video_longform.py --project {Project}
```
**Requires Python 3.11** specifically (needs `mutagen`) — not whatever `python3` resolves to
by default.

### C6. Verify the render on extracted frames — never trust the SRT alone
```powershell
ffmpeg -y -ss 120 -i {Project}/output/{Project}_captioned.mp4 -frames:v 1 check.png
```
Check **mid-scene, not at a boundary**, and check a frame **near the end** — timing drift is
cumulative, so a bug that's invisible at t=30s can be seconds off by t=500s. Confirm:
1920×1080, captions readable and matching the visual, watermark present in the right corner,
BGM audible under the voice. Listicle only: the numbered overlay shows the correct number at
that exact timestamp — extract from *inside* an item's window, not a transition, since
off-by-one errors are invisible everywhere else.

### C7. Automated post-stitch verification
```powershell
C:\Users\Girir\AppData\Local\Programs\Python\Python311\python.exe verify_output.py --project {Project}
```
Same interpreter requirement as C5. Runs BGM audibility, caption-sync (a fast structural
check that gates, plus a slow WhisperX advisory check that never gates — see
`IMPLEMENTATION.md` if a number from the advisory check looks alarming), stream integrity,
duration-vs-manifest, black/freeze frames, loudness, and watermark/overlay presence. Writes
`{Project}/output/verify_report.txt`, exits non-zero only on a real gating failure.
`--skip-caption-sync-advisory` speeds up iteration; run the full check at least once before
anything gets uploaded.

**If a human review (yours, or a second pair of eyes) flags something `verify_output.py`
can't catch** — wrong species rendered despite a correct prompt, a "healthy" shot where the
narration describes visible damage, a repetitive or off-brand B-roll choice — fix it the same
way real problems got fixed on Etiolation_S1's own review pass:
1. Write a **stronger, more specific** `override_prompt` in `prompts_review.json` — anchor
   distinguishing morphology before framing, name the specific confusion in negatives, and
   consider changing the shot angle before escalating language further (see C2).
2. Delete only the affected PNG(s) from `{Project}/images/`.
3. Re-run C3 with the same `--prompts-file` — it regenerates only what's missing.
4. Re-run C5 (stitch) and C7 (verify) — a stitch is required to see the new image in context;
   verify confirms nothing else broke.

---

## Phase D — Publish

Steps D1, D2, D4, D6, D7 are manual. D3 (upload) and D5 (pinned comment, conditionally) are
automated.

**D1. Thumbnail.** No automated path yet. Extract a frame, or build one with the
`aeonium-glow-brand` skill. Drop it into `{Project}/thumbnail.png` (`.jpg`/`.jpeg` also
work) — `upload_youtube.py` finds it automatically and asks before uploading it.

**D2. Title, description, chapters, tags — mostly automatic.** `upload_youtube.py`'s
`build_description()` generates the full description for you: hook + watch-next tease above
the fold, chapters (from `items.json` for a listicle, none yet for narrative — see
`IMPLEMENTATION.md`'s open gaps), links, subscribe line, tags, and the music credit — all
from existing project/DNA state. **The one thing that needs a real human decision is the
title.** Genus-level, common name, matches the hook. Set it via `manifest.json`'s `"title"`
field, or pass `--title` at upload time. Never tag `#shorts`.

**D3. Upload.**
```powershell
python upload_youtube.py --project {Project}
```
Needs a real terminal — it prompts interactively (thumbnail? pinned comment now or edit?)
unless you pass `--skip-comment`. Lands as a **private draft**, uploads the SRT as a subtitle
track, writes `youtube_video_id`/`youtube_video_url` back onto the manifest.

**D4. Publish.** Studio → confirm thumbnail is set → confirm title → set Public. Manual —
the API can create and edit a draft, but making it public is left as a deliberate human step.

**D5. Pinned comment — must come after D4, not before.** YouTube's API rejects comment
creation on videos still set to **private** (confirmed for real on Etiolation_S1's upload:
`403 forbidden`, "insufficient permissions"). The comment text itself
(`build_pinned_comment()`, the full ranked index with timestamps for a listicle) can be
generated any time — just don't try to post it until the video is public or unlisted.

**D6. Pin the comment.** Studio → Comments → ⋮ → Pin to top. The API cannot do this step.

**D7. Update tracking.** No long-form equivalent of Shorts' `sync_shorts_tracker.py` exists
yet. Note the upload manually wherever you track published videos until this is built.

---

## Fast reference — commands in order

```powershell
# B: script + source doc already placed by hand in {Project}\

# C1
python run_pipeline.py --project {Project} --start-from voiceover --dry-run-prompts --skip-upload
# <- HARD STOP: review prompts_review.json

# C3
python run_pipeline.py --project {Project} --start-from images --prompts-file "<ABS PATH>" --skip-upload

# C4
python make_contact_sheet.py --project {Project}

# C5 (Python 3.11)
C:\Users\Girir\AppData\Local\Programs\Python\Python311\python.exe stitch_video_longform.py --project {Project}

# C7 (Python 3.11)
C:\Users\Girir\AppData\Local\Programs\Python\Python311\python.exe verify_output.py --project {Project}

# D3 — only when explicitly asked for
python upload_youtube.py --project {Project} --skip-comment
```

---

## Known gaps (as of 2026-08-11 — check `CLAUDE.md`'s BACKLOG for anything newer)

- **No species-overuse check.** Variety across B-roll shots relies on prose instruction only;
  a species can dominate 60%+ of non-item shots with nothing flagging it. Caught by human
  review on Etiolation_S1, twice (once at the original dry-run, once again during the post-
  publish review pass documented in `CLAUDE.md`). Watch for this by eye every time.
- **No caption line-wrap tuning.** Font size is a channel_dna default now (28pt, lowered from
  an untuned 36pt placeholder), but how many words land on one burned caption line is fixed
  in the shared `generate_srt.py`, not overridable per-channel yet.
- **No thumbnail automation.**
- **No long-form view/publish tracker.**
- **Chapters only exist for listicle format** — a narrative video's YouTube description has
  no automated chapter markers yet (nothing currently marks section boundaries the way
  `stamp_items.py` marks item boundaries for a listicle).

For deeper detail on any of the above — why a check works the way it does, what bug it was
built to catch, what's shared vs. forked — see `IMPLEMENTATION.md`.
