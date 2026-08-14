---
name: produce-longform
description: Produces a complete Aeonium Glow long-form (16:9) YouTube video end-to-end, in either of two formats -- narrative (a flowing hook/sections/close video, the default) or listicle (a ranked countdown). Covers topic and source-doc selection, script approval, voiceover, scene splitting, brand-validated 16:9 image prompts, image generation, stitching with watermark and optional numbered overlays, and an optional YouTube upload. Use this whenever the user asks for a long-form or full-length video for @aeoniumglow -- phrases like "make the long-form video about root rot", "15 succulents that rot fast in regular soil", "do the etiolation countdown", "build the long video from the misting doc", or "produce the next long-form from that source doc" should all trigger it, even if they don't name it directly. Do NOT use this for Shorts; use produce-short instead. Do NOT use it for a one-off re-stitch, a single bad image, or a script tweak.
---

# Produce an Aeonium Glow long-form video

Two formats share one pipeline. **`narrative` is the default** — a flowing hook → sections →
close video, the shape of *Stop Succulent Rotting Fast: The First 5 Minutes Matter*.
**`listicle`** is a ranked countdown. Many videos have no list at all; do not assume one.

Read `longform_pipeline/BUILD_BRIEF.md` first if the pipeline has not been built yet. This
skill assumes it exists and works.

**Three hard stops**, mirroring `produce-short`: the structure, the script, and the generated
prompts. At each one, show the user the **actual content**, not a summary, and wait. Both of
the most expensive mistakes in this project's history — a silently swapped species name and a
stray caption burned into a finished video — happened on runs that looked completely clean
right up until they didn't.

Never call `upload_youtube.py` unless the user explicitly asked for an upload, or you ask at
the end and get an explicit yes.

---

## Step 0 — Inputs and format

**Scope: succulents only.** No general houseplants, tropicals, or foliage plants. Snake Plant
and cacti are botanically defensible and deliberately out of scope — an LLM filling out a list
or picking an example will reach for them, so check. Expanding scope is a channel-strategy
decision the user makes on purpose, never something a script introduces quietly.

You need a project name (no spaces), a topic, and a **domain source document**.

**Pick the format from the topic, and say which you picked.** If the user's topic contains a
count ("15 succulents that…", "the 7 signs of…") it is a listicle. If it is a process, a
diagnosis, a rescue, or an explanation, it is narrative. If genuinely ambiguous, ask — the two
produce very different videos and the choice is not reversible after scripting.

Everything from voiceover onward is identical between the formats. Only the script stage,
manifest stamping, and one optional overlay differ.

---

## Step 1 — Source doc, and the differentiation check

**Applies to both formats.**

`generate_script.py` is explicitly instructed not to state facts its source does not support —
that instruction was added after it invented an unsupported fix on its own.

1. **A domain source doc must exist before scripting.** Domain docs are per *axis*, not per
   video — one soil/drainage doc backs several soil videos. Check
   `...\Aeonium Glow\Long Videos\Source Docs\` first; you will often find the axis is already
   covered.
2. For a **listicle**, the doc must additionally **justify each rank in one line.** A ranked
   list is a series of factual claims plus an ordering claim; the justification is what makes
   the order defensible rather than vibes, and it stops the generator improvising a reason an
   item sits at #4.
3. Point `{Project}\source_doc.path` at it, in the **base** folder, per the usual convention.

**Differentiation check — do this every time, both formats.** Before writing anything, check
`shorts_session.md` Project Provenance, the `Aeonium_Glow/` package folders, and the vault
Source Docs list for content on the same axis. This project has shipped near-duplicate content
by accident before (`Propagation_S2` vs `short-04`).

A prevention/selection video and a rescue/diagnostic video on the same topic are **different
products and should cross-promote** — but only if the source doc states that scope boundary
explicitly and the new script doesn't rebuild the other video's biology section. Two or three
sentences of mechanism, then a pointer. Not a re-derivation.

---

## Step 2 — HARD STOP 1: the structure

**Narrative:** show the user the **section outline** — every section heading, in order, with a
one-line summary of what each covers. Ask whether the arc is right and whether anything is
missing or redundant against existing videos.

**Listicle:** show the user the **full ranked list, in countdown order, with the one-line
justification for each rank.** Not a count, not a summary — the actual list. Ask:
- Is anything ranked wrong?
- Is anything missing that a viewer would expect to own?
- Is #1 the right #1? It should be the highest risk × ownership, not the most dramatic
  outlier. The dramatic outlier usually belongs at #2, where it makes #1 land harder.

Everything downstream depends on this and nothing downstream can fix it.

---

## Step 3 — Species validation (BLOCKING for listicles)

`pipeline_config.json` → `approved_species` carries a small curated set.
`generate_images.py` flags any plant-mentioning prompt that does not name a species from it,
and the retry pass **rewrites the prompt to an approved species.**

**Narrative:** this is the guardrail working as designed. Leave it alone.

**Listicle:** this is a live hazard. On a 15-species list it silently swaps the plant in the
image away from the plant in the narration, once per item, and reports success. Before any
image generation:
- Every species in the item list must be in `approved_species` with a `visual` description, OR
- the run must be in listicle mode, where the item list is authoritative for `names_species()`

**Verify this actually holds** — do not assume. Generate prompts with `--dry-run-prompts` and
read them. If an item's prompt names a different plant than the item does, stop.

Taxonomy note, both formats: several common succulents are still sold under superseded names
(*Curio rowleyanus* / *Senecio rowleyanus*, *Haworthiopsis fasciata* / *Haworthia fasciata*).
Use the current name in narration, mention the trade name once so viewers recognise their own
plant, and make sure **both** forms satisfy the validator.

---

## Step 4 — Script, then HARD STOP 2

**Listicle only — `items.json` is generated from the source doc's ranked list.** One source of
truth; do not maintain a second copy. This project has been bitten repeatedly by duplicated
state. Constraint the generator must satisfy: **each item begins a new sentence**, so item
boundaries land on scene boundaries and the numbered overlay maps without fuzzy matching.

Show the user the **full script text** at the approval gate. Check yourself first.

**Both formats:**
- Does any claim exceed what the source doc's confidence markers allow?
- Does it re-derive a companion video's material instead of pointing at it?
- **Does the ending have the required two-beat structure — closing insight, then a spoken
  ask — not just the first beat?** This is a real, confirmed gap, not a hypothetical:
  Etiolation_S1 shipped with only the closing-insight beat and no spoken ask at all, caught
  only after upload by a human watching the finished video, which then required awkwardly
  splicing a new TTS clip onto an already-produced project. Check explicitly, every time,
  before voiceover ever runs: the last 1-2 sentences must include a spoken ask matching
  `channel_dna`'s `cta.comment_prompt_pattern` (specific, self-categorizing, answerable with
  one concrete detail from the viewer's own experience — never "let me know what you think").
  `subscribe` is deliberately description-surface only and is never spoken; `watch_next` is
  spoken too if `channel_dna`'s `cta.in_script_ask_beats` includes it and a real target
  video exists to point at. **The ask plays UNDER the outro card itself, not before it** —
  a scene flagged `"outro_card_narration": true` in the manifest renders the card art as its
  visual (`force_static`, no Ken Burns) with the narration audio, and the silent card's hold
  shortens by that much so the card's total on-screen time still matches
  `cta.outro_card.seconds` (`stitch_video_longform.py`'s `run_stitch()`;
  `write_burn_srt()` keeps this scene's line out of the *burned* captions, since it collides
  with the card's own on-screen text, while the CC-track SRT keeps the full transcript). This
  is a settled, evolved decision (`CLAUDE.md`, 2026-08-14) — do not change it without asking.

**Listicle only:**
- Is the shared fix stated once near the top as an open loop, with the full version promised at #1?
- Does each item have exactly one twist clause, not a full fix?
- Do the teases use **different words** at each insertion point?

---

## The listicle format, in one page

Skip this section entirely for narrative videos.

**Ranking rule — generalises to every listicle on this channel:**

> Rank by **severity on the video's problem axis × how many people own the plant.**

Not raw severity. A plant that fails instantly but that almost nobody owns ranks *below* a
plant that fails slowly in ten thousand homes. The payoff only lands if the viewer owns it.

| Video | Problem axis | Ranks by |
|---|---|---|
| Rot in regular soil | rot speed in peat-based mix | rot risk × ownership |
| Survive beginner mistakes | forgiveness | forgiveness × ownership |
| Stretch without light | etiolation speed | etiolation × ownership |

**Order:** always a countdown, #N → #1.

**Tiers** (scale proportionally for other list lengths): top third — still at risk but more
forgiving; middle third — common beginner kills; #5–#2 — high risk, very common; #1 — highest
combined risk and ownership.

**Payoff structure:**
1. Shared fix stated **once, near the top, as an open loop** — "the fix is nearly the same for
   all of them; I'll give you the exact version at number one"
2. Each item gets only its **specific twist**, one clause
3. The **full fix lands at #1**, before the CTA

Do not generate a separate full fix per item (kills pace). Do not withhold every fix until the
end (that is the catalog-channel pattern this channel exists to be better than).

**Retention glue:** teases after roughly each quarter, plus one immediately before #3. For 15
items: after #12, after #9, after #6, before #3.

> **Every tease must use different words and add new information.** Repeated identical phrasing
> on TTS narration is the clearest audible tell of synthetic voiceover — confirmed directly by
> analysing a comparable channel, where flat repetitive cadence across items was the giveaway.
> A viewer who has heard the same line three times stops hearing it the fourth.

Approved pattern (adapt specifics per video, keep the escalation):
- after #12 — "Three down. None of these are the one that's probably on your windowsill right now."
- after #9 — "Halfway. Everything left is something you've seen at a garden centre."
- after #6 — "From here it's the ones I get the most comments about."
- before #3 — "Top three. These are the ones beginners lose most." ← keep this one verbatim

**Per-video input**, which is all the authoring a listicle actually needs:

```
topic: Succulents that rot fast in regular soil
problem_axis: rot speed in peat-based potting mix
shared_fix: gritty mineral mix, full dry-down, real drainage
source_doc: <vault path>
items (15 → 1):
  15. Sempervivum tectorum | Hens and Chicks | handles damp better than most, still not safe
  ...
   1. Curio rowleyanus | String of Pearls | sold in peat everywhere, rots strand by strand
```

---

## Step 5 — Prompts, then HARD STOP 3

**Narrative:** `--dry-run-prompts` strongly recommended.
**Listicle:** `--dry-run-prompts` is **mandatory.** 15 items × 2–3 scenes is 30–45 images,
roughly 4× a Short, and the validator's retry loop multiplies the GPT-4o calls on top.

Tell the user the expected spend before generating.

Show them `prompts_review.json`. Check that every prompt:
- names the species that scene is actually about
- shows the **state the narration describes** — never the fix, never the outcome. A scene about
  a plant rotting at the base shows that plant in wet dense soil, or early basal softening. Not
  a hand repotting it into gritty mix. In a listicle, the fix appears once, at #1.
- is 16:9, not 9:16

**For every grouped shot (a `scene_id` like `group-07`, one image spanning several scenes'
`whisperx_start`/`end`), read the FULL combined `script` text for that entry, not just its
last sentence, and ask: does one static image (held with Ken Burns) actually work for
*every* line in that span, not only the line the auto-generated prompt happened to key off?
This is a real, confirmed failure mode, not a hypothetical: on Etiolation_S1, one group held
across four sentences — "Rot looks like damage. Shriveling looks like damage. A sunburned
leaf looks like damage. But a stretching succulent looks like a plant that is thriving" —
got a single "looks lush and thriving" image. The image was a perfectly reasonable match for
the *last* sentence and a flat contradiction of the first three, and nothing in prompt review,
`--dry-run-prompts`, the contact sheet, or `verify_output.py` catches this, because the prompt
text itself is entirely self-consistent — the mismatch is between the prompt and the *other*
sentences sharing its shot, not a flaw in the prompt read alone. When a grouped shot's script
spans genuinely different states (several distinct symptoms, a before/after, a list of
examples), **split it into separate shots** — remove the shared `visual_group_id` for the
scenes that need their own image (each scene then keys by its own `scene_id`) — rather than
writing one prompt that tries to average across all of them. Rhetorical-list narration
("X looks like damage. Y looks like damage. Z looks like damage. But W looks like success.")
is the pattern most likely to trigger this — watch for it specifically.

**Listicle item shots get this same bug, and the fix above is unsafe for them — do not remove
`visual_group_id` on an item shot.** Confirmed on Etiolation_S1's item-02 (Lithops): its
6-scene span opens with "A healthy Lithops sits almost flush with the gravel..." then pivots
to "the body elongates upward... losing that stone profile... eventually toppling," but held
one healthy-looking image across all of it — the exact same pattern, just inside a listicle
item instead of generic B-roll. The difference: `build_item_overlay_windows()` computes the
"#N Name" overlay's on-screen window by finding every scene that shares the *tagged* scene's
`visual_group_id` — removing it from the later scenes to give them their own image would
silently truncate the overlay early (it would end where the shrunken group now ends, not where
the item's narration actually finishes). **Instead, leave every scene's `visual_group_id`
untouched and place a per-scene image file directly** (e.g. `images/SCENE-095.png`) for just
the scenes that need a different picture — `find_video_source()` in `stitch_video_longform.py`
already checks for a scene-specific file *before* falling back to the shared group image, so
this overrides the picture for those scenes without touching the grouping the overlay depends
on. Because `generate_images.py`'s own shot-keying (`visual_group_id` or `scene_id`) can't be
reached this way — a scene with a `visual_group_id` set always keys by that, never its own
`scene_id`, so a `prompts_review.json` entry keyed by scene id is never picked up for it —
generate the replacement image directly (`generate_with_xai()`/`save_image()` from
`generate_images.py`, called standalone) rather than through the normal `--prompts-file` flow,
and copy it to each affected scene's own filename if several consecutive scenes need to share
the new state as one continuous shot. Verify afterward that the overlay window still spans the
item's full original range, not just that the new image looks right.

**Quote the paths.** A `--prompts-file` path with unquoted Windows backslashes has silently
mangled itself in this project before. It now hard-fails rather than substituting fresh
prompts, but quote them anyway.

---

## Step 6 — Images, stitch, verify

After generation, **assert every PNG in `images/` is landscape** before stitching. One line,
and it immediately catches the case where the image provider fell back to a square-cropping
path.

After stitching, verify on an **extracted frame, never the SRT**:

```powershell
ffmpeg -y -ss 120 -i <Project>/output/<Project>_captioned.mp4 -frames:v 1 check.png
```

Confirm: 1920×1080, captions readable in the bottom third, watermark present, BGM audible and
under the voice.

**For any grouped shot spanning multiple distinct narration lines, extract a frame at more
than one point in its window** (start, middle, near its end), not just one — a single frame
can look fine while a later line in the same held image is contradicted. See Step 5's note on
this same failure mode; it's cheaper to catch there (before generation) but re-check here too,
since it can still slip through a fast prompt-text read.

**Listicle only:** also confirm the numbered item overlay shows the correct number at that
timestamp, and check a frame from **inside an item**, not a transition. The overlay is the
thing most likely to be off by one, and it is invisible in every other check.

---

## Step 7 — Upload

Only if explicitly asked, or the user says yes when asked at the end. This step performs real,
side-effectful actions on the channel's YouTube account — treat it with the same care as any
other "send/publish on someone's behalf" action, not as a routine pipeline stage.

**Title is the one thing that needs a real decision; everything else is automatic.**
`upload_youtube.py`'s `build_description()` generates the full description from existing
project state — hook (first two sentences of `script.txt`), watch-next tease (from
`config_override.json`'s flat `cta_watch_next_*` keys, if set), chapters (from `items.json`
for a listicle, none yet for narrative), links, the subscribe line, tags, and the music credit
— all `channel_dna`-driven. Set the real title via `manifest.json`'s `"title"` field before
uploading (it defaults to the bare project name otherwise — an easy thing to forget), or pass
`--title` at upload time. Confirm before running:
- `manifest.json`'s `"title"` is a real, genus-level, common-name title — not the project name
- `youtube_tags` (channel_dna) does not contain `shorts`
- chapters will come from `items.json` (listicle) or don't exist yet (narrative) — never
  hand-author them

**Check the outro card's watch-next line before every upload — it is a single shared channel
asset, not per-project.** `resolve_outro_card()` always resolves
`channel_dna/aeonium_glow/outro_card.png` (no per-project override exists for this asset,
unlike `bgm_file`) — whatever it currently says is what every video shares until someone
regenerates it. If this video's `cta_watch_next_title` differs from what the card currently
shows, regenerate it and then copy it into place — **its own `--out` default writes inside
`outro_card_src/`, one level below the real live asset, not the live asset itself**:
```powershell
python channel_dna/aeonium_glow/outro_card_src/render_outro_card.py --watch-next-title "..."
copy channel_dna\aeonium_glow\outro_card_src\outro_card.png channel_dna\aeonium_glow\outro_card.png
```
That overwrites the live shared asset — the *previous* video's card is gone the moment a new
one is copied in. If two videos need to stay live with different cards simultaneously, render
to a distinct filename and point `cta.outro_card.asset` at it instead of copying over the
default; that's not the common case today.

**OAuth is already set up, shared with Shorts** — `pipeline_config.json`'s `credentials_dir`
points at `../shorts_pipeline2/`, where `client_secrets.json` and a cached
`youtube_token.pickle` already live. Nothing to configure per-video.

**Thumbnail (optional):** drop `thumbnail.png` (`.jpg`/`.jpeg` also work) into the project
folder *before* uploading — `upload_youtube.py` auto-detects it and asks before attaching. No
automated thumbnail generation exists; build one separately (e.g. the `aeonium-glow-brand`
skill) or extract a frame.

```powershell
python upload_youtube.py --project {Project} --skip-comment
```

**Needs a real terminal, same trap as `generate_script.py`'s approval gate.** Without
`--skip-comment`, it prompts interactively for the pinned comment (`Post this comment?
[y/n/edit]`) and, if a thumbnail file was found, for whether to upload it. In a
non-interactive/agent context, always pass `--skip-comment` and handle the comment as a
separate, explicit step (below) — don't try to drive the interactive prompt.

Lands as a **private draft**, uploads the SRT as a subtitle track, writes
`youtube_video_id`/`youtube_video_url` back onto `manifest.json`.

**Pinned comment must come *after* the video is public or unlisted, not before.** Confirmed
directly (2026-08-11, real API call): YouTube returns `403 forbidden,
"insufficient permissions"` when creating a comment thread on a still-private video. Generate
the comment text any time via `build_pinned_comment()` (full ranked index with timestamps for
a listicle) and show it to the user, but don't attempt to post it until after Step 7's manual
publish step below — and posting it is its own distinct public action, so confirm with the
user before posting even once the video is public.

**After publishing, use `post_update.py` to sync status and post the pinned comment —
added 2026-08-14, this pipeline now has its own copy (ported from
`shorts_pipeline2/post_update.py`, not the same file, this one builds its comment text from
this pipeline's own `build_pinned_comment()`):**

```powershell
python post_update.py --project {Project}
```

Run any time after upload. It always syncs live status (privacy, title, published date) into
`manifest.json`; it only *posts* the pinned comment once the video is actually public or
unlisted — checks the real live privacy status itself before attempting, so running it
against a still-private draft is safe and just syncs status, prints why it skipped posting,
and exits cleanly rather than repeating the 403 `upload_youtube.py --skip-comment` trap.
Skips re-posting if `manifest.json` already has a `youtube_pinned_comment_id` (use
`--force-comment` to post again anyway); `--text`/`--text-file` override the pipeline-built
comment; `--no-comment` syncs status only, never posts.

**Manual, no API path:** publishing the draft to Public (Studio → confirm thumbnail/title →
Public), and pinning a posted comment to the top (Studio → Comments → ⋮ → Pin to top — the API
cannot do this step even once a comment exists).
