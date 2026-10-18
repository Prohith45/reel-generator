#!/usr/bin/env python3
"""
Instagram Reels Uploader
========================
Uploads generated reel videos to Instagram Reels using either:
1. Instagrapi (Private Mobile API) - Supports direct local MP4 uploads & caches session.json
2. Meta Graph API - Supported when a publicly accessible video URL is provided

Features:
- Caches authenticated session in config/session.json (avoids login bans).
- Gracefully handles missing credentials or auth failures with:
  [WARNING] Instagram authentication failed. Skipping Instagram upload.
- Wrapped in isolated try-except so failures NEVER block YouTube or other steps.

Usage:
    python instagram_uploader.py --video "outputs/videos/sample.mp4" --topic "what is capacitor"
    python instagram_uploader.py --video "outputs/videos/sample.mp4" --dry-run
"""

import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

# Configure project root
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

logger = logging.getLogger("instagram_uploader")

SESSION_FILE = PROJECT_ROOT / "config" / "session.json"


def format_instagram_caption(topic: str, custom_caption: Optional[str] = None) -> str:
    """Format an engaging caption for Instagram Reels with hashtags."""
    if custom_caption:
        caption = custom_caption
    else:
        clean_topic = topic.strip()
        if not clean_topic[0].isupper():
            clean_topic = clean_topic[0].upper() + clean_topic[1:]
        caption = (
            f"⚡ {clean_topic} Explained!\n\n"
            f"Did you know how {topic.lower()} actually works? "
            f"Here is a quick breakdown in under 60 seconds. "
            f"Save this reel for later! 💾\n\n"
            f"Follow @your_handle for daily tech & engineering content! 🚀\n\n"
            f"#reels #tech #engineering #electronics #education #learn #stem #science #shorts"
        )
    if len(caption) > 2200:
        caption = caption[:2196] + "..."
    return caption


def upload_via_instagrapi(video_path: Path, caption: str, dry_run: bool = False) -> Dict[str, Any]:
    """Upload directly using Instagrapi with persistent session caching."""
    username = os.getenv("INSTAGRAM_USERNAME")
    password = os.getenv("INSTAGRAM_PASSWORD")

    if not username or not password:
        warning = (
            "[WARNING] Instagram credentials missing. "
            "Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in .env. Skipping Instagram upload."
        )
        logger.warning(warning)
        return {"success": False, "media_id": "", "url": "", "error": warning, "skipped": True}

    if dry_run:
        logger.info(f"[DRY-RUN] Would upload to Instagram via Instagrapi: {video_path}")
        return {"success": True, "media_id": "DRY_RUN_IG_ID", "url": "https://instagram.com/reel/DRY_RUN", "error": ""}

    try:
        from instagrapi import Client
    except ImportError:
        warning = "[WARNING] instagrapi is not installed. Run: pip install instagrapi. Skipping Instagram upload."
        logger.warning(warning)
        return {"success": False, "media_id": "", "url": "", "error": warning, "skipped": True}

    client = Client()

    # ── Authenticate with session cache ──
    try:
        logged_in = False
        if SESSION_FILE.exists():
            try:
                logger.info(f"Loading cached Instagram session from {SESSION_FILE}...")
                client.load_settings(str(SESSION_FILE))
                # Validate session viability without sending a new password login
                client.get_timeline_feed()
                logger.info("Instagram session restored successfully (zero login prompt).")
                logged_in = True
            except Exception as e:
                logger.warning(f"Cached session invalid or expired ({e}). Attempting fresh login...")
                logged_in = False

        if not logged_in:
            logger.info("Logging into Instagram (fresh session)...")
            # Auto-generate 2FA TOTP if seed is configured in .env
            totp_code = None
            totp_seed = os.getenv("INSTAGRAM_2FA_SEED") or os.getenv("INSTAGRAM_TOTP_KEY")
            if totp_seed:
                try:
                    import pyotp
                    totp = pyotp.TOTP(totp_seed.replace(" ", ""))
                    totp_code = totp.now()
                    logger.info("Generated 2FA TOTP verification code automatically.")
                except Exception as e:
                    logger.warning(f"Could not generate TOTP code: {e}")

            if totp_code:
                client.login(username, password, verification_code=totp_code)
            else:
                client.login(username, password)

            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            client.dump_settings(str(SESSION_FILE))
            logger.info("Instagram login successful. Session saved.")

    except Exception as auth_err:
        warning = f"[WARNING] Instagram authentication failed: {auth_err}. Skipping Instagram upload."
        logger.warning(warning)
        return {"success": False, "media_id": "", "url": "", "error": warning, "skipped": True}

    # ── Upload reel ──
    try:
        logger.info(f"Uploading Reel to Instagram: {video_path.name}")
        media = client.clip_upload(
            path=video_path,
            caption=caption,
        )

        if media and hasattr(media, "code"):
            url = f"https://www.instagram.com/reel/{media.code}/"
            media_id = str(getattr(media, "pk", ""))
            logger.info(f"[SUCCESS] Instagram Reel Published: {url}")
            return {"success": True, "media_id": media_id, "url": url, "error": ""}
        else:
            error_msg = f"Instagram upload returned unexpected response: {media}"
            logger.error(error_msg)
            return {"success": False, "media_id": "", "url": "", "error": error_msg}

    except Exception as upload_err:
        error_msg = f"Instagram clip_upload failed: {upload_err}"
        logger.error(error_msg)
        return {"success": False, "media_id": "", "url": "", "error": error_msg}


def upload_via_graph_api(video_path: Path, caption: str, dry_run: bool = False) -> Dict[str, Any]:
    """Upload via Meta Graph API (Requires a public video URL)."""
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    account_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID") or os.getenv("INSTAGRAM_ACCOUNT_ID")

    if not access_token or not account_id:
        warning = (
            "[WARNING] Meta Graph API credentials not configured. "
            "Set INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID in .env. Skipping."
        )
        logger.warning(warning)
        return {"success": False, "media_id": "", "url": "", "error": warning, "skipped": True}

    warning = (
        "[WARNING] Instagram Graph API requires a publicly hosted CDN video URL. "
        "Local file path cannot be uploaded directly via Graph API. "
        "To upload local files directly, configure INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in .env for Instagrapi."
    )
    logger.warning(warning)
    return {"success": False, "media_id": "", "url": "", "error": warning, "skipped": True}


def upload_to_instagram(
    video_path: str,
    topic: str = "",
    caption: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Upload a video file to Instagram Reels.
    Wraps entire execution in an isolated try-except so errors NEVER crash calling processes.
    """
    resolved_video = Path(video_path).resolve()
    if not resolved_video.exists():
        error = f"Video file not found: {resolved_video}"
        logger.error(error)
        return {"success": False, "media_id": "", "url": "", "error": error}

    formatted_caption = format_instagram_caption(topic or resolved_video.stem, caption)

    try:
        # Determine strategy: Instagrapi if username is set, else Graph API
        if os.getenv("INSTAGRAM_USERNAME"):
            return upload_via_instagrapi(resolved_video, formatted_caption, dry_run=dry_run)
        elif os.getenv("INSTAGRAM_ACCESS_TOKEN"):
            return upload_via_graph_api(resolved_video, formatted_caption, dry_run=dry_run)
        else:
            warning = (
                "[WARNING] No Instagram credentials found in environment (.env). "
                "Set INSTAGRAM_USERNAME + INSTAGRAM_PASSWORD (or INSTAGRAM_ACCESS_TOKEN + INSTAGRAM_BUSINESS_ACCOUNT_ID). "
                "Skipping Instagram upload."
            )
            logger.warning(warning)
            return {"success": False, "media_id": "", "url": "", "error": warning, "skipped": True}

    except Exception as e:
        warning = f"[WARNING] Unexpected Instagram upload exception: {e}. Skipping Instagram upload."
        logger.warning(warning)
        return {"success": False, "media_id": "", "url": "", "error": str(e), "skipped": True}


def main():
    parser = argparse.ArgumentParser(description="Instagram Reels Uploader")
    parser.add_argument("--video", required=True, help="Path to the generated .mp4 file")
    parser.add_argument("--topic", default="", help="Topic of the reel")
    parser.add_argument("--caption", default=None, help="Custom caption")
    parser.add_argument("--dry-run", action="store_true", help="Simulate upload without publishing")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    result = upload_to_instagram(
        video_path=args.video,
        topic=args.topic,
        caption=args.caption,
        dry_run=args.dry_run,
    )

    if result["success"]:
        print(f"\n[SUCCESS] Instagram Reel Published!")
        print(f"URL: {result['url']}")
        sys.exit(0)
    elif result.get("skipped"):
        # Skipped due to auth/config warning - non-fatal
        print(f"\n{result['error']}")
        sys.exit(0)
    else:
        print(f"\n[ERROR] Instagram Upload Failed: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
