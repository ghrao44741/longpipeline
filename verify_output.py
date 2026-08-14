"""
verify_output.py — longform_pipeline, post-stitch verification (PRODUCTION_RUNBOOK.md step C7)

Answers "did the finished video actually come out right", the sibling check to the
--dry-run-prompts / contact-sheet gates that answer the same question for images.
Every check up to now that mattered was found by a human looking at frames or
listening by ear (caption desync, the item-overlay outro bug, BGM being silently
inaudible for every long-form video before 2026-08-07). This makes those checks
measurable and repeatable instead of a judgment call each time.

Reuses shorts_pipeline2/local_mp4_analyzer.py's approach (loudness timeline via
ffprobe/ffmpeg windowed reads, transcription via openai-whisper) as a technique, not
as a dependency — that file exists for a different job (NotebookLM logo-card
detection, chapter suggestion) and is a Shorts file; nothing here imports it or edits it.

Checks (each reports PASS/FAIL with the measured value; non-zero exit on any FAIL
except (b2) and (g), which are advisory/best-effort and always report rather than fail):
  a. BGM audibility        — RMS/dBFS in the guaranteed-speech-free clip tail
                              (video_end .. video_end+CLIP_EXTRA) from every scene.
  b1. Caption sync          — GATING. Structural, exact, no transcription: re-derives
                              (structural)     each scene's expected SRT entries via
                              generate_srt.py's own split_caption_entries() (imported,
                              not reimplemented) against its CURRENT manifest.json
                              video_start/video_end, and asserts the SRT file actually
                              on disk matches to a few tens of milliseconds. Catches the
                              original desync bug class (SRT built from audio-space
                              start/end) and the "generate_srt.py run before the remap
                              step" ordering bypass. Instant, no GPU.
  b2. Caption sync          — ADVISORY, never fails the run. A GROSS-FAILURE DETECTOR, not
      (transcription)       a precision check — its own measured noise floor (4.2s mean,
                              15.3s worst-case on Etiolation_S1) is too coarse to reliably
                              catch a moderate, few-second error, so treat it as sensitive
                              above roughly 25-30s, where a real problem stands clearly
                              outside the noise (exactly how it caught the 96kHz
                              sample-rate bug at 40+s). See check_caption_sync_advisory()'s
                              docstring for why it can't be gating (segmentation
                              granularity mismatch between generate_srt.py's chunking and
                              a transcriber's, not video imprecision — confirmed via seven
                              direct frame extractions on Etiolation_S1, 2026-08-07/08).
  c. Stream integrity       — resolution, fps, duration, codec, pix_fmt, audio.
  d. Duration vs manifest   — video duration vs. sum(audio_duration + CLIP_EXTRA).
  e. Black / freeze frames  — ffmpeg blackdetect / freezedetect.
  f. Loudness               — integrated LUFS + true peak via ebur128.
  g. Overlay presence       — best-effort pixel-variance sample of the watermark
                              region, and (listicle only) the item-number region
                              at each item's timestamp. Report, don't fail.

Usage (Python 3.11 — see requirement note below):
    C:/Users/Girir/AppData/Local/Programs/Python/Python311/python.exe verify_output.py --project Etiolation_S1
    ...  --project Etiolation_S1 --whisper-model base --skip-caption-sync-advisory

Output:
    {project}/output/verify_report.txt   (full detail)
    stdout: one-screen PASS/FAIL summary

Requires: ffmpeg/ffprobe on PATH, openai-whisper, pydub, numpy, Pillow, mutagen.
Requires Python 3.11 specifically — check_caption_structural() imports
split_caption_entries() from shorts_pipeline2/generate_srt.py (shared, not copied),
which imports mutagen at module level even though split_caption_entries() itself never
uses it. Same interpreter stitch_video_longform.py already requires for the same
package; confirmed it also has whisper/pydub/numpy/Pillow, so no second environment
is needed.
"""

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_loader import load_config  # noqa: E402
from stitch_video_longform import resolve_outro_card  # noqa: E402 -- same dir, not cross-pipeline

# generate_srt.py is edited in place in shorts_pipeline2, not copied here (same rationale
# as stitch_video_longform.py's own cross-directory import) — the structural check needs
# split_caption_entries() itself, not a reimplementation that could silently drift from it.
_SHORTS_PIPELINE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shorts_pipeline2")
)
if _SHORTS_PIPELINE_DIR not in sys.path:
    sys.path.insert(0, _SHORTS_PIPELINE_DIR)

from console_encoding import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

CLIP_EXTRA = 0.5  # must match stitch_video_longform.py's own constant


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def ffprobe_json(path: str, args: list) -> dict:
    cmd = ["ffprobe", "-v", "error", "-print_format", "json"] + args + [path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}:\n{result.stderr}")
    return json.loads(result.stdout or "{}")


def audio_duration(path: str) -> float:
    data = ffprobe_json(path, ["-show_entries", "format=duration"])
    return float(data["format"]["duration"])


def parse_srt(path: str) -> list:
    """Returns [{"start": float, "end": float, "text": str}, ...]."""
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    def to_seconds(ts):
        h, m, s_ms = ts.split(":")
        s, ms = s_ms.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

    entries = []
    blocks = re.split(r"\n\s*\n", raw.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 2:
            continue
        time_line_idx = 1 if lines[0].strip().isdigit() else 0
        m = re.match(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})",
                      lines[time_line_idx].strip())
        if not m:
            continue
        text = " ".join(lines[time_line_idx + 1:]).strip()
        entries.append({"start": to_seconds(m.group(1)), "end": to_seconds(m.group(2)), "text": text})
    return entries


def norm_words(text: str) -> list:
    return re.findall(r"[a-z0-9']+", text.lower())


# ═══════════════════════════════════════════════════════════════════════════════
# (a) BGM AUDIBILITY
# ═══════════════════════════════════════════════════════════════════════════════

def _window_dbfs(video_path: str, start_s: float, duration_s: float) -> float:
    """
    Extract [start_s, start_s+duration_s) directly via ffmpeg into a small temp WAV and
    measure its dBFS with pydub — never loads the whole (multi-minute) file into pydub at
    once. Deliberate, not an optimization: pydub.AudioSegment.from_file() silently
    truncated a 602.6s file's audio to 537.983s on Etiolation_S1 (2026-08-08).

    NOT a pydub length limit — confirmed wrong (2026-08-08 correction; see
    tests/test_window_dbfs.py's docstring for the evidence and CLAUDE.md's writeup for the
    full trace). A synthetic 600s 44100Hz stereo AAC fixture does not truncate; pydub reads
    it in full. The real cause is inconsistent audio-stream metadata written into THIS
    pipeline's stitched containers specifically: ffprobe -count_frames on the real file
    finds 23169 AAC frames (=538.0s) while the same stream's duration_ts claims 602.55s.
    Traced (via direct reproduction with the real pipeline code, both at small scale on a
    handful of real clips and confirmed on the full Etiolation_S1 output) to
    concatenate_clips(): every per-scene clip from build_clip_from_image()/
    build_clip_from_video() renders its VIDEO for audio_duration+CLIP_EXTRA seconds but
    leaves its AUDIO input unpadded, so each clip's real audio is ~CLIP_EXTRA seconds
    SHORTER than its own video. Concatenating ~100+ such mismatched clips via ffmpeg's
    concat demuxer + re-encode writes an audio-stream duration_ts that doesn't match the
    real decoded sample count — full/unbounded decoders (pydub's whole-file load, plain
    `ffmpeg -i ... -vn out.wav` with no -t, ffprobe -count_frames) all stop at the same
    real point; a BOUNDED read with an explicit -t (this function's approach, confirmed
    directly against the real file including windows well past the 538s mark) retrieves
    real, correct audio throughout. The audio is genuinely present; only readers that try
    to decode to EOF in one unbounded pass are affected. Where exactly in the concat
    demuxer's duration bookkeeping this gets written wrong is not fully isolated — treat
    that as an open detail, not a solved mechanism; what's fixed here is routing around the
    symptom, which is enough for this file's own needs.
    Returns float("-inf") on failure (matches pydub's own silent-audio convention) so
    callers can filter it the same way as any other non-finite sample.
    """
    import tempfile
    from pydub import AudioSegment

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = os.path.join(tmp, "window.wav")
        cmd = ["ffmpeg", "-y", "-ss", str(start_s), "-t", str(duration_s),
               "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
               wav_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not os.path.exists(wav_path):
            return float("-inf")
        try:
            return AudioSegment.from_file(wav_path).dBFS
        except Exception:
            return float("-inf")


def check_bgm_audibility(project_dir: str, video_path: str, config: dict, scripts_dir: str) -> dict:
    manifest_path = os.path.join(project_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        scenes = json.load(f)["scenes"]

    samples = []
    for scene in scenes:
        v_end = scene.get("video_end")
        if v_end is None:
            continue
        # The last ~0.4s of every clip is guaranteed speech-free: every clip
        # renders audio_duration + CLIP_EXTRA seconds long, so [video_end,
        # video_end + CLIP_EXTRA] never contains narration, only BGM (if present).
        #
        # Before the 2026-08-08 apad fix (build_clip_from_image/video), this window was
        # speech-free but NOT gap-free: the un-padded audio input ended before its clip's
        # video did, so concatenate_clips() propagated an actual packet gap into roughly
        # this same window on every clip boundary -- BGM silently dropped to explicit
        # digital silence (~-91 dBFS) there instead of continuing, which this check had no
        # way to distinguish from "BGM genuinely absent." apad makes the narration track
        # continuous (silence-padded, not gapped) up to each clip's real video length, so
        # this window now reliably samples continuous BGM as intended. See CLAUDE.md.
        window_start = v_end + 0.05
        window_duration = CLIP_EXTRA - 0.10
        if window_duration <= 0:
            continue
        samples.append(_window_dbfs(video_path, window_start, window_duration))

    # The outro card, when enabled, is the cleanest possible BGM sample that will ever
    # exist — for a card WITHOUT outro_card_narration scenes, its whole duration is
    # narration-free by construction (build_outro_card_clip() renders it with a silent
    # audio track; only the later BGM mix pass puts anything audible there at all), unlike
    # a clip tail's ~0.4s window sandwiched between real narration. For a card WITH a
    # narrated scene (spoken CTA under the card, see run_stitch()'s outro_card_narration
    # handling), only the portion AFTER the narration is still pure BGM — that's why the
    # sampling window below starts at total - silent_card_seconds, not total - outro_seconds.
    # Sample nearly the whole span (small margins to avoid the mix's own fade-in/edges) as
    # a high-confidence data point alongside the per-clip-tail samples.
    # total_duration comes from ffprobe (audio_duration(), already proven accurate
    # throughout this file), never from a full-file pydub load -- see _window_dbfs()'s
    # docstring for why that specifically cannot be trusted at this file's length.
    outro_sample_dbfs = None
    _, outro_seconds = resolve_outro_card(scripts_dir, config)
    if outro_seconds:
        # A scene flagged outro_card_narration plays UNDER the head of the card's hold
        # (see stitch_video_longform.py's run_stitch()) -- only the portion AFTER that is
        # still genuinely narration-free by construction. Sampling the narrated head here
        # would silently mix real speech into what this check treats as a pure-BGM sample.
        narrated_card_seconds = sum(
            audio_duration(os.path.join(project_dir, s["audio"])) + CLIP_EXTRA
            for s in scenes if s.get("outro_card_narration")
            and os.path.exists(os.path.join(project_dir, s["audio"]))
        )
        silent_card_seconds = max(outro_seconds - narrated_card_seconds, 0.0)
        total_duration = audio_duration(video_path)
        margin = 0.5
        outro_start = max(0.0, total_duration - silent_card_seconds + margin)
        outro_window_duration = total_duration - margin - outro_start
        if outro_window_duration > 0:
            outro_sample_dbfs = _window_dbfs(video_path, outro_start, outro_window_duration)
            if outro_sample_dbfs != float("-inf"):
                samples.append(outro_sample_dbfs)

    if not samples:
        return {"name": "BGM audibility", "passed": False,
                "detail": "No speech-free windows found to sample — cannot verify."}

    finite = [s for s in samples if s != float("-inf")]
    mean_dbfs = sum(finite) / len(finite) if finite else float("-inf")
    max_dbfs = max(finite) if finite else float("-inf")
    min_dbfs = min(finite) if finite else float("-inf")

    # These are two genuinely different populations, not one -- collapsing them into a
    # single expected band has been wrong three times (2026-08-08): clip tails sit right
    # after a narration decay/room-tone tail and read louder (~-25 dBFS mean on
    # Etiolation_S1), while the outro card is the ONLY point in the video that is BGM
    # completely on its own and reads quieter (~-38 dBFS). A single "typical" range that
    # tries to describe both ends up either too wide to mean anything or silently
    # describing just one population while looking like it covers both. State them
    # separately instead of re-deriving a combined band a fourth time.
    passed = mean_dbfs > -50
    detail = (f"n={len(samples)} windows, mean={mean_dbfs:.1f} dBFS, "
              f"min={min_dbfs:.1f}, max={max_dbfs:.1f} dBFS -- pools two different "
              f"populations (clip-tail windows typically ~-20 to -30 dBFS; the outro card, "
              f"BGM completely alone, typically ~-35 to -40 dBFS); <-50 means silent/absent")
    if outro_sample_dbfs is not None:
        detail += f" | outro-card high-confidence sample: {outro_sample_dbfs:.1f} dBFS"
    return {"name": "BGM audibility", "passed": passed, "detail": detail}


# ═══════════════════════════════════════════════════════════════════════════════
# (b1) CAPTION SYNC — STRUCTURAL (gating)
# ═══════════════════════════════════════════════════════════════════════════════

def check_caption_structural(project_dir: str, srt_path: str, tolerance: float = 0.05) -> dict:
    """
    GATING. The ground truth for caption sync is the manifest, not a transcript — the
    manifest's video_start/video_end are what stitch_video_longform.py actually used to
    place every clip, so the question that matters structurally is "does the SRT on disk
    actually reflect the manifest's CURRENT values", not "does an independent transcription
    roughly agree". Re-derives each scene's expected SRT entries by calling
    generate_srt.py's own split_caption_entries() (imported from shorts_pipeline2, not
    reimplemented — a reimplementation could silently drift from the real chunking logic)
    against the manifest's current video_start/video_end, then asserts the SRT file
    actually on disk matches to within `tolerance` (default 50ms, comfortably above
    floating-point/millisecond-rounding noise but far tighter than any real desync).

    Catches exactly the bug class this whole verification effort exists for: an SRT built
    from stale audio-space start/end instead of the remapped video_start/video_end, or
    generate_srt.py having been run before write_video_timeline() — either produces an SRT
    that structurally disagrees with the current manifest, caught here instantly, no GPU,
    no transcription. It CANNOT catch video_start itself being computed wrong, since both
    sides of this comparison derive from the same value — that's check_caption_sync_advisory()'s
    job (as a gross-failure detector, not a precise one — see that function's docstring),
    which is why that check stays advisory rather than being folded into this one.

    Known, narrow blind spot: this check imports and calls the REAL split_caption_entries(),
    not a reimplementation — deliberately, so a difference in behavior between this check and
    the actual generate_srt.py can never produce a false failure. The tradeoff is that a bug
    INSIDE split_caption_entries() itself would make "expected" and "actual" agree (both
    derived from the same buggy function) and this check would pass regardless. That gap is
    covered from the other direction, not from this one: shorts_pipeline2/tests/test_generate_srt.py
    exercises split_caption_entries() directly and independently (short text, long text
    splitting proportionally by word count, short-chunk merging) — stated explicitly here so
    the coverage story isn't left implicit.
    """
    manifest_path = os.path.join(project_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        scenes = json.load(f)["scenes"]

    if not os.path.exists(srt_path):
        return {"name": "Caption sync (structural)", "passed": False, "detail": f"SRT not found: {srt_path}"}

    actual_entries = parse_srt(srt_path)

    from generate_srt import split_caption_entries  # shared, not copied -- see module header

    mismatches = []
    idx = 0
    for scene in scenes:
        video_start = scene.get("video_start")
        video_end = scene.get("video_end")
        if video_start is None or video_end is None:
            start, end = scene.get("start", 0.0), scene.get("end", 0.0)
        else:
            start, end = video_start, video_end

        expected_entries = split_caption_entries(scene["script"].strip(), start, end)
        for exp in expected_entries:
            if idx >= len(actual_entries):
                mismatches.append(f"{scene['id']}: SRT has fewer entries than the manifest implies")
                break
            act = actual_entries[idx]
            if abs(act["start"] - exp["start"]) > tolerance or abs(act["end"] - exp["end"]) > tolerance:
                mismatches.append(
                    f"{scene['id']} (SRT entry #{idx + 1}): expected [{exp['start']:.3f}, {exp['end']:.3f}]s, "
                    f"SRT has [{act['start']:.3f}, {act['end']:.3f}]s"
                )
            idx += 1

    if idx != len(actual_entries):
        mismatches.append(f"entry count mismatch: manifest implies {idx} entries, SRT has {len(actual_entries)}")

    passed = not mismatches
    detail = (f"{len(scenes)} scene(s), {idx} SRT entries checked against manifest video_start/video_end, "
              f"tolerance ±{tolerance*1000:.0f}ms")
    if mismatches:
        detail += f" -- {len(mismatches)} mismatch(es): " + "; ".join(mismatches[:5])
    return {"name": "Caption sync (structural)", "passed": passed, "detail": detail}


# ═══════════════════════════════════════════════════════════════════════════════
# (b2) CAPTION SYNC — TRANSCRIPTION SMOKE TEST (advisory, never fails the run)
# ═══════════════════════════════════════════════════════════════════════════════

def _get_whisper_words_plain(video_path: str, whisper_model: str) -> list:
    """Fallback path: plain openai-whisper, word_timestamps=True. Returns [(word, time), ...].
    Noticeably less precise than forced alignment — only used when the WhisperX
    transcription venv isn't available."""
    import whisper

    print(f"   Transcribing with plain Whisper '{whisper_model}' (this can take a few minutes)...")
    model = whisper.load_model(whisper_model)
    result = model.transcribe(video_path, verbose=False, word_timestamps=True)

    words = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []):
            token = norm_words(w.get("word", ""))
            if token:
                words.append((token[0], w["start"]))
    return words


def _get_whisperx_words(video_path: str, config: dict) -> list:
    """
    Preferred path: WhisperX forced alignment, via the separate transcription venv this
    pipeline already depends on for scene-splitting (config["transcription_venv_python"]).
    Shells out to whisperx_transcribe_helper.py rather than importing whisperx directly —
    verify_output.py runs in a different Python environment that doesn't have it (GPU-heavy
    dependency). Returns [(word, time), ...], or [] if the venv isn't configured/available
    (caller falls back to plain whisper).
    """
    venv_python = config.get("transcription_venv_python")
    if not venv_python or not os.path.exists(venv_python):
        return []

    helper_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whisperx_transcribe_helper.py")
    if not os.path.exists(helper_path):
        return []

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        out_json = os.path.join(tmp, "words.json")
        cmd = [venv_python, helper_path, video_path, out_json, config.get("whisper_device", "cuda")]
        print("   Transcribing with WhisperX (forced alignment, via transcription venv)...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not os.path.exists(out_json):
            print(f"   ⚠️  WhisperX transcription failed, falling back to plain Whisper:\n"
                  f"      {result.stderr[-500:]}")
            return []
        with open(out_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        words = []
        for w in data.get("words", []):
            token = norm_words(w.get("word", ""))
            if token:
                words.append((token[0], w["start"]))
        return words


def check_caption_sync_advisory(video_path: str, srt_path: str, whisper_model: str, config: dict,
                                 flag_threshold: float = 15.0) -> dict:
    """
    ADVISORY ONLY — never fails the run (always "passed": True), regardless of the measured
    offset. NOT a fine-grained check: its own measured noise floor on Etiolation_S1 was
    4.2s mean / 15.3s worst-case, even with WhisperX forced alignment — so any real
    video_start error small enough to plausibly occur (a few seconds) would be buried in
    that noise and this check would not reliably surface it. Read it instead as a
    GROSS-FAILURE DETECTOR: sensitive above roughly 25-30s, where a real problem stands
    clearly outside the noise floor rather than blending into it. That is not a demotion —
    it is exactly what this check is for. It is exactly how it caught the 96kHz
    sample-rate bug at 40+ seconds (2026-08-07): far too large to be noise, easy to
    separate from normal variation. check_caption_structural() is what actually gates on
    precise timing; this check's job is catching the class that check structurally cannot
    see — video_start itself being computed wrong, where the SRT and the manifest would
    still agree with each other (both derived from the same bad value) — but only at the
    magnitude where it stands out from this check's own noise, not at the magnitude where
    it would matter for a moderate, few-second error.

    Root cause of that noise floor (recorded so nobody retunes this expecting a different
    result): SEGMENTATION MISALIGNMENT, not intra-entry interpolation error.
    generate_srt.py's split_caption_entries() chunks each scene by WORD COUNT (2 wrapped
    lines at a time, MAX_LINE_CHARS-wide) into fixed-size caption blocks; a transcriber
    chunks by where it hears actual pauses in SPEECH. Entry #K in the SRT and "segment" #K
    in a transcript are answering different questions about where to draw a boundary, so
    even a word-for-word-identical, perfectly-synced transcript pairs up with the wrong SRT
    entry as soon as the two chunking schemes diverge — which happens quickly. This was
    directly confirmed on Etiolation_S1 (2026-08-07/08): every "worst offset" this check
    ever reported, across three matching-algorithm iterations and two transcription engines
    (plain Whisper, WhisperX), was manually verified via direct frame extraction to be
    correctly synced in the actual video — seven such checks, seven confirmations. Do not
    interpret a large number from this check alone as evidence of a real desync; cross-check
    with a direct frame extraction first, exactly as this investigation did — and do not
    raise flag_threshold to "fix" nuisance failures the way a gating check would need,
    because this check no longer gates anything.
    """
    if not os.path.exists(srt_path):
        return {"name": "Caption sync (advisory)", "passed": True, "detail": f"SRT not found: {srt_path}"}

    srt_entries = parse_srt(srt_path)
    if not srt_entries:
        return {"name": "Caption sync (advisory)", "passed": True, "detail": "SRT has no parseable entries."}

    whisper_words = _get_whisperx_words(video_path, config)
    engine = "WhisperX (forced alignment)"
    if not whisper_words:
        whisper_words = _get_whisper_words_plain(video_path, whisper_model)
        engine = f"plain Whisper '{whisper_model}' (WhisperX unavailable)"

    if not whisper_words:
        return {"name": "Caption sync (advisory)", "passed": True, "detail": "Transcription produced no words."}

    window = 10.0
    offsets = []
    worst = None
    unmatched_entries = 0
    for entry in srt_entries:
        entry_word_list = norm_words(entry["text"])
        if not entry_word_list:
            continue
        candidates = [(w, t) for w, t in whisper_words if entry["start"] - window <= t <= entry["end"] + window]

        per_word_offsets = []
        for ew in entry_word_list[:3]:
            occurrences = [t for w, t in candidates if w == ew]
            if not occurrences:
                continue
            nearest_t = min(occurrences, key=lambda t: abs(t - entry["start"]))
            per_word_offsets.append(nearest_t - entry["start"])

        if not per_word_offsets:
            unmatched_entries += 1
            continue
        per_word_offsets.sort()
        offset = per_word_offsets[len(per_word_offsets) // 2]  # median
        offsets.append(abs(offset))
        if worst is None or abs(offset) > abs(worst[0]):
            worst = (offset, entry["start"], entry["text"][:60])

    if not offsets:
        return {"name": "Caption sync (advisory)", "passed": True,
                "detail": "Could not confidently match any SRT entry to a nearby transcribed word."}

    mean_offset = sum(offsets) / len(offsets)
    worst_offset, worst_t, worst_text = worst
    flagged = abs(worst_offset) > flag_threshold
    detail = (f"engine={engine}, n={len(offsets)} matched entries (of {len(srt_entries)}, "
              f"{unmatched_entries} unmatched within +/-{window}s), mean |offset|={mean_offset:.3f}s, "
              f"worst |offset|={abs(worst_offset):.3f}s at t={worst_t:.1f}s ({worst_text!r}), "
              f"informational threshold={flag_threshold}s (never fails the run)"
              + (" -- ABOVE THRESHOLD, cross-check with a direct frame extraction, do not assume desync" if flagged else ""))
    return {"name": "Caption sync (advisory)", "passed": True, "detail": detail}


# ═══════════════════════════════════════════════════════════════════════════════
# (c) STREAM INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════════

def check_stream_integrity(video_path: str) -> dict:
    data = ffprobe_json(video_path, ["-show_format", "-show_streams"])
    streams = data.get("streams", [])
    v = next((s for s in streams if s["codec_type"] == "video"), None)
    a = next((s for s in streams if s["codec_type"] == "audio"), None)

    problems = []
    if v is None:
        problems.append("no video stream")
    else:
        if (v.get("width"), v.get("height")) != (1920, 1080):
            problems.append(f"resolution {v.get('width')}x{v.get('height')} != 1920x1080")
        if v.get("pix_fmt") != "yuv420p":
            problems.append(f"pix_fmt {v.get('pix_fmt')!r} != yuv420p")
    if a is None:
        problems.append("no audio stream")
    else:
        if not a.get("sample_rate") or not a.get("channels"):
            problems.append("audio stream missing sample_rate/channels")

    duration = float(data.get("format", {}).get("duration", 0.0))
    fps = v.get("avg_frame_rate", "?") if v else "?"
    codec = v.get("codec_name", "?") if v else "?"
    sr = a.get("sample_rate", "?") if a else "?"
    ch = a.get("channels", "?") if a else "?"

    detail = (f"video: {v.get('width') if v else '?'}x{v.get('height') if v else '?'} "
              f"@ {fps}fps, codec={codec}, pix_fmt={v.get('pix_fmt') if v else '?'} | "
              f"audio: {a.get('codec_name') if a else 'MISSING'}, {sr}Hz, {ch}ch | "
              f"duration={duration:.1f}s"
              + (f" | PROBLEMS: {'; '.join(problems)}" if problems else ""))
    return {"name": "Stream integrity", "passed": not problems, "detail": detail}


# ═══════════════════════════════════════════════════════════════════════════════
# (d) DURATION vs MANIFEST
# ═══════════════════════════════════════════════════════════════════════════════

def check_duration_vs_manifest(project_dir: str, video_path: str, config: dict, scripts_dir: str,
                                per_clip_tolerance: float = 0.06) -> dict:
    """
    per_clip_tolerance scales with scene count rather than a flat threshold, because
    every clip's "-t <duration>" gets quantized to whole frames at 30fps (~0.033s
    granularity) when rendered — on Etiolation_S1 (122 scenes) this alone accounted
    for +4.32s of harmless cumulative rounding, which a flat ±1.5s tolerance would
    have failed. A genuinely dropped or duplicated clip shows up as a jump on the
    order of that ONE clip's own length (several seconds), not spread evenly across
    every clip — this tolerance is sized to absorb quantization while still catching
    that.

    Adds the outro card's resolved length when cta.outro_card is enabled and its asset
    resolves — stitch_video_longform.py appends it as a real extra clip after all scene
    clips (see resolve_outro_card()/build_outro_card_clip()), so the manifest's own
    scene-only sum will always be short by exactly that much once the card is in use.
    Without this, every stitch with an outro card enabled would fail this check by
    ~outro_seconds even though nothing is actually wrong — the same "measuring the wrong
    thing" failure shape this check was already redesigned once to avoid.
    """
    manifest_path = os.path.join(project_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        scenes = json.load(f)["scenes"]

    expected = 0.0
    narrated_card_seconds = 0.0
    missing_audio = []
    for scene in scenes:
        aud_path = os.path.join(project_dir, scene["audio"])
        if not os.path.exists(aud_path):
            missing_audio.append(scene["id"])
            continue
        clip_seconds = audio_duration(aud_path) + CLIP_EXTRA
        expected += clip_seconds
        if scene.get("outro_card_narration"):
            narrated_card_seconds += clip_seconds

    if missing_audio:
        return {"name": "Duration vs manifest", "passed": False,
                "detail": f"{len(missing_audio)} scene(s) missing audio files, "
                          f"cannot compute expected duration: {missing_audio[:5]}"}

    # A scene flagged outro_card_narration plays UNDER the outro card itself (see
    # stitch_video_longform.py's run_stitch()) -- its clip is already counted above, so
    # only the REMAINING silent portion of outro_seconds gets appended as a separate clip.
    # Adding the full outro_seconds here too would double-count the narrated portion.
    _, outro_seconds = resolve_outro_card(scripts_dir, config)
    if outro_seconds:
        expected += max(outro_seconds - narrated_card_seconds, 0.0)

    actual = audio_duration(video_path)
    diff = actual - expected
    tolerance = max(1.5, per_clip_tolerance * len(scenes))
    passed = abs(diff) <= tolerance
    net_outro = max(outro_seconds - narrated_card_seconds, 0.0) if outro_seconds else None
    detail = (f"expected={expected:.2f}s (sum of {len(scenes)} clip durations"
              + (f" + {net_outro:g}s outro card" if net_outro is not None else "") + "), "
              f"actual={actual:.2f}s, diff={diff:+.2f}s (tolerance ±{tolerance:.2f}s, "
              f"scaled for {len(scenes)} clips' frame-quantization)")
    return {"name": "Duration vs manifest", "passed": passed, "detail": detail}


# ═══════════════════════════════════════════════════════════════════════════════
# (e) BLACK / FREEZE FRAMES
# ═══════════════════════════════════════════════════════════════════════════════

def check_black_freeze(project_dir: str, video_path: str, config: dict, scripts_dir: str,
                       near_total_ratio: float = 0.85) -> dict:
    """
    freezedetect is a poor raw signal for this content: every clip is a deliberately
    subtle Ken Burns pan/zoom (~4% over several seconds, "barely perceptible" by
    stitch_video_longform.py's own design) over locally-flat macro photography
    (blurred windowsill backgrounds). That combination produces real but small
    frame-to-frame deltas — freezedetect flagged 115/122 clips as "frozen" at its
    lenient default, and STILL flagged 56 even at an aggressively strict -80dB
    (2026-08-07). Tightening the noise threshold further chases zero, not
    correctness — confirmed by directly diffing two frames inside a flagged window
    and finding real, non-zero pixel change.

    What actually distinguishes a false positive (slow pan, flagged for PART of a
    clip) from a real bug (a stuck/duplicated frame spanning nearly all of it) is
    what FRACTION of its containing clip's own duration the freeze consumes. A
    freeze is only reported as a real problem if it covers more than
    near_total_ratio of the clip it falls in — i.e. the clip is ~entirely static,
    which no amount of subtle Ken Burns motion should ever produce.

    One exception (2026-08-14): the outro card. A scene flagged outro_card_narration renders
    with force_static (no Ken Burns — see run_stitch()), and the silent outro card clip is a
    held frame by construction. Both are 100% static ON PURPOSE, so a freeze spanning the whole
    span there is the design, not a stuck frame. Those regions are excluded from the
    real-problem classification and counted as "attributed to static outro card" instead.
    """
    manifest_path = os.path.join(project_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        scenes = json.load(f)["scenes"]
    clip_ranges = [
        (s["video_start"], s["video_end"] + CLIP_EXTRA, s["id"])
        for s in scenes if s.get("video_start") is not None and s.get("video_end") is not None
    ]

    # Static-by-design regions: outro_card_narration scenes (force_static) plus the silent
    # outro card clip (held frame). Freezes inside these are expected, not bugs.
    static_ranges = [
        (s["video_start"], s["video_end"] + CLIP_EXTRA, s["id"])
        for s in scenes if s.get("outro_card_narration")
        and s.get("video_start") is not None and s.get("video_end") is not None
    ]
    _, outro_seconds = resolve_outro_card(scripts_dir, config)
    if outro_seconds:
        total_duration = audio_duration(video_path)
        static_ranges.append((max(0.0, total_duration - outro_seconds), total_duration, "outro_card"))

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", "blackdetect=d=0.5:pic_th=0.98,freezedetect=n=-60dB:d=1.5",
        "-an", "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr

    black_hits = re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", stderr)
    freeze_hits = re.findall(
        r"freeze_start: ([\d.]+)\s*\n.*?freeze_duration: ([\d.]+)\s*\n.*?freeze_end: ([\d.]+)",
        stderr, re.DOTALL,
    )

    real_problems = []
    benign_count = 0
    static_count = 0
    for start_s, dur_s, end_s in freeze_hits:
        start, dur = float(start_s), float(dur_s)
        static = next((r for r in static_ranges if r[0] <= start < r[1]), None)
        if static is not None:
            # Static-by-design (outro narration scene or the card hold) — the freeze IS the
            # design, not a stuck frame. Count separately so the report explains why it's not
            # a problem instead of lumping it into the Ken Burns bucket.
            static_count += 1
            continue
        containing = next((r for r in clip_ranges if r[0] <= start < r[1]), None)
        if containing is None:
            real_problems.append(f"freeze at {start:.1f}s ({dur:.1f}s) -- no containing clip found")
            continue
        clip_start, clip_end, clip_id = containing
        clip_len = clip_end - clip_start
        ratio = dur / clip_len if clip_len > 0 else 1.0
        if ratio > near_total_ratio:
            real_problems.append(f"{clip_id} is {ratio:.0%} frozen ({dur:.1f}s of {clip_len:.1f}s clip) "
                                  f"at {start:.1f}s -- likely a stuck/duplicated frame")
        else:
            benign_count += 1

    for start, end, dur in black_hits:
        real_problems.append(f"black {start}s-{end}s ({dur}s)")

    detail = (f"{len(black_hits)} black segment(s), {len(freeze_hits)} freeze segment(s) detected "
              f"({benign_count} attributed to normal slow Ken Burns motion, <{near_total_ratio:.0%} "
              f"of their clip; {static_count} attributed to static outro card / narrated card scene; "
              f"{len(real_problems) - len(black_hits)} span >{near_total_ratio:.0%} "
              f"of their clip and are treated as real)")
    if real_problems:
        detail += " -- " + "; ".join(real_problems[:8])
    return {"name": "Black/freeze frames", "passed": not real_problems, "detail": detail}


# ═══════════════════════════════════════════════════════════════════════════════
# (f) LOUDNESS
# ═══════════════════════════════════════════════════════════════════════════════

def check_loudness(video_path: str, target_lufs: float = -14.0, tolerance: float = 3.0) -> dict:
    cmd = ["ffmpeg", "-i", video_path, "-af", "ebur128=peak=true", "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr

    # ebur128 prints periodic "I: ... LUFS" readings throughout playback (early ones are
    # transient, before the meter converges — often near-silent-looking) AND a final
    # "Summary:" block with the real integrated reading. Must anchor on the Summary
    # block specifically, not just take any "I:" match — grabbing the first one read as
    # -70 LUFS ("silent") on a video that measured -14.3 LUFS at the end, on Etiolation_S1
    # (2026-08-07). The summary's "True peak:" block uses a single "Peak:" value, unlike
    # the periodic lines' stereo "FTPK:"/"TPK:" pairs, so it's unambiguous too.
    summary_match = re.search(
        r"Integrated loudness:\s*\n\s*I:\s*(-?[\d.]+)\s*LUFS.*?"
        r"True peak:\s*\n\s*Peak:\s*(-?[\d.]+)\s*dBFS",
        stderr, re.DOTALL,
    )

    if not summary_match:
        return {"name": "Loudness", "passed": False,
                "detail": "ebur128 produced no Summary block (integrated-loudness reading)."}

    integrated = float(summary_match.group(1))
    true_peak = float(summary_match.group(2))
    delta = integrated - target_lufs
    passed = abs(delta) <= tolerance
    detail = (f"integrated={integrated:.1f} LUFS (target {target_lufs} ±{tolerance}, "
              f"delta={delta:+.1f})"
              + (f", true peak={true_peak:.1f} dBFS" if true_peak is not None else ""))
    return {"name": "Loudness", "passed": passed, "detail": detail}


# ═══════════════════════════════════════════════════════════════════════════════
# (g) OVERLAY PRESENCE — best-effort, always reports, never fails the run
# ═══════════════════════════════════════════════════════════════════════════════

def _crop_std(video_path: str, t: float, box: tuple) -> float:
    """Extract one frame at t, return the std-dev of pixel intensity within box
    (x, y, w, h) as a rough proxy for 'is there text/logo here, or flat background'."""
    import numpy as np
    from PIL import Image
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        frame_path = os.path.join(tmp, "frame.png")
        cmd = ["ffmpeg", "-y", "-ss", str(t), "-i", video_path, "-frames:v", "1",
               "-update", "1", frame_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not os.path.exists(frame_path):
            return -1.0
        im = Image.open(frame_path).convert("L")
        x, y, w, h = box
        crop = im.crop((x, y, x + w, y + h))
        arr = np.array(crop, dtype=float)
        return float(arr.std())


def check_overlay_presence(project_dir: str, video_path: str, config: dict) -> dict:
    data = ffprobe_json(video_path, ["-show_entries", "stream=width,height", "-select_streams", "v:0"])
    stream = data.get("streams", [{}])[0]
    width, height = stream.get("width", 1920), stream.get("height", 1080)

    wm_position = config.get("watermark_position", "bottom-left")
    wm_box_w, wm_box_h = 320, 60
    pos_map = {
        "bottom-left":  (30, height - 90, wm_box_w, wm_box_h),
        "bottom-right": (width - wm_box_w - 30, height - 90, wm_box_w, wm_box_h),
        "top-left":     (30, 30, wm_box_w, wm_box_h),
        "top-right":    (width - wm_box_w - 30, 30, wm_box_w, wm_box_h),
    }
    wm_box = pos_map.get(wm_position, pos_map["bottom-left"])

    duration = audio_duration(video_path)
    sample_times = [duration * f for f in (0.1, 0.3, 0.5, 0.7, 0.9)]
    wm_stds = [_crop_std(video_path, t, wm_box) for t in sample_times]
    wm_stds = [s for s in wm_stds if s >= 0]
    wm_avg = sum(wm_stds) / len(wm_stds) if wm_stds else -1

    lines = [f"watermark region ({wm_position}): avg pixel std-dev={wm_avg:.1f} "
             f"across {len(wm_stds)} sample(s) (very low ~<5 may mean no text present)"]

    items_path = os.path.join(project_dir, "items.json")
    manifest_path = os.path.join(project_dir, "manifest.json")
    if os.path.exists(items_path) and os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            scenes = json.load(f)["scenes"]
        item_starts = [(s["item_number"], s["item_name"], s["video_start"])
                        for s in scenes if s.get("item_number") is not None and s.get("video_start") is not None]
        if item_starts:
            ov_position = config.get("item_overlay_position", "top-left")
            ov_box_w, ov_box_h = 500, 70
            ov_pos_map = {
                "top-left":     (30, 30, ov_box_w, ov_box_h),
                "top-right":    (width - ov_box_w - 30, 30, ov_box_w, ov_box_h),
                "bottom-left":  (30, height - 100, ov_box_w, ov_box_h),
                "bottom-right": (width - ov_box_w - 30, height - 100, ov_box_w, ov_box_h),
            }
            ov_box = ov_pos_map.get(ov_position, ov_pos_map["top-left"])
            item_stds = []
            for n, name, start in item_starts:
                s = _crop_std(video_path, start + 1.0, ov_box)
                if s >= 0:
                    item_stds.append((n, name, s))
            if item_stds:
                avg = sum(s for _, _, s in item_stds) / len(item_stds)
                low = [f"#{n} {name}" for n, name, s in item_stds if s < 5]
                lines.append(f"item-number region ({ov_position}): avg pixel std-dev={avg:.1f} "
                             f"across {len(item_stds)} item(s)"
                             + (f" -- possibly missing at: {', '.join(low)}" if low else ""))

    return {"name": "Overlay presence (best-effort)", "passed": True, "detail": " | ".join(lines)}


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Post-stitch verification for longform_pipeline output")
    parser.add_argument("--project", required=True, help="Project folder name or absolute path")
    parser.add_argument("--whisper-model", default="base", help="Whisper model for the advisory caption-sync check")
    parser.add_argument("--skip-caption-sync-advisory", action="store_true",
                         help="Skip check (b2) -- it's the slowest (full transcription) and advisory-only. "
                              "Check (b1), the structural gating check, always runs (instant, no transcription).")
    args = parser.parse_args()

    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = (args.project if os.path.isabs(args.project)
                    else os.path.join(scripts_dir, args.project))
    if not os.path.isdir(project_dir):
        print(f"❌ Project folder not found: {project_dir}")
        sys.exit(1)

    manifest_path = os.path.join(project_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        episode = os.path.basename(json.load(f)["episode"].rstrip("/\\"))

    output_dir = os.path.join(project_dir, "output")
    video_path = os.path.join(output_dir, f"{episode}_captioned.mp4")
    srt_path = os.path.join(output_dir, f"{episode}_captions.srt")
    if not os.path.exists(video_path):
        print(f"❌ Captioned video not found: {video_path}")
        sys.exit(1)

    config = load_config(scripts_dir, project_dir)

    print(f"\n{'═' * 60}")
    print(f"  VERIFY OUTPUT — {os.path.basename(project_dir)}")
    print(f"{'═' * 60}\n")

    results = []

    print("[a] BGM audibility...")
    results.append(check_bgm_audibility(project_dir, video_path, config, scripts_dir))

    print("[b1] Caption sync (structural, gating)...")
    results.append(check_caption_structural(project_dir, srt_path))

    if args.skip_caption_sync_advisory:
        print("[b2] Caption sync (advisory)... SKIPPED (--skip-caption-sync-advisory)")
    else:
        print("[b2] Caption sync (advisory)...")
        results.append(check_caption_sync_advisory(video_path, srt_path, args.whisper_model, config))

    print("[c] Stream integrity...")
    results.append(check_stream_integrity(video_path))

    print("[d] Duration vs manifest...")
    results.append(check_duration_vs_manifest(project_dir, video_path, config, scripts_dir))

    print("[e] Black/freeze frames...")
    results.append(check_black_freeze(project_dir, video_path, config, scripts_dir))

    print("[f] Loudness...")
    results.append(check_loudness(video_path))

    print("[g] Overlay presence (best-effort)...")
    results.append(check_overlay_presence(project_dir, video_path, config))

    # ── Report ────────────────────────────────────────────────────────────
    report_path = os.path.join(output_dir, "verify_report.txt")
    lines = [f"verify_output.py report — {os.path.basename(project_dir)}", f"video: {video_path}", ""]
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        lines.append(f"[{status}] {r['name']}")
        lines.append(f"       {r['detail']}")
        lines.append("")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n{'═' * 60}")
    print(f"  SUMMARY")
    print(f"{'═' * 60}")
    any_fail = False
    for r in results:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        if not r["passed"] and r["name"] != "Overlay presence (best-effort)":
            any_fail = True
        print(f"  {status}  {r['name']}")
        print(f"          {r['detail']}")
    print(f"\n  Full report: {report_path}")
    print(f"{'═' * 60}\n")

    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
