"""
config_loader.py — longform_pipeline

Single source of truth for config loading in this pipeline. Every forked script
imports load_config() from here instead of defining its own copy (previously
duplicated in generate_images.py, generate_script.py, upload_youtube.py,
run_pipeline.py).

Two files, two concerns:
  pipeline_config.json        HOW THE MACHINE RUNS (subject-agnostic) — aspect
                               ratio, provider order, scene timing, venv paths.
  <channel_dna>/<name>.json   WHAT THE CHANNEL IS (subject-specific, brand) —
                               voice, script style, visual style, watermark,
                               YouTube metadata, the approved subject list.

WHERE THE DNA LIVES (moved 2026-08-14). It is no longer inside this repo — it
sits at C:\\Bakcup_Asus\\shared-tools\\channel_dna\\, beside the shared WhisperX
venv, because the Merge_videos composer became a second consumer of the same
DNA and the same assets (bgm.mp3, outro_card.png). Whichever project held them,
the other had to reach across into its folder, and two copies would drift.
pipeline_config.json's "channel_dna_file" is a RELATIVE pointer
("../../shared-tools/channel_dna/aeonium_glow.json") so the whole C:\\Bakcup_Asus
tree stays relocatable. That pointer was the ONLY change the move required —
_resolve_dna_path() already honoured absolute paths and joined relative ones
against scripts_dir, and channel_assets_dir() derives the assets folder from it.

load_config() reads pipeline_config.json, resolves its "channel_dna_file"
pointer, and shallow-merges the DNA dict over it (DNA wins on key collision).
The result is one flat dict — every existing config.get("some_key") call site
in the forked scripts is unchanged; only where the value now comes from is
different.

Channel-scoped assets (bgm.mp3, and later a watermark logo, intro/outro
stings, custom fonts) live in <channel_dna>/<name>/, adjacent to
<channel_dna>/<name>.json — see channel_assets_dir() below. DNA keys naming an
asset (e.g. "bgm_file") hold a bare filename resolved against that directory,
not a config key of their own.
"""

import json
import os

from console_encoding import ensure_utf8_console
ensure_utf8_console()


def _resolve_dna_path(scripts_dir: str, config: dict) -> str:
    """Absolute path to the channel_dna_file named in config, or "" if unset."""
    dna_rel = config.get("channel_dna_file")
    if not dna_rel:
        return ""
    return dna_rel if os.path.isabs(dna_rel) else os.path.join(scripts_dir, dna_rel)


def load_config(scripts_dir: str, project_dir: str = None) -> dict:
    """
    project_dir is optional and additive: if given and
    {project_dir}/config_override.json exists, it's shallow-merged on top of
    everything else (highest priority — wins over both the base config and the
    channel DNA). This is the per-project override layer several config keys'
    own doc comments already assumed existed (e.g. item_overlay_enabled's
    "flip it on in the project's own config, not here") — it didn't, until
    Etiolation_S1 needed it for real (2026-08-06). Silent no-op when
    project_dir is omitted or the file doesn't exist — most callers don't need
    a project-level override and shouldn't have to care that this layer exists.
    """
    config_path = os.path.join(scripts_dir, "pipeline_config.json")
    if not os.path.exists(config_path):
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    dna_path = _resolve_dna_path(scripts_dir, config)
    if dna_path:
        if os.path.exists(dna_path):
            with open(dna_path, "r", encoding="utf-8") as f:
                dna = json.load(f)
            config = {**config, **dna}  # shallow merge — DNA wins on collision
        else:
            print(f"   ⚠️  channel_dna_file not found: {dna_path}")

    if project_dir:
        override_path = os.path.join(project_dir, "config_override.json")
        if os.path.exists(override_path):
            with open(override_path, "r", encoding="utf-8") as f:
                overrides = json.load(f)
            if "cta" in overrides:
                # The shallow merge below would REPLACE the DNA's entire "cta" block —
                # the ask pattern, the outro card, the subscribe line — with whatever
                # partial dict this override happens to contain, silently, no error. Per-
                # video CTA specifics (watch-next target, comment prompt) must be flat
                # cta_* keys instead (see channel_dna's own "cta" block comment and
                # cta_plan.md "Where this lives") — those merge in additively and can't
                # clobber the rest. This is the same silent-substitution shape as three
                # earlier bugs this project already hit (prompts-file path mangling, the
                # validator's species-rewrite, build_prompt_map's missing auto_prompt
                # fallback) — reject it here rather than let a fourth one through quietly.
                raise ValueError(
                    f"{override_path} has a nested \"cta\" object — this would silently "
                    f"REPLACE channel_dna's entire cta block (ask pattern, outro card, "
                    f"subscribe line), not merge into it. Use flat cta_* keys instead "
                    f"(e.g. \"cta_watch_next_title\", \"cta_comment_prompt\") — see "
                    f"channel_dna/*.json's \"cta\" block comment."
                )
            config = {**config, **overrides}  # shallow merge — project overrides win over all

    return config


def channel_assets_dir(scripts_dir: str, config: dict) -> str:
    """
    Directory holding this channel's asset files: <name>.json's assets live in
    <name>/ beside it (e.g. .../channel_dna/aeonium_glow.json ->
    .../channel_dna/aeonium_glow/). Returns "" if config has no channel_dna_file
    to derive it from — callers should treat that as "no assets dir available",
    not as an error in itself.
    """
    dna_path = _resolve_dna_path(scripts_dir, config)
    if not dna_path:
        return ""
    dna_dir = os.path.dirname(dna_path)
    stem = os.path.splitext(os.path.basename(dna_path))[0]
    return os.path.join(dna_dir, stem)
