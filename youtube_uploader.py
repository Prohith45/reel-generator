#!/usr/bin/env python3
"""
YouTube Shorts Uploader
=======================
Uploads generated reel videos to YouTube Shorts via YouTube Data API v3 with OAuth2.

Features:
- Dynamically resolves client_secret.json relative to project root.
- Caches persistent tokens in config/token.json (or config/token.pickle).
- Auto-refreshes expired credentials via creds.refresh(Request()).
- Falls back to browser InstalledAppFlow if tokens are missing.
- Formats metadata (title < 100 chars, description + hashtags, category 28, privacy).

Usage:
    python youtube_uploader.py --video "outputs/videos/sample.mp4" --topic "what is capacitor"
    python youtube_uploader.py --video "outputs/videos/sample.mp4" --topic "what is capacitor" --privacy unlisted
    python youtube_uploader.py --video "outputs/videos/sample.mp4" --dry-run
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

logger = logging.getLogger("youtube_uploader")

# API Configuration
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

# Persistent token & secret locations
TOKEN_JSON_PATH = PROJECT_ROOT / "config" / "token.json"
TOKEN_PICKLE_PATH = PROJECT_ROOT / "config" / "token.pickle"
CLIENT_SECRET_CANDIDATES = [
    PROJECT_ROOT / "client_secret.json",
    PROJECT_ROOT / "client_secrets.json",
    PROJECT_ROOT / "credentials.json",
    PROJECT_ROOT / "config" / "client_secret.json",
    PROJECT_ROOT / "config" / "client_secrets.json",
]


def resolve_client_secret_path() -> Optional[Path]:
    """Dynamically resolve client_secret.json relative to project root."""
    for path in CLIENT_SECRET_CANDIDATES:
        if path.exists():
            return path
    return None


def get_authenticated_credentials(allow_browser_flow: bool = True):
    """
    Obtains valid Google OAuth2 credentials.
    Priority order:
    1. Cached config/token.json or config/token.pickle (refreshed if expired)
    2. Refresh token from environment (.env: YOUTUBE_REFRESH_TOKEN, YOUTUBE_CLIENT_ID, etc.)
    3. Browser-based InstalledAppFlow fallback (saves to token.json)
    """
    import google.auth.transport.requests
    from google.oauth2.credentials import Credentials

    creds: Optional[Credentials] = None
    request = google.auth.transport.requests.Request()

    # ── 1. Check cached token.json ──
    if TOKEN_JSON_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_JSON_PATH), SCOPES)
            logger.info(f"Loaded credentials from {TOKEN_JSON_PATH}")
        except Exception as e:
            logger.warning(f"Failed to load {TOKEN_JSON_PATH}: {e}")
            creds = None

    # ── 2. Check cached token.pickle (legacy support) ──
    if not creds and TOKEN_PICKLE_PATH.exists():
        try:
            import pickle
            with open(TOKEN_PICKLE_PATH, "rb") as token_file:
                creds = pickle.load(token_file)
            logger.info(f"Loaded credentials from {TOKEN_PICKLE_PATH}")
        except Exception as e:
            logger.warning(f"Failed to load {TOKEN_PICKLE_PATH}: {e}")
            creds = None

    # ── 3. Validate & Refresh if expired ──
    if creds:
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            try:
                logger.info("Cached token expired. Refreshing token via OAuth2...")
                creds.refresh(request)
                # Save refreshed credentials
                _save_credentials(creds)
                logger.info("Token refreshed and saved successfully.")
                return creds
            except Exception as e:
                logger.warning(f"Failed to refresh cached token: {e}")
                creds = None

    # ── 4. Check Environment Variables (.env) ──
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")

    # If client_id/secret missing in env, try reading from client_secret.json
    secret_path = resolve_client_secret_path()
    if secret_path and (not client_id or not client_secret):
        try:
            with open(secret_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            client_info = data.get("installed", data.get("web", {}))
            client_id = client_id or client_info.get("client_id")
            client_secret = client_secret or client_info.get("client_secret")
        except Exception as e:
            logger.warning(f"Failed to read client info from {secret_path}: {e}")

    if client_id and client_secret and refresh_token:
        try:
            logger.info("Constructing credentials from refresh_token in environment...")
            creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
                token_uri="https://oauth2.googleapis.com/token",
                scopes=SCOPES,
            )
            creds.refresh(request)
            _save_credentials(creds)
            return creds
        except Exception as e:
            logger.warning(f"Failed to initialize credentials from environment refresh token: {e}")
            creds = None

    # ── 5. Fallback: Browser InstalledAppFlow ──
    if allow_browser_flow:
        if not secret_path:
            raise FileNotFoundError(
                f"Cannot authorize YouTube: client_secret.json not found in project root ({PROJECT_ROOT}). "
                "Download your OAuth client ID credentials from Google Cloud Console."
            )
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            logger.info(f"Initiating interactive OAuth flow using: {secret_path}")
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
            creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
            _save_credentials(creds)
            return creds
        except Exception as e:
            raise RuntimeError(f"Interactive Google OAuth flow failed: {e}")

    raise RuntimeError("No valid YouTube credentials found and interactive flow is disabled.")


def _save_credentials(creds):
    """Persist credentials to config/token.json and update .env."""
    TOKEN_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(TOKEN_JSON_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        logger.info(f"Credentials saved to {TOKEN_JSON_PATH}")
    except Exception as e:
        logger.warning(f"Failed to save {TOKEN_JSON_PATH}: {e}")

    # Also sync refresh_token to .env
    if getattr(creds, "refresh_token", None):
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            try:
                import re
                env_text = env_path.read_text(encoding="utf-8")
                replacements = {
                    "YOUTUBE_CLIENT_ID": getattr(creds, "client_id", "") or "",
                    "YOUTUBE_CLIENT_SECRET": getattr(creds, "client_secret", "") or "",
                    "YOUTUBE_REFRESH_TOKEN": creds.refresh_token,
                }
                for key, val in replacements.items():
                    if not val:
                        continue
                    pattern = rf"^{key}=.*$"
                    new_line = f"{key}={val}"
                    if re.search(pattern, env_text, re.MULTILINE):
                        env_text = re.sub(pattern, new_line, env_text, flags=re.MULTILINE)
                    else:
                        env_text += f"\n{new_line}"
                env_path.write_text(env_text, encoding="utf-8")
                logger.info("YouTube OAuth credentials synced to .env")
            except Exception as e:
                logger.warning(f"Failed to sync credentials to .env: {e}")


def format_metadata(topic: str, custom_title: Optional[str] = None, custom_desc: Optional[str] = None):
    """
    Format compliant YouTube Shorts title & description.
    - Title < 100 chars
    - Description with hashtags
    """
    # Title
    if custom_title:
        title = custom_title
    else:
        clean_topic = topic.strip()
        if not clean_topic[0].isupper():
            clean_topic = clean_topic[0].upper() + clean_topic[1:]
        title = f"{clean_topic} Explained #shorts"
    
    if len(title) > 100:
        title = title[:96] + "..."

    # Description
    if custom_desc:
        desc = custom_desc
    else:
        desc = (
            f"Understand {topic} in under 60 seconds!\n\n"
            f"In this short, we break down the core concepts behind {topic}. "
            f"Clear, visual, and straight to the point.\n\n"
            f"🔔 Subscribe for daily engineering & tech shorts!\n\n"
            f"#shorts #education #tech #engineering #science #learn"
        )
    if len(desc) > 5000:
        desc = desc[:4996] + "..."

    tags = ["shorts", "tech", "education", "engineering", "science"]
    for word in topic.lower().split():
        if len(word) > 3 and word not in tags:
            tags.append(word)

    return title, desc, tags[:30]


def upload_to_youtube(
    video_path: str,
    topic: str = "",
    title: Optional[str] = None,
    description: Optional[str] = None,
    category_id: str = "28",
    privacy_status: str = "public",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Upload a video file to YouTube Shorts.
    Returns: dict(success=bool, video_id=str, url=str, error=str)
    """
    resolved_video = Path(video_path).resolve()
    if not resolved_video.exists():
        error = f"Video file not found: {resolved_video}"
        logger.error(error)
        return {"success": False, "video_id": "", "url": "", "error": error}

    file_size = resolved_video.stat().st_size
    if file_size == 0:
        error = f"Video file is 0 bytes: {resolved_video}"
        logger.error(error)
        return {"success": False, "video_id": "", "url": "", "error": error}

    formatted_title, formatted_desc, tags = format_metadata(topic or resolved_video.stem, title, description)

    if dry_run:
        logger.info(f"[DRY-RUN] Would upload to YouTube Shorts:")
        logger.info(f"  Video: {resolved_video} ({file_size / (1024*1024):.1f} MB)")
        logger.info(f"  Title: {formatted_title}")
        logger.info(f"  Category: {category_id} | Privacy: {privacy_status}")
        return {
            "success": True,
            "video_id": "DRY_RUN_ID",
            "url": "https://youtube.com/shorts/DRY_RUN_ID",
            "error": "",
        }

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    try:
        creds = get_authenticated_credentials()
        youtube = build(API_SERVICE_NAME, API_VERSION, credentials=creds, cache_discovery=False)

        body = {
            "snippet": {
                "title": formatted_title,
                "description": formatted_desc,
                "tags": tags,
                "categoryId": str(category_id),
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en",
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        logger.info(f"Initiating YouTube upload for: {resolved_video.name}")
        logger.info(f"Title: {formatted_title}")

        media = MediaFileUpload(
            str(resolved_video),
            chunksize=8 * 1024 * 1024,
            resumable=True,
            mimetype="video/mp4",
        )

        insert_request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
            notifySubscribers=True,
        )

        response = None
        while response is None:
            status, response = insert_request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                logger.info(f"Upload progress: {progress}%")

        video_id = response.get("id", "")
        if video_id:
            url = f"https://youtube.com/shorts/{video_id}"
            logger.info(f"[SUCCESS] YouTube upload complete: {url}")
            return {"success": True, "video_id": video_id, "url": url, "error": ""}
        else:
            return {"success": False, "video_id": "", "url": "", "error": f"No video ID returned: {response}"}

    except HttpError as e:
        error_msg = f"YouTube API HttpError: {e.content.decode() if hasattr(e, 'content') and e.content else str(e)}"
        logger.error(error_msg)
        return {"success": False, "video_id": "", "url": "", "error": error_msg}
    except Exception as e:
        error_msg = f"YouTube upload exception: {str(e)}"
        logger.error(error_msg)
        return {"success": False, "video_id": "", "url": "", "error": error_msg}


def main():
    parser = argparse.ArgumentParser(description="YouTube Shorts Uploader")
    parser.add_argument("--video", required=True, help="Absolute or relative path to the .mp4 video file")
    parser.add_argument("--topic", default="", help="Topic of the reel")
    parser.add_argument("--title", default=None, help="Custom video title (< 100 characters)")
    parser.add_argument("--description", default=None, help="Custom video description")
    parser.add_argument("--category", default="28", help="Category ID (28 = Science & Technology, 27 = Education)")
    parser.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"], help="Privacy status")
    parser.add_argument("--dry-run", action="store_true", help="Simulate upload without pushing to YouTube")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    result = upload_to_youtube(
        video_path=args.video,
        topic=args.topic,
        title=args.title,
        description=args.description,
        category_id=args.category,
        privacy_status=args.privacy,
        dry_run=args.dry_run,
    )

    if result["success"]:
        print(f"\n[SUCCESS] YouTube Video Published!")
        print(f"URL: {result['url']}")
        sys.exit(0)
    else:
        print(f"\n[FATAL] YouTube Upload Failed: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
