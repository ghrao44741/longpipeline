"""
upload_youtube.py — AeoniumGlow Long-form Pipeline
Uploads the final captioned video to YouTube as a private draft.
Also uploads the SRT as a subtitle track, and posts a pinned comment.

First-time setup:
  1. Go to Google Cloud Console → Create project → Enable YouTube Data API v3
  2. Create OAuth 2.0 credentials (Desktop app) → download as client_secrets.json
  3. Place client_secrets.json in the same folder as this script
  4. Run this script — a browser window opens for one-time auth → saves youtube_token.pickle

Subsequent runs are fully headless (uses saved token).

Usage:
    python upload_youtube.py --project Etiolation_S1
    python upload_youtube.py --project Etiolation_S1 --title "Custom title" --description "..."
    python upload_youtube.py --project Etiolation_S1 --skip-comment

After upload, the script offers to post a pinned comment — for a listicle (items.json present,
cta.pinned_comment_mode == "ranked_index" in channel_dna), the full ranked list with timestamps,
generated from items.json + the manifest's video_start; otherwise the DNA's
youtube_pinned_comment prompt text (narrative / prompt_only mode). The YouTube API cannot pin
automatically; after posting, go to YouTube Studio → Comments → click ⋮ next to your comment →
Pin to top.

Requires:
    pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
"""

import argparse
import json
import os
import pickle
import sys
import time

from console_encoding import ensure_utf8_console
ensure_utf8_console()

from config_loader import load_config  # single source of truth, see config_loader.py

# ── optional .env support ─────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
except ImportError:
    print("❌ Google API libraries not installed.")
    print("   Run: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2")
    sys.exit(1)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

MAX_RETRIES  = 5
RETRY_DELAY  = 5   # seconds between retries


def get_authenticated_service(scripts_dir: str, credentials_dir: str = None):
    """
    Authenticate via OAuth and return the YouTube API service.

    credentials_dir (from pipeline_config.json's "credentials_dir"), if set, points at
    where client_secrets.json / youtube_token.pickle actually live — for this pipeline,
    shorts_pipeline2's own credentials, so the same YouTube channel isn't authenticated
    via two independently-refreshing tokens. Relative paths resolve against scripts_dir.
    Falls back to scripts_dir itself when unset, matching prior behavior.
    """
    creds_dir = scripts_dir
    if credentials_dir:
        creds_dir = (credentials_dir if os.path.isabs(credentials_dir)
                     else os.path.normpath(os.path.join(scripts_dir, credentials_dir)))

    token_path   = os.path.join(creds_dir, "youtube_token.pickle")
    secrets_path = os.path.join(creds_dir, "client_secrets.json")

    creds = None

    if os.path.exists(token_path):
        with open(token_path, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("   Refreshing YouTube token...")
            creds.refresh(Request())
        else:
            if not os.path.exists(secrets_path):
                print(f"❌ client_secrets.json not found at {secrets_path}")
                print()
                print("Setup steps:")
                print("  1. Go to https://console.cloud.google.com")
                print("  2. Create a project → Enable 'YouTube Data API v3'")
                print("  3. APIs & Services → Credentials → Create OAuth 2.0 Client ID")
                print("     Application type: Desktop app")
                print("  4. Download JSON → rename to client_secrets.json")
                print(f"  5. Place it in: {creds_dir}")
                sys.exit(1)

            print("   Opening browser for YouTube authentication (one-time)...")
            flow  = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "wb") as f:
            pickle.dump(creds, f)
        print("   ✅ Token saved.")

    return build("youtube", "v3", credentials=creds)


def upload_video(youtube, video_path: str, title: str, description: str,
                 tags: list, category_id: str, made_for_kids: bool,
                 language: str) -> str:
    """Upload the video and return the YouTube video ID."""
    body = {
        "snippet": {
            "title":        title,
            "description":  description,
            "tags":         tags,
            "categoryId":   category_id,
            "defaultLanguage":      language,
            "defaultAudioLanguage": language,   # required for captions to activate automatically
        },
        "status": {
            "privacyStatus":     "private",
            "selfDeclaredMadeForKids": made_for_kids,
            "madeForKids":       made_for_kids,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=8 * 1024 * 1024,  # 8 MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    print(f"   Uploading video: {os.path.basename(video_path)}")
    print(f"   Title          : {title}")
    print(f"   Privacy        : private (draft)")

    response = None
    retry = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"   Progress       : {pct}%", end="\r")
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retry < MAX_RETRIES:
                retry += 1
                print(f"   ⚠️  Transient error ({e.resp.status}), retrying {retry}/{MAX_RETRIES}...")
                time.sleep(RETRY_DELAY * retry)
            else:
                raise

    print()
    video_id = response["id"]
    print(f"   ✅ Uploaded: https://youtu.be/{video_id}")
    return video_id


def upload_thumbnail(youtube, video_id: str, thumbnail_path: str):
    """Upload a thumbnail image to the video."""
    ext      = os.path.splitext(thumbnail_path)[1].lower()
    mimetype = "image/png" if ext == ".png" else "image/jpeg"
    media    = MediaFileUpload(thumbnail_path, mimetype=mimetype)
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=media,
        ).execute()
        print(f"   ✅ Thumbnail uploaded: {os.path.basename(thumbnail_path)}")
    except HttpError as e:
        print(f"   ⚠️  Thumbnail upload failed: {e}")
        print("      You can set it manually in YouTube Studio.")


def upload_subtitle(youtube, video_id: str, srt_path: str, language: str = "en"):
    """Upload SRT as a subtitle caption track."""
    body = {
        "snippet": {
            "videoId":    video_id,
            "language":   language,
            "name":       "",
            "isDraft":    False,
        }
    }
    media = MediaFileUpload(srt_path, mimetype="application/octet-stream")

    try:
        youtube.captions().insert(
            part="snippet",
            body=body,
            media_body=media,
        ).execute()
        print(f"   ✅ Subtitles uploaded: {os.path.basename(srt_path)}")
    except HttpError as e:
        print(f"   ⚠️  Subtitle upload failed: {e}")
        print("      You can add captions manually in YouTube Studio.")


def post_pinned_comment(youtube, video_id: str, comment_text: str) -> str | None:
    """
    Post a top-level comment on the video as the channel owner.
    Returns the comment ID if successful, None on failure.

    Note: The YouTube Data API does not expose a pin endpoint.
    After posting, go to Studio → Comments → click the ⋮ menu → Pin.
    """
    try:
        response = youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text
                        }
                    }
                }
            }
        ).execute()
        comment_id = response["id"]
        print(f"   ✅ Comment posted (ID: {comment_id})")
        print(f"   📌 To pin: Studio → Comments → ⋮ menu next to your comment → Pin")
        return comment_id
    except HttpError as e:
        error_reason = ""
        try:
            error_detail = json.loads(e.content)
            error_reason = error_detail.get("error", {}).get("errors", [{}])[0].get("reason", "")
        except Exception:
            pass
        if error_reason == "commentsDisabled":
            print("   ⚠️  Comments are disabled on this video — skipping.")
        else:
            print(f"   ⚠️  Comment post failed: {e}")
            print("      Post it manually from YouTube Studio if needed.")
        return None


def format_chapter_timestamp(seconds: float) -> str:
    """YouTube chapter format: M:SS, or H:MM:SS past the first hour."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def build_chapters(manifest: dict, include_intro: bool = True, intro_label: str = "Intro") -> list:
    """
    Returns [(seconds, label), ...] for a listicle's item countdown, using item_number/
    item_name/video_start already stamped on manifest scenes by stamp_items.py and
    write_video_timeline(). Returns [] for narrative projects (no scene carries
    item_number) — callers should treat that as "no chapters", not an error; narrative
    chapters from section headings aren't generated yet (nothing currently marks section
    boundaries the way stamp_items.py marks item boundaries — see CLAUDE.md BACKLOG).

    YouTube requires the first chapter to start at 0:00, at least 3 chapters 10s+ apart,
    and ascending order — a synthetic "Intro" chapter is prepended to guarantee the 0:00
    requirement regardless of where the first item actually starts. include_intro=False
    for callers that just want the item list itself (e.g. the pinned comment, which has no
    0:00 requirement and shouldn't show a meaningless "Intro" row).
    """
    scenes = manifest.get("scenes", [])
    tagged = [
        (s["video_start"], s["item_number"], s.get("item_name", ""))
        for s in scenes
        if s.get("item_number") is not None and s.get("video_start") is not None
    ]
    if not tagged:
        return []
    tagged.sort(key=lambda t: t[0])
    chapters = [(0.0, intro_label)] if include_intro else []
    for start, n, name in tagged:
        chapters.append((start, f"#{n} {name}".strip()))
    return chapters


def build_description(project_dir: str, manifest: dict, config: dict,
                       custom_description: str = None) -> str:
    """
    Long-form description (cta_plan.md "PER-SURFACE SPECIFICS — Description"). The first
    two lines are above the fold and the only ones most viewers see — they carry the hook
    and the watch-next tease, not channel boilerplate. Then a script-derived summary sentence
    (if the script states its intent with an "I am going to..."-style marker), then chapters
    (listicle only), then a per-video comment CTA (config_override.json's cta_comment_prompt,
    if set), then links, then the subscribe line, then tags. Never #shorts — that's a Shorts
    leftover this function used to carry unmodified; long-form isn't a Short.

    Watch-next target is per-video, read from FLAT cta_watch_next_* keys in the project's
    own config_override.json (never a nested "cta" object — config_loader.py rejects that,
    see its own docstring) — cta.ask_priority puts watch_next first, matching the in-script
    ask's own ordering.
    """
    if custom_description:
        return custom_description

    channel = config.get("channel_handle", "@aeoniumglow")

    script_path = os.path.join(project_dir, "script.txt")
    hook = ""
    if os.path.exists(script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            script_text = f.read().strip()
        sentences = script_text.replace("...", "…").split(". ")
        hook = ". ".join(sentences[:2]).strip()
        if hook and not hook.endswith("."):
            hook += "."

    watch_next_title = config.get("cta_watch_next_title", "").strip()
    watch_next_id    = config.get("cta_watch_next_id", "").strip()
    watch_next_why   = config.get("cta_watch_next_why", "").strip()

    # ── Summary block (script-derived "what this video does" sentence) ────────
    # Looks for the first sentence with a first-person intent marker ("I am going
    # to…", "I will…", "We'll…", "In this video…") — in scripts written to the
    # channel template this is the sentence that states the video's mission
    # (e.g. Etiolation_S1: "I am going to count down ten succulents that stretch
    # when the light is not enough…"). Falls back to nothing if absent — a
    # narrative that never states intent stays hook + chapters, no invented copy.
    summary = ""
    if os.path.exists(script_path):
        with open(script_path, "r", encoding="utf-8") as f:
            script_text = f.read().strip()
        for para in script_text.split("\n\n"):
            for sent in para.replace("...", "…").split(". "):
                s = sent.strip()
                if s.startswith(("I am going to ", "I am going to\n", "I will ", "We will ", "We'll ", "In this video ")):
                    summary = s.rstrip(".")
                    if summary and not summary.endswith("."):
                        summary += "."
                    break
            if summary:
                break

    comment_prompt = config.get("cta_comment_prompt", "").strip()

    lines = []

    # ── Above the fold: hook + watch-next tease, first two lines ──────────────
    if hook:
        lines.append(hook)
    if watch_next_title:
        tease = f"Watch next: {watch_next_title}"
        if watch_next_why:
            tease += f" — {watch_next_why}."
        lines.append(tease)
    if lines:
        lines.append("")

    # ── Summary block (scannable "what you'll learn" line) ────────────────────
    if summary:
        lines.append(summary)
        lines.append("")

    # ── Chapters (listicle only) ───────────────────────────────────────────────
    for t, label in build_chapters(manifest):
        lines.append(f"{format_chapter_timestamp(t)} {label}")
    if lines and lines[-1] != "":
        lines.append("")

    # ── Comment CTA (per-video flat key, same source as the pinned comment) ────
    # The prompt is a complete question ("Which number is on your windowsill?"),
    # so it stands alone here — no "Drop yours below." suffix (that phrase works
    # after the ranked list in the pinned comment, but reads clunky after a
    # self-contained ask).
    if comment_prompt:
        lines.append(comment_prompt)
        lines.append("")

    # ── Links ───────────────────────────────────────────────────────────────────
    if watch_next_id:
        lines.append(f"Watch next: https://youtu.be/{watch_next_id}")
    lines.append(f"More from {channel}: https://youtube.com/{channel}")
    lines.append("")

    # ── Subscribe (DNA cta block, not a per-video key — same line every video) ──
    subscribe_line = config.get("cta", {}).get("subscribe_line", "").strip()
    if subscribe_line:
        lines.append(subscribe_line)
        lines.append("")

    # ── Tags — succulent-relevant, never #shorts ───────────────────────────────
    tags = [t for t in config.get("youtube_tags", ["succulents", "plantcare"])
            if t.strip().lower() != "shorts"]
    if tags:
        lines.append(" ".join(f"#{t.replace(' ', '')}" for t in tags))

    # ── Optional music credit — config-driven, not assumed from Shorts' BGM license ──
    music_credit = config.get("music_credit", "").strip()
    if music_credit:
        lines.append("")
        lines.append(music_credit)

    return "\n".join(lines).strip()


def build_pinned_comment(project_dir: str, manifest: dict, config: dict) -> str:
    """
    cta_plan.md "PER-SURFACE SPECIFICS — Pinned comment". For a listicle
    (cta.pinned_comment_mode == "ranked_index"), the full ranked list with timestamps —
    entirely mechanical from items.json + the manifest's video_start, costs nothing per
    video once built, and viewers use it as an index (drives "you forgot X" replies).
    Falls back to the DNA's generic youtube_pinned_comment prompt text for narrative
    projects (no items.json, or cta.pinned_comment_mode != "ranked_index").
    """
    cta = config.get("cta", {})
    items_path = os.path.join(project_dir, "items.json")

    if cta.get("pinned_comment_mode") == "ranked_index" and os.path.exists(items_path):
        item_chapters = build_chapters(manifest, include_intro=False)
        if item_chapters:
            lines = ["The full ranked list, with timestamps:", ""]
            for t, label in item_chapters:
                lines.append(f"{format_chapter_timestamp(t)} {label}")
            lines.append("")
            # Per-video flat key, same prompt as the in-script ask for consistency
            # (cta_plan.md's comment_prompt_pattern is the DNA-level pattern this text
            # must follow; the actual line is per-video, never hardcoded here).
            comment_prompt = config.get("cta_comment_prompt", "").strip()
            if comment_prompt:
                lines.append(f"{comment_prompt} Drop yours below.")
            return "\n".join(lines).strip()

    return config.get("youtube_pinned_comment", "").strip()


def upload_to_youtube(project_dir: str, title: str = None,
                      description: str = None, force_video: str = None,
                      skip_comment: bool = False):
    scripts_dir   = os.path.dirname(os.path.abspath(__file__))
    # project_dir passed through so config_override.json's flat cta_* keys (watch-next
    # target, comment prompt -- per-video, never a nested "cta" object, see
    # config_loader.py's own guard) actually get merged in. Missing this meant every
    # per-video CTA key silently resolved to "" regardless of what was set.
    config        = load_config(scripts_dir, project_dir)
    manifest_path = os.path.join(project_dir, "manifest.json")

    if not os.path.exists(manifest_path):
        print(f"❌ manifest.json not found: {manifest_path}")
        sys.exit(1)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    episode    = manifest["episode"]
    output_dir = os.path.join(project_dir, "output")

    # ── locate video ──────────────────────────────────────────────────────────
    if force_video:
        video_path = force_video
    else:
        captioned = os.path.join(output_dir, f"{episode}_captioned.mp4")
        final     = os.path.join(output_dir, f"{episode}_final.mp4")
        if os.path.exists(captioned):
            video_path = captioned
        elif os.path.exists(final):
            print(f"   ⚠️  Captioned video not found, using final (no burned captions)")
            video_path = final
        else:
            print(f"❌ No video found in {output_dir}")
            print("   Run stitch_video_complete.py first.")
            sys.exit(1)

    # ── locate SRT ────────────────────────────────────────────────────────────
    srt_path = os.path.join(output_dir, f"{episode}_captions.srt")
    has_srt  = os.path.exists(srt_path)

    # ── build metadata ────────────────────────────────────────────────────────
    if not title:
        title = manifest.get("title", episode)

    desc = build_description(project_dir, manifest, config, description)

    tags        = config.get("youtube_tags", ["succulents", "shorts"])
    category_id = config.get("youtube_category_id", "28")
    language    = config.get("youtube_default_language", "en")
    kids        = config.get("youtube_made_for_kids", False)

    # ── authenticate ──────────────────────────────────────────────────────────
    print(f"\n🔐 Authenticating with YouTube...")
    youtube = get_authenticated_service(scripts_dir, credentials_dir=config.get("credentials_dir"))

    # ── upload ────────────────────────────────────────────────────────────────
    print(f"\n📤 Uploading to YouTube...")
    video_id = upload_video(
        youtube, video_path, title, desc,
        tags, category_id, kids, language,
    )

    if has_srt:
        print(f"\n📝 Uploading subtitles...")
        upload_subtitle(youtube, video_id, srt_path, language)
    else:
        print(f"   ℹ️  No SRT found at {srt_path} — skipping subtitle upload.")

    # ── optional thumbnail ────────────────────────────────────────────────────
    thumbnail_path = None
    for ext in ("thumbnail.png", "thumbnail.jpg", "thumbnail.jpeg"):
        candidate = os.path.join(project_dir, ext)
        if os.path.exists(candidate):
            thumbnail_path = candidate
            break

    if thumbnail_path:
        answer = input(f"\n🖼️  Thumbnail found ({os.path.basename(thumbnail_path)}). Upload it? [y/n]: ").strip().lower()
        if answer == "y":
            upload_thumbnail(youtube, video_id, thumbnail_path)
        else:
            print("   Thumbnail skipped — set it manually in YouTube Studio.")
    else:
        print(f"\n   ℹ️  No thumbnail found. Drop thumbnail.png into the project folder to enable upload.")

    # ── pinned comment ────────────────────────────────────────────────────────
    pinned_comment_text = build_pinned_comment(project_dir, manifest, config)
    if pinned_comment_text and not skip_comment:
        print(f"\n💬 Posting pinned comment...")
        print(f"   Text: {pinned_comment_text}")
        answer = input("   Post this comment? [y/n/edit]: ").strip().lower()
        if answer == "edit":
            pinned_comment_text = input("   Enter comment text: ").strip()
            answer = "y"
        if answer == "y":
            comment_id = post_pinned_comment(youtube, video_id, pinned_comment_text)
            if comment_id:
                manifest["youtube_pinned_comment_id"] = comment_id
        else:
            print("   Comment skipped.")
    elif skip_comment:
        print(f"\n   ℹ️  Pinned comment skipped (--skip-comment).")

    # ── write video ID to manifest ────────────────────────────────────────────
    manifest["youtube_video_id"]  = video_id
    manifest["youtube_video_url"] = f"https://youtu.be/{video_id}"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n{'─'*55}")
    print(f"✅ Upload complete!")
    print(f"   URL    : https://youtu.be/{video_id}")
    print(f"   Studio : https://studio.youtube.com/video/{video_id}/edit")
    print(f"   Status : private draft — add thumbnail, then publish")
    print(f"{'─'*55}\n")
    return video_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload an AeoniumGlow long-form video to YouTube")
    parser.add_argument("--project",      required=True, help="Project folder (e.g. short-04)")
    parser.add_argument("--title",        default=None,  help="Override video title")
    parser.add_argument("--description",  default=None,  help="Override video description")
    parser.add_argument("--video",        default=None,  help="Override video file path")
    parser.add_argument("--skip-comment", action="store_true",
                        help="Skip posting the pinned comment from pipeline_config.json")
    args = parser.parse_args()

    scripts_dir  = os.path.dirname(os.path.abspath(__file__))
    project_dir  = (
        args.project if os.path.isabs(args.project)
        else os.path.join(scripts_dir, args.project)
    )

    if not os.path.isdir(project_dir):
        print(f"❌ Project folder not found: {project_dir}")
        sys.exit(1)

    upload_to_youtube(
        project_dir,
        title=args.title,
        description=args.description,
        force_video=args.video,
        skip_comment=args.skip_comment,
    )
