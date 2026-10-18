"""
Publisher Factory
Creates and manages publisher instances.
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


def load_credentials() -> Dict[str, Any]:
    """Load credentials from config files and environment variables."""
    import yaml
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass
    
    credentials = {
        "youtube": {},
        "instagram": {}
    }
    
    # Load from local config file (gitignored)
    local_config_path = PROJECT_ROOT / "config" / "automation.local.yaml"
    if local_config_path.exists():
        with open(local_config_path, "r") as f:
            local_config = yaml.safe_load(f) or {}
            credentials["youtube"].update(local_config.get("youtube", {}))
            credentials["instagram"].update(local_config.get("instagram", {}))
    
    # Override with environment variables (highest priority)
    # YouTube
    if os.getenv("YOUTUBE_CLIENT_ID"):
        credentials["youtube"]["client_id"] = os.getenv("YOUTUBE_CLIENT_ID")
    if os.getenv("YOUTUBE_CLIENT_SECRET"):
        credentials["youtube"]["client_secret"] = os.getenv("YOUTUBE_CLIENT_SECRET")
    if os.getenv("YOUTUBE_REFRESH_TOKEN"):
        credentials["youtube"]["refresh_token"] = os.getenv("YOUTUBE_REFRESH_TOKEN")
    
    # Instagram (Instagrapi - private mobile API)
    if os.getenv("INSTAGRAM_USERNAME"):
        credentials["instagram"]["username"] = os.getenv("INSTAGRAM_USERNAME")
    if os.getenv("INSTAGRAM_PASSWORD"):
        credentials["instagram"]["password"] = os.getenv("INSTAGRAM_PASSWORD")
    # Instagram (Meta Graph API)
    if os.getenv("INSTAGRAM_ACCESS_TOKEN"):
        credentials["instagram"]["access_token"] = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID"):
        credentials["instagram"]["instagram_business_account_id"] = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    elif os.getenv("INSTAGRAM_BUSINESS_ID"):
        credentials["instagram"]["instagram_business_account_id"] = os.getenv("INSTAGRAM_BUSINESS_ID")
    elif os.getenv("INSTAGRAM_ACCOUNT_ID"):
        credentials["instagram"]["instagram_business_account_id"] = os.getenv("INSTAGRAM_ACCOUNT_ID")
    if os.getenv("META_APP_ID"):
        credentials["instagram"]["app_id"] = os.getenv("META_APP_ID")
    if os.getenv("META_APP_SECRET"):
        credentials["instagram"]["app_secret"] = os.getenv("META_APP_SECRET")
    
    return credentials


def create_publishers(config: Dict[str, Any]) -> Dict[str, Any]:
    """Create publisher instances based on config."""
    credentials = load_credentials()
    publishers = {}
    
    # YouTube
    if config.get("youtube", {}).get("enabled", True):
        try:
            from automation.publisher.youtube_publisher import create_youtube_publisher
            publishers["youtube"] = create_youtube_publisher(config, credentials["youtube"])
            logger.info("YouTube publisher initialized")
        except Exception as e:
            logger.warning(f"YouTube publisher not available: {e}")
            publishers["youtube"] = None
    else:
        publishers["youtube"] = None
    
    # Instagram
    if config.get("instagram", {}).get("enabled", True):
        try:
            from automation.publisher.instagram_publisher import create_instagram_publisher
            publishers["instagram"] = create_instagram_publisher(config, credentials["instagram"])
            logger.info("Instagram publisher initialized")
        except Exception as e:
            logger.warning(f"Instagram publisher not available: {e}")
            publishers["instagram"] = None
    else:
        publishers["instagram"] = None
    
    return publishers


def get_publisher_status(publishers: Dict[str, Any]) -> Dict[str, bool]:
    """Get availability status of publishers."""
    return {
        "youtube": publishers.get("youtube") is not None,
        "instagram": publishers.get("instagram") is not None
    }