"""
stitch_video_longform.py — AeoniumGlow Long-form Pipeline
Landscape 1920×1080, Ken Burns, watermark, SRT captions.

Adapted from the sibling long-form pipeline's stitch script (The Interested Indian) —
see BUILD_BRIEF.md §7. Differences from that source and from stitch_video_complete.py
(Shorts):
  • Resolution  : 1920×1080 (landscape) vs 1080×1920 (vertical, Shorts)
  • Ken Burns   : upscales to 3840×2160 for headroom, zoompan outputs 1920×1080
  • Mascot layer: removed — Interested-Indian-specific, no Aeonium Glow equivalent
  • CTA card    : removed — read from {project}/../common/cta/, which doesn't exist in
                  this layout. No long-form CTA-card concept in Phase 1.
  • Watermark   : ported from stitch_video_complete.py's add_watermark() (resolution-
                  agnostic already) — Interested Indian's version had none
  • BGM lookup  : ported from stitch_video_complete.py's find_bgm_path() (checks
                  {project_dir} then {scripts_dir}) — Interested Indian's version
                  hardcoded {project_dir}/bgm.mp3 only and rendered silently music-free
                  if absent
  • Captions    : SRT burn (standard subtitle at bottom-third, not karaoke ASS)
                  Upload the .srt to YouTube as a subtitle track too
  • Config      : bgm_volume, watermark_text/color/fontsize/position, caption font size
                  all read from config_loader.load_config() (channel_dna-merged), not
                  hardcoded constants

Usage:
    python stitch_video_longform.py --project MyVideo
    python stitch_video_longform.py --project MyVideo --skip-captions

Requirements:
    ffmpeg on PATH
    pip install mutagen
    stamp_manifest.py, generate_srt.py in shorts_pipeline2 (imported cross-directory,
    not copied — see BUILD_BRIEF.md §4)
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

from mutagen.mp3 import MP3

from console_encoding import ensure_utf8_console
ensure_utf8_console()

from config_loader import load_config, channel_assets_dir

# stamp_manifest.py / generate_srt.py are edited in place in shorts_pipeline2, not copied
# here — see BUILD_BRIEF.md §4. strip_trailing_hallucinations() and other WhisperX/caption
# fixes only need to land once; forking these would let this pipeline drift out of sync.
_SHORTS_PIPELINE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shorts_pipeline2")
)
if _SHORTS_PIPELINE_DIR not in sys.path:
    sys.path.insert(0, _SHORTS_PIPELINE_DIR)

try:
    from stamp_manifest import stamp_manifest
    from generate_srt import generate_srt
    _CAPTION_PIPELINE_AVAILABLE = True
except ImportError as e:
    _CAPTION_PIPELINE_AVAILABLE = False
    _CAPTION_IMPORT_ERROR = str(e)

# ── constants ─────────────────────────────────────────────────────────────────
FPS               = 30
RESOLUTION        = "1920x1080"   # landscape long-form
KEN_BURNS_ENABLED = True
KEN_BURNS_ZOOM_RATIO = 1.04       # 4% zoom — barely perceptible, readable text


# ═══════════════════════════════════════════════════════════════════════════════
# KEN BURNS — landscape variant
# ═══════════════════════════════════════════════════════════════════════════════

def ken_burns_filter(scene_index: int, duration_seconds: float, fps: int) -> str:
    """
    Slow Ken Burns pan/zoom for 1920×1080 landscape output.
    4 alternating variants so consecutive scenes move differently.
    Entirely self-contained within each clip — cannot cause sync drift.
    """
    total_frames = max(1, int(duration_seconds * fps))
    variant = scene_index % 4

    if variant == 0:                             # slow zoom-in, drift top-left
        zoom_expr = f"min(zoom+0.0015,{KEN_BURNS_ZOOM_RATIO})"
        x_expr = "iw/2-(iw/zoom/2)-ow*0.02"
        y_expr = "ih/2-(ih/zoom/2)-oh*0.02"
    elif variant == 1:                           # slow zoom-in, drift bottom-right
        zoom_expr = f"min(zoom+0.0015,{KEN_BURNS_ZOOM_RATIO})"
        x_expr = "iw/2-(iw/zoom/2)+ow*0.02"
        y_expr = "ih/2-(ih/zoom/2)+oh*0.02"
    elif variant == 2:                           # slow zoom-out, center
        zoom_expr = f"if(eq(on,0),{KEN_BURNS_ZOOM_RATIO},max(zoom-0.0015,1.0))"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    else:                                        # very slow zoom-in, center
        zoom_expr = f"min(zoom+0.0012,{KEN_BURNS_ZOOM_RATIO})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    return (
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={total_frames}:s=1920x1080:fps={fps}"   # ← landscape output
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE LOOKUP
# ═══════════════════════════════════════════════════════════════════════════════

def get_audio_duration(path: str) -> float:
    return MP3(path).info.length


def ffprobe_duration(path: str) -> float:
    """
    Real container duration via ffprobe -- VIDEO space, not audio space. Needed wherever a
    real render is compared against total_duration accumulated as sum(audio_duration +
    CLIP_EXTRA): that accumulator is audio-space and drifts from the actual rendered video
    by ~CLIP_EXTRA + frame-quantization per clip (confirmed 4.8s over 122 clips on
    Etiolation_S1, 2026-08-08) -- see CLAUDE.md's audio-space-vs-video-space entries.
    """
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def find_video_source(project_dir: str, scene_id: str,
                      visual_group_id: str) -> tuple:
    """
    Returns (source_path, source_type).
    Priority: scene video > scene image > group video > group image.
    No CTA card logic (long-form doesn't use it).
    """
    video_path = os.path.join(project_dir, "videos", f"{scene_id}.mp4")
    if os.path.exists(video_path):
        return video_path, "video"

    for ext in [".png", ".jpg", ".jpeg"]:
        image_path = os.path.join(project_dir, "images", f"{scene_id}{ext}")
        if os.path.exists(image_path):
            return image_path, "image"

    if visual_group_id:
        group_video = os.path.join(project_dir, "videos", f"{visual_group_id}.mp4")
        if os.path.exists(group_video):
            return group_video, "video"
        for ext in [".png", ".jpg", ".jpeg"]:
            group_image = os.path.join(project_dir, "images", f"{visual_group_id}{ext}")
            if os.path.exists(group_image):
                return group_image, "image"

    return None, None


def resolve_channel_asset(filename: str, scripts_dir: str, config: dict) -> str:
    """
    Resolve a channel-specific asset file (bgm.mp3, and later a watermark logo,
    intro/outro sting, or custom font) against channel_dna/<name>/ — the directory
    convention established in Phase 1 Closeout §D.8. Returns "" if the channel
    assets dir can't be derived (no channel_dna_file) or the file isn't in it;
    callers needing a project-override/legacy-root fallback compose this with
    their own checks (see find_bgm_path()) rather than this function growing
    per-caller fallback logic itself.
    """
    assets_dir = channel_assets_dir(scripts_dir, config)
    if not assets_dir:
        return ""
    candidate = os.path.join(assets_dir, filename)
    return candidate if os.path.exists(candidate) else ""


def find_bgm_path(project_dir: str, scripts_dir: str, config: dict) -> str:
    """
    Locate the BGM file. Priority:
      1. {project_dir}/{bgm_file}          project-level override
      2. {channel assets dir}/{bgm_file}   channel default — see resolve_channel_asset()
      3. {scripts_dir}/{bgm_file}          legacy root — deprecated, warns loudly if hit
    Returns "" if config declares no bgm_file at all (BGM genuinely not wanted).

    Raises FileNotFoundError if bgm_file IS declared but resolves nowhere — a
    missing asset must fail loudly, not render silently music-free. This is a
    stricter contract than the version this file started with (ported from
    stitch_video_complete.py), which returned "" either way and let the render
    proceed music-free with no warning (see BUILD_BRIEF.md §7) — a real risk now
    that there's an extra resolution candidate to get wrong.
    """
    bgm_file = config.get("bgm_file")
    if not bgm_file:
        return ""

    candidates = []

    project_bgm = os.path.join(project_dir, bgm_file)
    candidates.append(project_bgm)
    if os.path.exists(project_bgm):
        return project_bgm

    assets_dir = channel_assets_dir(scripts_dir, config)
    if assets_dir:
        channel_bgm = os.path.join(assets_dir, bgm_file)
        candidates.append(channel_bgm)
        if os.path.exists(channel_bgm):
            return channel_bgm

    legacy_bgm = os.path.join(scripts_dir, bgm_file)
    candidates.append(legacy_bgm)
    if os.path.exists(legacy_bgm):
        print(f"   ⚠️  DEPRECATED: BGM resolved from the legacy pipeline root ({legacy_bgm}).")
        print(f"      Move it to {assets_dir or '<channel assets dir>'} instead — "
              f"see config_loader.channel_assets_dir().")
        return legacy_bgm

    raise FileNotFoundError(
        f"bgm_file '{bgm_file}' is configured but was not found in any of:\n" +
        "\n".join(f"  - {c}" for c in candidates)
    )


def add_watermark(video_path: str, output_path: str,
                  text: str = "@aeoniumglow",
                  color: str = "#F5EFE0",
                  fontsize: int = 42,
                  position: str = "bottom-left",
                  card_start: float = None):
    """
    Burn a persistent text watermark onto the video using ffmpeg drawtext.
    position: 'bottom-left' | 'bottom-right' | 'top-left' | 'top-right'

    Ported verbatim from stitch_video_complete.py's add_watermark() — already
    resolution-agnostic (position computed from ffmpeg w/h vars, not literals), so no
    16:9-specific change was needed, just wiring it into this file (BUILD_BRIEF.md §7).

    card_start: if given, the drawtext is gated to stop at this timestamp (seconds) via
    enable='lt(t,card_start)'. Used to skip the outro card span — outro_card.png already
    bakes in its own "@aeoniumglow" credit, so watermarking the whole video including that
    span produces a redundant second, larger watermark on top of it. Preferred over
    regenerating the card asset (2026-08-08).
    """
    pos_map = {
        "bottom-left":  ("50",          "h-80"),
        "bottom-right": ("w-tw-50",     "h-80"),
        "top-left":     ("50",          "50"),
        "top-right":    ("w-tw-50",     "50"),
    }
    x, y = pos_map.get(position, ("50", "h-80"))

    hex_color = color.lstrip("#")
    ffmpeg_color = f"0x{hex_color}"

    font_file = r"C:\Windows\Fonts\Arial.ttf"
    if os.path.exists(font_file):
        font_part = f"fontfile='{font_file.replace(chr(92), '/').replace(':', chr(92)+':')}'"
    else:
        font_part = ""

    enable_part = f":enable='lt(t,{card_start})'" if card_start is not None else ""

    drawtext = (
        f"drawtext={font_part}:text='{text}':"
        f"fontcolor={ffmpeg_color}@0.90:fontsize={fontsize}:"
        f"x={x}:y={y}:"
        f"shadowcolor=black@0.45:shadowx=2:shadowy=2"
        f"{enable_part}"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", drawtext,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"\n  ✗ Watermark error:\n{result.stderr[-500:]}")
        raise RuntimeError("Watermark step failed")


def build_item_overlay_windows(scenes: list, total_duration: float) -> list:
    """
    Compute one on-screen window per listicle item from manifest scenes already
    stamped by stamp_items.py (item_number/item_name on each item's opening scene,
    visual_group_id on every scene in that item's span) and remapped by
    write_video_timeline() (video_start on every timed scene).

    A window runs from its item's video_start up to the video_start of the first
    scene AFTER its own visual_group_id's contiguous block ends — not "the next
    item's video_start", which silently mislabels any non-item content between
    items (a hook, a mid-video aside) as belonging to the preceding item, and
    badly mislabels a trailing outro/"here's the fix" section after the LAST
    item as belonging to it — caught on Etiolation_S1 (2026-08-06): "#1 Echeveria
    elegans" was still on screen 120+ seconds into the outro, well past item #1's
    own content, because "last item runs to total_duration" doesn't know
    stamp_items.py's own outro_opening_line boundary exists. Falls back to
    total_duration only when the item's group genuinely runs to the end of the
    manifest with nothing after it (no outro, no narrative-format equivalent).

    Returns []  for narrative-format projects (no scene carries item_number) —
    callers should treat that as "nothing to overlay", not an error.
    """
    tagged = [s for s in scenes if s.get("item_number") is not None]
    windows = []
    for scene in tagged:
        start = scene.get("video_start")
        if start is None:
            # write_video_timeline() skips scenes without whisperx_start/end —
            # an item opening on such a scene has no reliable on-screen time.
            continue

        group_id = scene.get("visual_group_id")
        group_indices = [i for i, s in enumerate(scenes) if s.get("visual_group_id") == group_id]
        last_group_idx = max(group_indices) if group_indices else scenes.index(scene)

        end = total_duration
        for later_scene in scenes[last_group_idx + 1:]:
            later_start = later_scene.get("video_start")
            if later_start is not None:
                end = later_start
                break

        windows.append({
            "item_number": scene["item_number"],
            "item_name":   scene.get("item_name", ""),
            "start":       start,
            "end":         end,
        })
    return windows


def add_item_number_overlay(video_path: str, output_path: str, windows: list,
                             text_template: str = "#{n}  {name}",
                             color: str = "#F5EFE0",
                             fontsize: int = 54,
                             position: str = "top-left"):
    """
    Burn the listicle item number/name onto the video, one drawtext filter per
    window with an enable='between(t,start,end)' clause — same ffmpeg drawtext
    pattern as add_watermark(), just chained per-window instead of a single
    always-on filter. No-op (copies the file through) if windows is empty, so
    narrative-format projects (which never call this with non-empty windows —
    see main()) pay nothing.
    """
    if not windows:
        if video_path != output_path:
            with open(video_path, "rb") as src, open(output_path, "wb") as dst:
                dst.write(src.read())
        return

    pos_map = {
        "top-left":     ("50",      "50"),
        "top-right":    ("w-tw-50", "50"),
        "bottom-left":  ("50",      "h-80"),
        "bottom-right": ("w-tw-50", "h-80"),
    }
    x, y = pos_map.get(position, ("50", "50"))

    hex_color = color.lstrip("#")
    ffmpeg_color = f"0x{hex_color}"

    font_file = r"C:\Windows\Fonts\Arial.ttf"
    if os.path.exists(font_file):
        font_part = f"fontfile='{font_file.replace(chr(92), '/').replace(':', chr(92)+':')}':"
    else:
        font_part = ""

    def escape_text(s: str) -> str:
        # ffmpeg drawtext text= needs : and ' and \ escaped
        return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", r"\'")

    filters = []
    for w in windows:
        label = escape_text(text_template.format(n=w["item_number"], name=w["item_name"]))
        filters.append(
            f"drawtext={font_part}text='{label}':"
            f"fontcolor={ffmpeg_color}@0.95:fontsize={fontsize}:"
            f"x={x}:y={y}:"
            f"shadowcolor=black@0.55:shadowx=2:shadowy=2:"
            f"enable='between(t,{w['start']:.3f},{w['end']:.3f})'"
        )
    vf = ",".join(filters)

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"\n  ✗ Item overlay error:\n{result.stderr[-500:]}")
        raise RuntimeError("Item number overlay step failed")


# ═══════════════════════════════════════════════════════════════════════════════
# CLIP BUILDERS
# ═══════════════════════════════════════════════════════════════════════════════

def build_clip_from_video(scene_id: str, video_path: str, audio_path: str,
                           audio_duration: float, tmp_dir: str) -> str:
    """Render a scene clip from an animated .mp4 source (loops if shorter)."""
    clip_path = os.path.join(tmp_dir, f"{scene_id}.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", video_path,
        "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-vf", (
            "scale=1920:1080:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0xFAF7F2,setsar=1"
        ),
        # apad pads the (finite, un-looped) narration audio with silence out to -t's
        # video-space duration -- without it, audio ends CLIP_EXTRA (~0.5s) before video on
        # every clip, and concatenate_clips() propagates that gap into the final container's
        # audio duration_ts and into ~one BGM dropout per clip boundary (2026-08-08, see
        # CLAUDE.md).
        "-af", "apad",
        "-t", str(audio_duration + 0.5),
        "-r", str(FPS), clip_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ ffmpeg error ({scene_id} video):\n{result.stderr[-500:]}")
        raise RuntimeError(f"ffmpeg failed: {scene_id}")
    return clip_path


def build_clip_from_image(scene_id: str, image_path: str, audio_path: str,
                           audio_duration: float, tmp_dir: str,
                           scene_index: int = 0,
                           force_static: bool = False) -> str:
    """
    Render a scene clip from a still image.
    With KEN_BURNS_ENABLED: upscales to 3840×2160 (2× headroom for landscape)
    then applies zoompan → 1920×1080 output.
    force_static=True skips Ken Burns (for title cards etc.).
    """
    clip_path = os.path.join(tmp_dir, f"{scene_id}.mp4")
    total_duration = audio_duration + 0.5

    if KEN_BURNS_ENABLED and not force_static:
        vf_chain = (
            # 2× upscale for landscape headroom (3840×2160)
            "scale=3840:2160:force_original_aspect_ratio=increase,"
            "crop=3840:2160,"
            f"{ken_burns_filter(scene_index, total_duration, FPS)}"
        )
    else:
        vf_chain = (
            "scale=1920:1080:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0xFAF7F2,setsar=1"
        )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-i", audio_path,
        "-c:v", "libx264", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-vf", vf_chain,
        # apad pads the (finite) narration audio with silence out to -t's video-space
        # duration -- see build_clip_from_video()'s comment above, same reasoning.
        "-af", "apad",
        "-t", str(total_duration),
        "-r", str(FPS), clip_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ ffmpeg error ({scene_id} image):\n{result.stderr[-500:]}")
        raise RuntimeError(f"ffmpeg failed: {scene_id}")
    return clip_path


def build_outro_card_clip(image_path: str, seconds: float, tmp_dir: str) -> str:
    """
    Render the end-card pseudo-scene (cta_plan.md "End card"): a held, STATIC frame — no
    Ken Burns pan, this is deliberately calm — with a silent audio track for `seconds`.
    Silent, not absent: this clip still needs its own audio stream so concatenate_clips()
    (which maps a single continuous audio stream across the whole concatenated video) has
    something to concatenate against. The silence is exactly the point — with no narration
    audio here, mix_background_music()'s later BGM pass is the ONLY audio audible during
    this segment, which is the one moment the music is heard on its own (cta_plan.md
    "a branded still, no narration, BGM only").
    """
    clip_path = os.path.join(tmp_dir, "outro_card.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-c:v", "libx264", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-vf", (
            "scale=1920:1080:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0xFAF7F2,setsar=1"
        ),
        "-t", str(seconds),
        "-r", str(FPS), clip_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ ffmpeg error (outro card):\n{result.stderr[-500:]}")
        raise RuntimeError("ffmpeg failed: outro card")
    return clip_path


def resolve_outro_card(scripts_dir: str, config: dict) -> tuple:
    """
    Returns (image_path, seconds) if the outro card is DNA-enabled and its asset actually
    resolves, else (None, None) — the caller treats that as "no outro card", not an error.

    Deliberately does NOT use find_bgm_path()'s fail-loud contract: bgm_file being declared
    but missing is always a real misconfiguration (the file is expected to exist by the
    time anyone runs a stitch), but outro_card.enabled can be true in DNA before the asset
    has ever been generated — Phase 3 (cta_plan.md) built this support specifically so it
    would be ready the moment channel_dna/<name>/outro_card.png exists, without gating the
    rest of the pipeline on that file showing up first. Missing asset prints a visible
    warning and the stitch proceeds without an outro card — silent skip would hide a real
    typo in the DNA's "asset" filename just as easily as it would hide "not made yet".
    """
    cta = config.get("cta", {})
    outro_card_cfg = cta.get("outro_card", {})
    if not outro_card_cfg.get("enabled"):
        return None, None

    asset = outro_card_cfg.get("asset", "outro_card.png")
    seconds = outro_card_cfg.get("seconds", 18)
    image_path = resolve_channel_asset(asset, scripts_dir, config)
    if not image_path:
        assets_dir = channel_assets_dir(scripts_dir, config)
        print(f"   ⚠️  cta.outro_card.enabled is true but '{asset}' was not found in "
              f"{assets_dir or '<channel assets dir>'} — proceeding without an outro card. "
              f"Generate it (aeonium-glow-brand skill) and re-stitch to add it.")
        return None, None

    return image_path, seconds


# ═══════════════════════════════════════════════════════════════════════════════
# CONCAT + BGM
# ═══════════════════════════════════════════════════════════════════════════════

def concatenate_clips(clip_paths: list, output_path: str, tmp_dir: str):
    list_path = os.path.join(tmp_dir, "concat_list.txt")
    with open(list_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.replace(os.sep, '/')}'\n")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", list_path,
        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ ffmpeg concat error:\n{result.stderr[-500:]}")
        raise RuntimeError("ffmpeg concat failed")


def mix_background_music(video_path: str, bgm_path: str,
                          output_path: str, volume: float):
    # loudnorm brings narration to -14 LUFS regardless of how quiet ElevenLabs rendered it.
    # BGM gets a gentle fade-in (2s) so it doesn't click at the loop point.
    #
    # normalize=0 is load-bearing, not cosmetic. amix defaults to normalize=1, which
    # divides every input by the SUM of its weights — with weights=4 1 that's an extra
    # /5 on top of bgm_volume, so a configured 0.1 (-20 dB) actually renders at
    # 0.1/5 = 0.02 (-34 dB), inaudible under -14 LUFS narration. Caught on Etiolation_S1
    # (2026-08-07): BGM was silently absent in every long-form video shipped before this
    # fix, verified only by ear ("under the voice" vs "gone") until verify_output.py's
    # RMS-in-the-silent-tail check made it measurable. Dropping weights (redundant once
    # normalize=0 stops auto-scaling by them) keeps this at the configured volume
    # directly. Shorts' stitch_video_complete.py already runs the correct
    # normalize=0 + no-weights formula at the same 0.1 volume and is audible — this is
    # long-form's copy catching up, not a new design. See CLAUDE.md's traps section.
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-stream_loop", "-1", "-i", bgm_path,
        "-filter_complex", (
            f"[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[voice];"
            f"[1:a]afade=t=in:st=0:d=2,volume={volume}[bgm];"
            f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
        ),
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        # loudnorm's internal true-peak oversampling leaves the output sample rate
        # unspecified, and ffmpeg let it through as 96000Hz here (both real inputs are
        # 44100Hz) — an unusual, non-standard rate that isn't a playback bug (the
        # container's own PTS/duration stayed self-consistent) but confused an external
        # tool decoding this file: verify_output.py's Whisper-based caption-sync check
        # measured a spurious, growing "desync" up to 40+s by mid-video purely from this,
        # while directly extracted frames at those same real timestamps showed correct
        # sync throughout (2026-08-07). Force the standard rate explicitly, matching
        # Shorts' stitch_video_complete.py, which already does this.
        "-ar", "44100", "-ac", "2",
        "-shortest", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ BGM mix error:\n{result.stderr[-500:]}")
        raise RuntimeError("BGM mix failed")


# ═══════════════════════════════════════════════════════════════════════════════
# CAPTION BURN (SRT — landscape-appropriate, bottom-third)
# ═══════════════════════════════════════════════════════════════════════════════

def burn_srt_captions(video_path: str, srt_path: str, output_path: str, fontsize: int = 36):
    """
    Burn SRT captions into the video using ffmpeg subtitles filter.
    Uses bottom-third positioning (Alignment=2, MarginV=40) and a clean
    white font with black outline — appropriate for 1920×1080 landscape.

    fontsize default of 36 is a Phase 1 placeholder for Aeonium Glow specifically (the
    sibling pipeline's 28 was tuned for a different channel at the same 1920x1080 —
    picking a new value isn't about resolution, it's about this channel's own look, not
    yet established for long-form). Verify on an extracted frame and adjust via config's
    "caption_fontsize" if needed — see BUILD_BRIEF.md §7.
    """
    # ffmpeg needs forward slashes and escaped colons in Windows paths
    srt_ff = srt_path.replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", (
            f"subtitles='{srt_ff}':force_style='"
            f"FontName=Arial,FontSize={fontsize},Bold=1,"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "Outline=2,Shadow=0,"
            "Alignment=2,MarginV=40'"
        ),
        "-c:v", "libx264", "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ Caption burn error:\n{result.stderr[-500:]}")
        raise RuntimeError("Caption burn failed")


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — STITCH
# ═══════════════════════════════════════════════════════════════════════════════

def run_stitch(project_dir: str) -> str:
    """Render all scenes → {project}/output/{episode}_final.mp4. Returns output path."""
    manifest_path = os.path.join(project_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    config      = load_config(scripts_dir, project_dir)

    episode = os.path.basename(manifest["episode"].rstrip("/\\"))  # guard: strip full path if stored
    scenes  = manifest["scenes"]
    output_dir   = os.path.join(project_dir, "output")
    output_file  = os.path.join(output_dir, f"{episode}_final.mp4")
    bgm_path     = find_bgm_path(project_dir, scripts_dir, config)
    bgm_volume   = config.get("bgm_volume", 0.10)
    outro_image, outro_seconds = resolve_outro_card(scripts_dir, config)

    os.makedirs(output_dir, exist_ok=True)

    print(f"Project   : {project_dir}")
    print(f"Title     : {manifest.get('title', '—')}")
    print(f"Scenes    : {len(scenes)}")
    print(f"Resolution: {RESOLUTION}")
    print(f"Ken Burns : {'on' if KEN_BURNS_ENABLED else 'off'}  ({KEN_BURNS_ZOOM_RATIO}× zoom)")
    print(f"BGM       : {'✓ ' + bgm_path if bgm_path else '✗ none'}")
    print(f"Outro card: {f'✓ {outro_image} ({outro_seconds}s)' if outro_image else '✗ none'}")
    print(f"{'─' * 55}")

    # ── Plan sources ────────────────────────────────────────────────────────
    print("\nPlanning sources...")
    scene_plan    = []
    missing_audio = []
    video_count   = 0
    image_count   = 0

    for scene in scenes:
        scene_id       = scene["id"]
        aud_path       = os.path.join(project_dir, scene["audio"])
        visual_group   = scene.get("visual_group_id")
        source_path, source_type = find_video_source(project_dir, scene_id, visual_group)

        if not os.path.exists(aud_path):
            missing_audio.append(aud_path)

        scene_plan.append({
            "id":          scene_id,
            "source_path": source_path,
            "source_type": source_type,
            "audio_path":  aud_path,
        })

        if   source_type == "video": video_count += 1
        elif source_type == "image": image_count += 1

        label = f"[{source_type.upper()}]" if source_type else "[MISSING]"
        print(
            f"  {scene_id}  {label:<9}"
            f"  vis {'✓' if source_path else '✗'}"
            f"  aud {'✓' if os.path.exists(aud_path) else '✗'}"
        )

    print(f"\n  Video clips : {video_count}")
    print(f"  Still images: {image_count}")

    missing_sources = [s for s in scene_plan if not s["source_path"]]
    if missing_sources or missing_audio:
        print("\n✗ Cannot stitch — missing files:")
        for s in missing_sources:
            print(f"  No image/video for {s['id']}")
        for a in missing_audio:
            print(f"  Missing audio: {a}")
        sys.exit(1)

    print(f"\n  ✓ All sources resolved. Starting render...")

    # ── Render ──────────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp_dir:
        clip_paths     = []
        total_duration = 0.0

        for i, plan in enumerate(scene_plan, 1):
            aud_duration    = get_audio_duration(plan["audio_path"])
            total_duration += aud_duration + 0.5
            label           = f"[{plan['source_type'].upper()}]"
            print(f"\n[{i:03d}/{len(scenes)}] {plan['id']}  {label}  ({aud_duration:.1f}s)")

            if plan["source_type"] == "video":
                clip = build_clip_from_video(
                    plan["id"], plan["source_path"],
                    plan["audio_path"], aud_duration, tmp_dir
                )
            else:
                clip = build_clip_from_image(
                    plan["id"], plan["source_path"],
                    plan["audio_path"], aud_duration, tmp_dir,
                    scene_index=i,
                )

            clip_paths.append(clip)
            print(f"  ✓ rendered")

        # ── Outro card (cta.outro_card, DNA-gated — resolved earlier, see header) ──
        if outro_image:
            print(f"\n[outro card] {outro_seconds}s held frame, BGM only, no narration")
            outro_clip = build_outro_card_clip(outro_image, outro_seconds, tmp_dir)
            clip_paths.append(outro_clip)
            total_duration += outro_seconds
            print(f"  ✓ rendered")

        # ── Concat + optional BGM + watermark ────────────────────────────────
        print(f"\n{'─' * 55}")
        m_min, m_sec = divmod(int(total_duration), 60)
        print(f"Concatenating {len(clip_paths)} clips  (~{m_min}m {m_sec}s)...")

        pre_watermark = os.path.join(tmp_dir, "pre_watermark.mp4")

        if bgm_path:
            concat_tmp = os.path.join(tmp_dir, "concat_no_bgm.mp4")
            concatenate_clips(clip_paths, concat_tmp, tmp_dir)
            print(f"Mixing BGM at {int(bgm_volume * 100)}%...")
            mix_background_music(concat_tmp, bgm_path, pre_watermark, bgm_volume)
        else:
            concatenate_clips(clip_paths, pre_watermark, tmp_dir)

        # outro_card.png already bakes in its own "@aeoniumglow" credit — gate the
        # watermark to stop where the card begins so the two don't double up (2026-08-08).
        # Must use the REAL rendered duration (ffprobe on pre_watermark.mp4), not
        # total_duration -- that accumulator is audio-space (sum of audio_duration +
        # CLIP_EXTRA) and drifts from the actual video-space render by ~CLIP_EXTRA +
        # frame-quantization per clip (4.8s over 122 clips on Etiolation_S1). Using
        # total_duration here left 4.8s of real narration video unwatermarked.
        card_start = (ffprobe_duration(pre_watermark) - outro_seconds) if outro_image else None

        watermark_text = config.get("watermark_text", "@aeoniumglow")
        print(f"Adding {watermark_text} watermark...")
        add_watermark(
            pre_watermark, output_file,
            text=watermark_text,
            color=config.get("watermark_color", "#F5EFE0"),
            fontsize=config.get("watermark_fontsize", 42),
            position=config.get("watermark_position", "bottom-left"),
            card_start=card_start,
        )

    print(f"\n✓ Stitch done: {output_file}  (~{m_min}m {m_sec}s)")
    return output_file


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# VIDEO-TIMELINE REMAPPING — ported from shorts_pipeline2/generate_ass.py:116-174
# ═══════════════════════════════════════════════════════════════════════════════
# WhisperX timestamps (whisperx_start/whisperx_end) come from the original continuous
# narration.wav. The stitched video has a different timeline because each scene clip
# adds render padding (CLIP_EXTRA seconds of extra video after the audio — see
# build_clip_from_image/build_clip_from_video above). Without remapping, captions
# drift out of sync with each scene, worse in later scenes — this is exactly the bug
# this pass fixes (Phase 1 Closeout §A). Shorts' karaoke .ass captions already solve
# this identical problem via this identical logic; this is a port, not a new design.
#
# merged_into_next (scenes sharing their successor's clip, no own CLIP_EXTRA tail) is
# a Shorts-only concept — stitch_video_longform.py has no equivalent, so it's always
# an empty set here.

CLIP_PADDING = 0.15  # fallback pre-padding for manifests written before per-scene padding was recorded
CLIP_EXTRA   = 0.5   # seconds of extra video after audio per scene — must match build_clip_from_image/video


def build_video_timeline(scenes: list, merged_into_next: set = None) -> list:
    """For each scene, compute where it starts in the final video (video_start) and
    the actual pre-speech padding baked into its MP3. Returns list of dicts matching
    scenes order."""
    if merged_into_next is None:
        merged_into_next = set()

    timeline = []
    video_cursor = 0.0
    for scene in scenes:
        wx_start = scene.get("whisperx_start")
        mp3_start = scene.get("start", 0.0)
        mp3_end   = scene.get("end",   0.0)
        mp3_duration = mp3_end - mp3_start

        recorded_pre = scene.get("audio_pre_padding")
        if recorded_pre is not None:
            actual_pre = recorded_pre
        else:
            actual_pre = min(wx_start, CLIP_PADDING) if wx_start is not None else CLIP_PADDING

        timeline.append({
            "whisperx_start":  wx_start,
            "whisperx_end":    scene.get("whisperx_end"),
            "video_start":     video_cursor,
            "actual_pre":      actual_pre,
        })
        if scene["id"] in merged_into_next:
            video_cursor += mp3_duration
        else:
            video_cursor += mp3_duration + CLIP_EXTRA
    return timeline


def remap_time(t, timeline: list):
    """Map a timestamp from original-audio space to video-timeline space. Returns
    None if t is None (caller must not write a None-derived value onto the manifest
    — see write_video_timeline()'s guard). Falls back to the raw timestamp if scene
    boundaries are unavailable."""
    if t is None:
        return None
    for entry in timeline:
        wx_s = entry["whisperx_start"]
        wx_e = entry["whisperx_end"]
        if wx_s is None or wx_e is None:
            return t
        if wx_s <= t <= wx_e:
            t_within = t - wx_s
            return entry["video_start"] + entry["actual_pre"] + t_within
    return t


def write_video_timeline(project_dir: str):
    """
    Write video_start/video_end onto each scene in manifest.json, alongside the
    existing audio-space start/end (which this does NOT touch). generate_srt.py
    prefers these when present — see Phase 1 Closeout §A.

    Scenes missing whisperx_start/whisperx_end are skipped (not written at all,
    never written as null) — generate_srt.py's per-scene fallback handles these
    cleanly via the existing start/end or raw-duration path.
    """
    manifest_path = os.path.join(project_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    scenes = manifest["scenes"]
    timeline = build_video_timeline(scenes)

    skipped = []
    for scene, entry in zip(scenes, timeline):
        if scene.get("whisperx_start") is None or scene.get("whisperx_end") is None:
            skipped.append(scene["id"])
            continue
        scene["video_start"] = remap_time(scene["whisperx_start"], timeline)
        scene["video_end"]   = remap_time(scene["whisperx_end"], timeline)

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    written = len(scenes) - len(skipped)
    print(f"✅ video_start/video_end written for {written}/{len(scenes)} scene(s)")
    if skipped:
        print(f"   ⚠️  Skipped (no whisperx_start/end): {skipped}")


def main():
    parser = argparse.ArgumentParser(
        description="AeoniumGlow long-form stitch: 1920×1080 landscape, Ken Burns, watermark, SRT captions"
    )
    parser.add_argument(
        "--project", required=True,
        help="Project folder — relative to this script, or absolute path."
    )
    parser.add_argument(
        "--skip-captions", action="store_true",
        help="Stop after stitch — skip stamp, SRT generation, and caption burn"
    )
    args = parser.parse_args()

    script_dir  = os.path.dirname(os.path.abspath(__file__))
    project_dir = (
        args.project if os.path.isabs(args.project)
        else os.path.normpath(os.path.join(script_dir, args.project))
    )
    if not os.path.isdir(project_dir):
        print(f"❌ Project folder not found: {project_dir}")
        sys.exit(1)

    # ── Step 1: Stitch ────────────────────────────────────────────────────
    print(f"\n{'═' * 55}")
    print("STEP 1/6 — STITCH  (1920×1080 landscape)")
    print(f"{'═' * 55}\n")
    final_video = run_stitch(project_dir)

    if args.skip_captions:
        print("\n--skip-captions set. Done.")
        return

    if not _CAPTION_PIPELINE_AVAILABLE:
        print(f"\n⚠️  Caption pipeline unavailable: {_CAPTION_IMPORT_ERROR}")
        print("   stamp_manifest.py and generate_srt.py must be in the same folder.")
        sys.exit(1)

    # ── Step 2: Stamp manifest ────────────────────────────────────────────
    print(f"\n{'═' * 55}")
    print("STEP 2/6 — STAMP MANIFEST")
    print(f"{'═' * 55}\n")
    stamp_manifest(project_dir)

    # ── Step 3: Remap to video-timeline (fixes caption/video desync) ──────
    print(f"\n{'═' * 55}")
    print("STEP 3/6 — REMAP VIDEO TIMELINE")
    print(f"{'═' * 55}\n")
    write_video_timeline(project_dir)

    # ── Step 4: Item number overlay (listicle only — no-op for narrative) ──
    print(f"\n{'═' * 55}")
    print("STEP 4/6 — ITEM NUMBER OVERLAY")
    print(f"{'═' * 55}\n")
    config = load_config(script_dir, project_dir)
    with open(os.path.join(project_dir, "manifest.json"), "r", encoding="utf-8") as f:
        manifest_for_overlay = json.load(f)
    if config.get("item_overlay_enabled", False):
        scenes_for_overlay = manifest_for_overlay["scenes"]
        # Real video-space duration via ffprobe on the actual render, not a sum of
        # audio_duration + CLIP_EXTRA -- that accumulator is audio-space and drifts from
        # the real video by ~CLIP_EXTRA + frame-quantization per clip (same class of bug
        # as the watermark card_start fix above; see CLAUDE.md). build_item_overlay_windows()
        # only falls back to this value for a trailing item that runs to the true end of
        # the video, so an audio-space number here would silently truncate that item's
        # window early on any project where it's actually reached.
        total_duration = ffprobe_duration(final_video)
        windows = build_item_overlay_windows(scenes_for_overlay, total_duration)
        if windows:
            overlaid_video = final_video + ".overlay_tmp.mp4"
            add_item_number_overlay(
                final_video, overlaid_video, windows,
                text_template=config.get("item_overlay_text", "#{n}  {name}"),
                color=config.get("item_overlay_color", "#F5EFE0"),
                fontsize=config.get("item_overlay_fontsize", 54),
                position=config.get("item_overlay_position", "top-left"),
            )
            os.replace(overlaid_video, final_video)
            print(f"✓ {len(windows)} item number window(s) burned onto {final_video}")
        else:
            print("item_overlay_enabled is set but no scene carries item_number — "
                  "run stamp_items.py before stitching for listicle projects. Skipping.")
    else:
        print("item_overlay_enabled is false (default) — skipping. "
              "Set it in pipeline_config.json/channel_dna for listicle projects.")

    # ── Step 5: Generate SRT ───────────────────────────────────────────────
    print(f"\n{'═' * 55}")
    print("STEP 5/6 — GENERATE SRT")
    print(f"{'═' * 55}\n")
    generate_srt(project_dir)

    # ── Step 6: Burn SRT captions ──────────────────────────────────────────
    print(f"\n{'═' * 55}")
    print("STEP 6/6 — BURN CAPTIONS (SRT, bottom-third)")
    print(f"{'═' * 55}\n")

    with open(os.path.join(project_dir, "manifest.json"), "r", encoding="utf-8") as f:
        manifest = json.load(f)
    episode       = os.path.basename(manifest["episode"].rstrip("/\\"))  # guard: strip full path
    output_dir    = os.path.join(project_dir, "output")
    srt_path      = os.path.join(output_dir, f"{episode}_captions.srt")
    captioned_out = os.path.join(output_dir, f"{episode}_captioned.mp4")

    if os.path.exists(srt_path):
        print(f"Burning captions from {srt_path}...")
        config = load_config(os.path.dirname(os.path.abspath(__file__)), project_dir)
        burn_srt_captions(final_video, srt_path, captioned_out,
                          fontsize=config.get("caption_fontsize", 36))
        print(f"✓ Captioned: {captioned_out}")
    else:
        print(f"⚠️  SRT not found at {srt_path} — skipping burn")

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'═' * 55}")
    print(f"✅ ALL DONE — {manifest.get('title', episode)}")
    print(f"{'═' * 55}")
    print(f"  {episode}_final.mp4      ← stitched, no captions")
    print(f"  {episode}_captions.srt   ← upload to YouTube as subtitle track")
    print(f"  {episode}_captioned.mp4  ← burned-in captions, ready to post")
    print(f"\n  All files in: {output_dir}")
    print(f"\nTo re-run this episode:")
    print(f'  python stitch_video_longform.py --project "{args.project}"')


if __name__ == "__main__":
    main()
