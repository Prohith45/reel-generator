"""
YouTube Publisher
Uploads reels to YouTube Shorts using YouTube Data API v3 with OAuth2.
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


@dataclass
class YouTubeUploadResult:
    """Result of YouTube upload."""
    success: bool
    video_id: str = ""
    url: str = ""
    error: str = ""


class YouTubePublisher:
    """Publishes videos to YouTube Shorts."""
    
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
    API_SERVICE_NAME = "youtube"
    API_VERSION = "v3"
    
    def __init__(self, config: Dict[str, Any], credentials_config: Dict[str, Any]):
        self.config = config
        self.yt_config = config.get("youtube", {})
        self.credentials_config = credentials_config
        
        self.client_id = credentials_config.get("client_id")
        self.client_secret = credentials_config.get("client_secret")
        self.refresh_token = credentials_config.get("refresh_token")
        
        # Fallback: read client_id/client_secret from client_secret.json if not in env/config
        if not self.client_id or not self.client_secret:
            self._load_from_client_secret_json()
        
        self.privacy_status = self.yt_config.get("privacy_status", "public")
        self.category_id = self.yt_config.get("category_id", "28")
        self.default_tags = self.yt_config.get("default_tags", [])
        self.made_for_kids = self.yt_config.get("made_for_kids", False)
        self.notify_subscribers = self.yt_config.get("notify_subscribers", False)
        
        self.max_retries = self.yt_config.get("max_retries", 3)
        self.retry_delay = self.yt_config.get("retry_delay_seconds", 60)
        
        self._service = None
    
    def _load_from_client_secret_json(self):
        """Fallback: load client_id/secret from the project-root client_secret.json."""
        secrets_file = PROJECT_ROOT / "client_secret.json"
        if not secrets_file.exists():
            return
        try:
            import json as _json
            data = _json.loads(secrets_file.read_text(encoding="utf-8"))
            installed = data.get("installed", data.get("web", {}))
            if not self.client_id:
                self.client_id = installed.get("client_id", "")
            if not self.client_secret:
                self.client_secret = installed.get("client_secret", "")
            if self.client_id:
                logger.info("YouTube credentials loaded from client_secret.json")
        except Exception as e:
            logger.warning(f"Could not read client_secret.json: {e}")
    
    def _get_credentials(self) -> Credentials:
        """Create credentials from refresh token."""
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise ValueError("Missing YouTube OAuth2 credentials (client_id, client_secret, refresh_token)")
        
        return Credentials(
            token=None,  # Will be refreshed
            refresh_token=self.refresh_token,
            client_id=self.client_id,
            client_secret=self.client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=self.SCOPES
        )
    
    def _get_service(self):
        """Get or create YouTube API service."""
        if self._service is None:
            creds = self._get_credentials()
            # Refresh the token
            request = google.auth.transport.requests.Request()
            creds.refresh(request)
            self._service = build(
                self.API_SERVICE_NAME,
                self.API_VERSION,
                credentials=creds,
                cache_discovery=False
            )
        return self._service
    
    def upload(self, video_path: str, topic_config, dry_run: bool = False) -> YouTubeUploadResult:
        """Upload a video to YouTube Shorts."""
        if dry_run:
            logger.info(f"[DRY RUN] Would upload to YouTube: {video_path}")
            return YouTubeUploadResult(
                success=True,
                video_id="DRY_RUN_ID",
                url="https://youtube.com/shorts/DRY_RUN_ID"
            )
        
        if not os.path.exists(video_path):
            return YouTubeUploadResult(success=False, error=f"Video file not found: {video_path}")
        
        # Prepare metadata
        title = self._build_title(topic_config)
        description = self._build_description(topic_config)
        tags = self._build_tags(topic_config)
        
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": self.category_id,
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en"
            },
            "status": {
                "privacyStatus": self.privacy_status,
                "madeForKids": self.made_for_kids,
                "selfDeclaredMadeForKids": self.made_for_kids
            }
        }
        
        # Add scheduling if configured
        schedule_time = self.yt_config.get("schedule_time")
        if schedule_time:
            body["status"]["publishAt"] = schedule_time
            body["status"]["privacyStatus"] = "private"  # Required for scheduling
        
        # Upload with retries
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"YouTube upload attempt {attempt}/{self.max_retries}: {video_path}")
                
                service = self._get_service()
                
                # Create media upload
                media = MediaFileUpload(
                    video_path,
                    chunksize=1024*1024*8,  # 8MB chunks
                    resumable=True,
                    mimetype="video/mp4"
                )
                
                # Execute upload
                request = service.videos().insert(
                    part=",".join(body.keys()),
                    body=body,
                    media_body=media,
                    notifySubscribers=self.notify_subscribers
                )
                
                response = None
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        logger.info(f"Upload progress: {int(status.progress() * 100)}%")
                
                video_id = response.get("id")
                if video_id:
                    url = f"https://www.youtube.com/shorts/{video_id}"
                    logger.info(f"YouTube upload successful: {url}")
                    return YouTubeUploadResult(
                        success=True,
                        video_id=video_id,
                        url=url
                    )
                else:
                    raise Exception("No video ID in response")
                    
            except HttpError as e:
                error_content = e.content.decode() if e.content else str(e)
                logger.warning(f"YouTube upload attempt {attempt} failed: {error_content}")
                
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                else:
                    return YouTubeUploadResult(success=False, error=f"YouTube upload failed after {self.max_retries} attempts: {error_content}")
                    
            except Exception as e:
                logger.error(f"YouTube upload error: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    return YouTubeUploadResult(success=False, error=str(e))
        
        return YouTubeUploadResult(success=False, error="Unknown error")
    
    def _build_title(self, topic_config) -> str:
        """Build video title."""
        title = topic_config.title
        # YouTube Shorts title limit: 100 chars
        if len(title) > 100:
            title = title[:97] + "..."
        return title
    
    def _build_description(self, topic_config) -> str:
        """Build video description."""
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
        lines.extend([
            "🔔 Subscribe for more tech shorts!",
            "",
            "#Shorts #Tech #Education #Engineering"
        ])
        
        description = "\n".join(lines)
        # YouTube description limit: 5000 chars
        if len(description) > 5000:
            description = description[:4997] + "..."
        
        return description
    
    def _build_tags(self, topic_config) -> list:
        """Build video tags."""
        tags = set(self.default_tags)
        
        # Add hashtags as tags (without #)
        for tag in topic_config.hashtags:
            clean_tag = tag.lstrip("#")
            if clean_tag:
                tags.add(clean_tag)
        
        # Add topic words as tags
        topic_words = topic_config.topic.lower().split()
        for word in topic_words:
            if len(word) > 3:
                tags.add(word)
        
        # Limit to 500 chars total (YouTube limit)
        tag_list = list(tags)[:30]  # Reasonable limit
        return tag_list


def create_youtube_publisher(config: Dict[str, Any], credentials_config: Dict[str, Any]) -> YouTubePublisher:
    """Factory function to create YouTubePublisher."""
    return YouTubePublisher(config, credentials_config)