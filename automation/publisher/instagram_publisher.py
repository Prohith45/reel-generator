"""
Instagram Publisher
Uploads reels to Instagram using Instagrapi (private mobile API).
Falls back gracefully if authentication fails.
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
SESSION_FILE = PROJECT_ROOT / "config" / "instagram_session.json"


@dataclass
class InstagramUploadResult:
    """Result of Instagram upload."""
    success: bool
    media_id: str = ""
    url: str = ""
    error: str = ""


class InstagramPublisher:
    """Publishes videos to Instagram Reels via Instagrapi (private mobile API)."""

    def __init__(self, config: Dict[str, Any], credentials_config: Dict[str, Any]):
        self.config = config
        self.ig_config = config.get("instagram", {})
        self.credentials_config = credentials_config

        self.username = credentials_config.get("username", "")
        self.password = credentials_config.get("password", "")
        self.access_token = credentials_config.get("access_token", "")
        self.instagram_business_account_id = credentials_config.get(
            "instagram_business_account_id", ""
        )

        self.share_to_feed = self.ig_config.get("share_to_feed", True)
        self.max_retries = self.ig_config.get("max_retries", 3)
        self.retry_delay = self.ig_config.get("retry_delay_seconds", 60)

        self._client = None
        self._mode = "none"  # "instagrapi", "graph_api", or "none"

        # Determine which mode to use
        self._detect_mode()

    def _detect_mode(self):
        """Detect which Instagram upload method is available."""
        # Priority 1: Instagrapi (private mobile API — no public URL needed)
        if self.username and self.password:
            try:
                from instagrapi import Client as InstaClient
                self._mode = "instagrapi"
                logger.info("Instagram mode: Instagrapi (private mobile API)")
                return
            except ImportError:
                logger.warning(
                    "instagrapi not installed. Run: pip install instagrapi"
                )

        # Priority 2: Meta Graph API (requires public video URL / CDN hosting)
        if self.access_token and self.instagram_business_account_id:
            self._mode = "graph_api"
            logger.info("Instagram mode: Meta Graph API")
            return

        logger.warning(
            "Instagram credentials not configured. "
            "Set INSTAGRAM_USERNAME + INSTAGRAM_PASSWORD in .env for Instagrapi, "
            "or INSTAGRAM_ACCESS_TOKEN + INSTAGRAM_BUSINESS_ACCOUNT_ID for Graph API."
        )

    # ── Instagrapi (Private Mobile API) ──────────────────────────────────────

    def _get_instagrapi_client(self):
        """Get or create an authenticated Instagrapi client."""
        if self._client is not None:
            return self._client

        from instagrapi import Client as InstaClient

        client = InstaClient()

        # Try to resume session
        if SESSION_FILE.exists():
            try:
                client.load_settings(str(SESSION_FILE))
                client.login(self.username, self.password)
                client.get_timeline_feed()  # Validate session is alive
                logger.info("Instagram session resumed from cache")
                self._client = client
                return self._client
            except Exception as e:
                logger.warning(f"Cached session invalid, re-authenticating: {e}")

        # Fresh login
        client.login(self.username, self.password)
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        client.dump_settings(str(SESSION_FILE))
        logger.info("Instagram fresh login successful, session saved")
        self._client = client
        return self._client

    def _upload_via_instagrapi(self, video_path: str, topic_config) -> InstagramUploadResult:
        """Upload via Instagrapi private mobile API."""
        try:
            client = self._get_instagrapi_client()
            caption = self._build_caption(topic_config)

            media = client.clip_upload(
                path=Path(video_path),
                caption=caption,
            )

            if media and media.pk:
                media_id = str(media.pk)
                url = f"https://www.instagram.com/reel/{media.code}/"
                logger.info(f"Instagram upload successful: {url}")
                return InstagramUploadResult(
                    success=True, media_id=media_id, url=url
                )
            else:
                return InstagramUploadResult(
                    success=False, error="No media ID returned from Instagrapi"
                )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Instagrapi upload failed: {error_msg}")
            return InstagramUploadResult(success=False, error=error_msg)

    # ── Meta Graph API ───────────────────────────────────────────────────────

    def _upload_via_graph_api(self, video_path: str, topic_config) -> InstagramUploadResult:
        """
        Upload via Meta Graph API.
        NOTE: This requires a publicly accessible video URL.
        If you don't have a CDN, use Instagrapi mode instead.
        """
        import requests

        GRAPH_API_VERSION = "v20.0"
        BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

        # Graph API requires a publicly accessible URL, not a local file.
        # Warn the user and fail gracefully.
        logger.error(
            "Instagram Graph API requires a publicly hosted video URL. "
            "Local file upload is not supported by the Graph API. "
            "Switch to Instagrapi mode (set INSTAGRAM_USERNAME + INSTAGRAM_PASSWORD in .env) "
            "for direct local file uploads."
        )
        return InstagramUploadResult(
            success=False,
            error="Graph API requires a public video URL. Use Instagrapi mode for local uploads."
        )

    # ── Public Upload Interface ──────────────────────────────────────────────

    def upload(self, video_path: str, topic_config, dry_run: bool = False) -> InstagramUploadResult:
        """Upload a video to Instagram Reels."""
        if dry_run:
            logger.info(f"[DRY RUN] Would upload to Instagram: {video_path}")
            return InstagramUploadResult(
                success=True,
                media_id="DRY_RUN_ID",
                url="https://instagram.com/reel/DRY_RUN_ID",
            )

        if not os.path.exists(video_path):
            return InstagramUploadResult(
                success=False, error=f"Video file not found: {video_path}"
            )

        # Check file size (Instagram limit: 100MB for reels)
        file_size = os.path.getsize(video_path)
        if file_size > 100 * 1024 * 1024:
            return InstagramUploadResult(
                success=False,
                error=f"Video too large: {file_size / (1024*1024):.1f}MB (max 100MB)",
            )

        # Upload with retries
        for attempt in range(1, self.max_retries + 1):
            logger.info(
                f"Instagram upload attempt {attempt}/{self.max_retries}: {video_path}"
            )

            if self._mode == "instagrapi":
                result = self._upload_via_instagrapi(video_path, topic_config)
            elif self._mode == "graph_api":
                result = self._upload_via_graph_api(video_path, topic_config)
            else:
                return InstagramUploadResult(
                    success=False,
                    error="No Instagram upload method configured. "
                    "Set credentials in .env (see .env.example).",
                )

            if result.success:
                return result

            if attempt < self.max_retries:
                logger.info(f"Retrying in {self.retry_delay}s...")
                time.sleep(self.retry_delay)

        return result  # Return last failed result

    # ── Caption Builder ──────────────────────────────────────────────────────

    def _build_caption(self, topic_config) -> str:
        """Build Instagram caption."""
        lines = []

        if topic_config.hook:
            lines.append(topic_config.hook)
            lines.append("")

        if topic_config.description:
            lines.append(topic_config.description)
            lines.append("")

        # Hashtags
        if topic_config.hashtags:
            lines.append(" ".join(topic_config.hashtags))
            lines.append("")

        # Standard footer
        lines.extend(
            [
                "Follow for more tech content! \U0001f680",
                "",
                "#reels #tech #education #engineering #shorts",
            ]
        )

        caption = "\n".join(lines)
        # Instagram caption limit: 2200 chars
        if len(caption) > 2200:
            caption = caption[:2197] + "..."

        return caption

    # ── Token Refresh ────────────────────────────────────────────────────────

    def refresh_access_token(self) -> bool:
        """Refresh Meta Graph API long-lived access token."""
        import requests

        app_id = self.credentials_config.get("app_id")
        app_secret = self.credentials_config.get("app_secret")

        if not app_id or not app_secret:
            logger.warning("App credentials not configured, cannot refresh token")
            return False

        url = "https://graph.facebook.com/v20.0/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": self.access_token,
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                new_token = data.get("access_token")
                if new_token:
                    self.access_token = new_token
                    logger.info("Access token refreshed successfully")
                    return True
            else:
                logger.error(
                    f"Token refresh failed: {response.status_code} - {response.text}"
                )
        except Exception as e:
            logger.error(f"Token refresh error: {e}")

        return False


def create_instagram_publisher(
    config: Dict[str, Any], credentials_config: Dict[str, Any]
) -> InstagramPublisher:
    """Factory function to create InstagramPublisher."""
    return InstagramPublisher(config, credentials_config)