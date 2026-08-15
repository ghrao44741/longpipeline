"""
post_update.py — AeoniumGlow Long-Form Pipeline
Sync a project's manifest.json against the video's LIVE YouTube state (privacy,
title, publish date), then post the pinned comment if the video is public.

Ported from shorts_pipeline2/post_update.py (2026-08-14) with three long-form
specific changes:

1. Project resolution: projects live under longform_pipeline/ and are passed as
   `--project` (relative to this script's dir, or absolute).
2. Comment text: built from the long-form pipeline itself via
   upload_youtube.build_pinned_comment() (the ranked-list-with-timestamps
   comment for listicles, per-video cta_comment_prompt, etc.) instead of the
   shorts pipeline_config.json's youtube_pinned_comment. --text/--text-file
   still override.
3. Auth: reuses upload_youtube.get_authenticated_service() with the same
   credentials_dir resolution (points at ..\shorts_pipeline2 by default) so
   the long-form and shorts pipelines share one YouTube token.

Why this exists (same reasoning as the shorts version): manifest.json is
written at upload time and never updated automatically. A video's privacy
status or title can change in Studio afterwards with nothing in tracked state
knowing. This script re-verifies against the API every run.

Comments can only be posted on a public (or unlisted) video — YouTube's API
rejects commentThreads.insert on private videos with a 403 "insufficient
permissions" error that reads like a real permissions problem but isn't one.
This script checks privacy status BEFORE attempting to post (confirmed on
Etiolation_S1's private draft, 2026-08-14: pinned comment must be posted
post-publish, not at upload).

Usage:
    python post_update.py --project Etiolation_S1
    python post_update.py --project Etiolation_S1 --no-comment   # sync status only
    python post_update.py --project Etiolation_S1 --text "Custom comment"
    python post_update.py --project Etiolation_S1 --force-comment  # re-post
    python post_update.py --project Etiolation_S1 --thumbnail    # upload thumbnail.png to the EXISTING video (no MP4 re-upload)

Requires:
    pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from googleapiclient.errors import HttpError
except ImportError:
    print("❌ Google API libraries not installed.")
    print("   Run: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2")
    sys.exit(1)

# Long-form pipeline's own auth + comment builders — same OAuth token (shared
# credentials_dir), same manifest schema, same per-video comment logic.
from config_loader import load_config  # noqa: E402
from upload_youtube import get_authenticated_service, build_pinned_comment  # noqa: E402

# Privacy states that accept comments. "private" does not — see module docstring.
COMMENTABLE_STATES = {"public", "unlisted"}


def fetch_live_status(youtube, video_id: str) -> dict:
    """
    Query the video's current status directly from the API.
    Returns {} if the video doesn't exist / isn't visible to this channel's
    token (e.g. it was deleted).
    """
    resp = youtube.videos().list(part="status,snippet", id=video_id).execute()
    items = resp.get("items", [])
    if not items:
        return {}
    item = items[0]
    return {
        "privacy_status": item["status"]["privacyStatus"],
        "upload_status":  item["status"].get("uploadStatus"),
        "live_title":     item["snippet"]["title"],
        "published_at":   item["snippet"].get("publishedAt"),
    }


def sync_project(youtube, project_dir: str, comment_text: str, post: bool,
                 force_comment: bool, scripts_dir: str, thumb_path: str | None = None) -> None:
    label = os.path.basename(project_dir)
    manifest_path = os.path.join(project_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        print(f"\n⚠️  {label}: manifest.json not found — skipping")
        return

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    video_id = manifest.get("youtube_video_id", "").strip()
    if not video_id:
        print(f"\n⚠️  {label}: no youtube_video_id in manifest — not uploaded yet, skipping")
        return

    print(f"\n{'─'*55}")
    print(f"📹 {label}  ({video_id})")

    live = fetch_live_status(youtube, video_id)
    if not live:
        print(f"   ❌ Video not found on the channel — the recorded ID may be stale "
              f"(deleted, or never matched a real upload). Re-upload if needed.")
        manifest["youtube_privacy_status"] = "not_found"
        manifest["youtube_status_checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        return

    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest["youtube_privacy_status"]    = live["privacy_status"]
    manifest["youtube_live_title"]        = live["live_title"]
    manifest["youtube_published_at"]      = live["published_at"]
    manifest["youtube_status_checked_at"] = checked_at

    print(f"   Privacy : {live['privacy_status']}")
    print(f"   Title   : {live['live_title']}")
    if live["published_at"]:
        when_label = "Live since" if live["privacy_status"] == "public" else "Uploaded"
        print(f"   {when_label}: {live['published_at']}")

    # ── optional thumbnail upload (existing video, no re-upload of the MP4) ──
    if thumb_path:
        from upload_youtube import upload_thumbnail
        try:
            upload_thumbnail(youtube, video_id, thumb_path)
        except HttpError as e:
            print(f"   ⚠️  Thumbnail upload failed: {e}")
            print("      Set it manually in YouTube Studio.")

    already_commented = bool(manifest.get("youtube_pinned_comment_id"))

    if not post:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        print(f"   💾 Status synced to manifest.json (--no-comment, skipped posting)")
        return

    if live["privacy_status"] not in COMMENTABLE_STATES:
        print(f"   ⚠️  Video is not public (currently: {live['privacy_status']}) — "
              f"comments can't be posted until it's published. Skipping comment.")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        return

    if already_commented and not force_comment:
        print(f"   ✅ Already commented (ID: {manifest['youtube_pinned_comment_id']}) — "
              f"use --force-comment to post again.")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        return

    comment_id = _post_comment_api(youtube, video_id, comment_text)
    if comment_id:
        manifest["youtube_pinned_comment_id"]        = comment_id
        manifest["youtube_pinned_comment_posted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        print(f"   ✅ Comment posted (ID: {comment_id})")
        print(f"   📌 To pin: Studio → Comments → ⋮ next to your comment → Pin to top")

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def _post_comment_api(youtube, video_id: str, text: str) -> str | None:
    """Post a top-level comment. Returns the comment thread ID, or None on failure."""
    try:
        response = youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": text
                        }
                    }
                }
            }
        ).execute()
        return response["id"]
    except HttpError as e:
        print(f"   ❌ Failed to post comment: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Sync manifest.json against live YouTube status, then post the "
                    "pinned comment if the video is public."
    )
    parser.add_argument("--project", required=True, metavar="FOLDER",
                        help="Project folder (relative to this script, or absolute)")
    text_group = parser.add_mutually_exclusive_group()
    text_group.add_argument("--text", metavar="TEXT", help="Comment text (overrides pipeline-built pinned comment)")
    text_group.add_argument("--text-file", metavar="PATH", help="Read comment text from a plain .txt file")
    parser.add_argument("--no-comment", action="store_true",
                        help="Only sync status fields into manifest.json — never attempt to post a comment")
    parser.add_argument("--force-comment", action="store_true",
                        help="Post the comment even if manifest.json already has a youtube_pinned_comment_id")
    parser.add_argument("--thumbnail", nargs="?", const="auto", metavar="PATH",
                        help="Upload thumbnail.png (or PATH) from the project folder to the EXISTING video "
                             "-- for a live/draft video whose thumbnail changed after upload. "
                             "No re-upload of the MP4; no duplicate video is created.")
    args = parser.parse_args()

    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = (args.project if os.path.isabs(args.project)
                   else os.path.normpath(os.path.join(scripts_dir, args.project)))
    if not os.path.isdir(project_dir):
        print(f"❌ Project folder not found: {project_dir}")
        sys.exit(1)

    if args.thumbnail:
        if args.thumbnail == "auto":
            thumb_path = None
            for ext in ("thumbnail.png", "thumbnail.jpg", "thumbnail.jpeg"):
                candidate = os.path.join(project_dir, ext)
                if os.path.exists(candidate):
                    thumb_path = candidate
                    break
            if not thumb_path:
                print(f"❌ No thumbnail.png/.jpg/.jpeg in project folder: {project_dir}")
                sys.exit(1)
        else:
            thumb_path = args.thumbnail if os.path.isabs(args.thumbnail) else os.path.join(scripts_dir, args.thumbnail)
        if not os.path.exists(thumb_path):
            print(f"❌ Thumbnail file not found: {thumb_path}")
            sys.exit(1)
        if not os.path.isdir(project_dir):
            print(f"❌ Project folder not found: {project_dir}")
            sys.exit(1)
    else:
        thumb_path = None

    if args.text:
        comment_text = args.text.strip()
    elif args.text_file:
        tf = args.text_file if os.path.isabs(args.text_file) else os.path.join(scripts_dir, args.text_file)
        if not os.path.exists(tf):
            print(f"❌ Text file not found: {tf}")
            sys.exit(1)
        with open(tf, "r", encoding="utf-8") as f:
            comment_text = f.read().strip()
    else:
        # Long-form pinned comment, built from manifest + items.json + config —
        # the same text upload_youtube.py would have pinned had the video been public.
        config = load_config(scripts_dir, project_dir)
        with open(os.path.join(project_dir, "manifest.json"), "r", encoding="utf-8") as f:
            manifest = json.load(f)
        comment_text = build_pinned_comment(project_dir, manifest, config).strip()

    if not args.no_comment and not comment_text:
        print("❌ No comment text provided and the pipeline-built pinned comment is empty.")
        print("   Use --text, --text-file, or --no-comment to skip posting entirely.")
        sys.exit(1)

    print("🔐 Authenticating with YouTube...")
    config = load_config(scripts_dir, project_dir)
    youtube = get_authenticated_service(scripts_dir, credentials_dir=config.get("credentials_dir"))

    try:
        sync_project(youtube, project_dir, comment_text, post=not args.no_comment,
                     force_comment=args.force_comment, scripts_dir=scripts_dir,
                     thumb_path=thumb_path)
    except HttpError as e:
        print(f"\n⚠️  {os.path.basename(project_dir)}: API error — {e}")

    print(f"\n{'─'*55}")
    print("Done.")


if __name__ == "__main__":
    main()
