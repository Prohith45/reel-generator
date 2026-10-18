"""
Publishing History Database
SQLite-based persistent storage for tracking published reels.
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from contextlib import contextmanager

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
DB_PATH = PROJECT_ROOT / "data" / "publishing_history.db"


@dataclass
class PublishedReel:
    """Record of a published reel."""
    id: Optional[int] = None
    topic: str = ""
    title: str = ""
    hook: str = ""
    description: str = ""
    hashtags: str = ""  # JSON array as string
    generation_options: str = ""  # JSON as string
    video_path: str = ""
    video_filename: str = ""
    generated_at: str = ""  # ISO format
    duration_seconds: float = 0.0
    file_size_bytes: int = 0
    
    # YouTube
    youtube_status: str = "pending"  # pending, published, failed, skipped
    youtube_video_id: str = ""
    youtube_url: str = ""
    youtube_error: str = ""
    youtube_retry_count: int = 0
    youtube_published_at: str = ""
    
    # Instagram
    instagram_status: str = "pending"  # pending, published, failed, skipped
    instagram_media_id: str = ""
    instagram_url: str = ""
    instagram_error: str = ""
    instagram_retry_count: int = 0
    instagram_published_at: str = ""
    
    # Overall
    overall_status: str = "pending"  # pending, partial, published, failed
    dry_run: bool = False
    created_at: str = ""  # ISO format
    updated_at: str = ""  # ISO format


class PublishingHistoryDB:
    """SQLite database for publishing history."""
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS published_reels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    title TEXT NOT NULL,
                    hook TEXT,
                    description TEXT,
                    hashtags TEXT,  -- JSON array
                    generation_options TEXT,  -- JSON
                    video_path TEXT NOT NULL,
                    video_filename TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    duration_seconds REAL DEFAULT 0,
                    file_size_bytes INTEGER DEFAULT 0,
                    
                    youtube_status TEXT DEFAULT 'pending',
                    youtube_video_id TEXT DEFAULT '',
                    youtube_url TEXT DEFAULT '',
                    youtube_error TEXT DEFAULT '',
                    youtube_retry_count INTEGER DEFAULT 0,
                    youtube_published_at TEXT DEFAULT '',
                    
                    instagram_status TEXT DEFAULT 'pending',
                    instagram_media_id TEXT DEFAULT '',
                    instagram_url TEXT DEFAULT '',
                    instagram_error TEXT DEFAULT '',
                    instagram_retry_count INTEGER DEFAULT 0,
                    instagram_published_at TEXT DEFAULT '',
                    
                    overall_status TEXT DEFAULT 'pending',
                    dry_run BOOLEAN DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_topic ON published_reels(topic)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_generated_at ON published_reels(generated_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_youtube_status ON published_reels(youtube_status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_instagram_status ON published_reels(instagram_status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_overall_status ON published_reels(overall_status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dry_run ON published_reels(dry_run)
            """)
            
            conn.commit()
        logger.info(f"Publishing history database initialized at {self.db_path}")
    
    @contextmanager
    def _get_conn(self):
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def add_reel(self, reel: PublishedReel) -> int:
        """Add a new reel record. Returns the row ID."""
        now = datetime.now().isoformat()
        if not reel.created_at:
            reel.created_at = now
        reel.updated_at = now
        
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO published_reels (
                    topic, title, hook, description, hashtags, generation_options,
                    video_path, video_filename, generated_at, duration_seconds,
                    file_size_bytes, youtube_status, instagram_status,
                    overall_status, dry_run, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                reel.topic, reel.title, reel.hook, reel.description,
                reel.hashtags, reel.generation_options,
                reel.video_path, reel.video_filename, reel.generated_at,
                reel.duration_seconds, reel.file_size_bytes,
                reel.youtube_status, reel.instagram_status,
                reel.overall_status, int(reel.dry_run),
                reel.created_at, reel.updated_at
            ))
            conn.commit()
            reel_id = cursor.lastrowid
            logger.info(f"Added reel record ID {reel_id}: {reel.topic}")
            return reel_id
    
    def update_reel(self, reel_id: int, updates: Dict[str, Any]) -> bool:
        """Update specific fields of a reel record."""
        if not updates:
            return False
        
        updates["updated_at"] = datetime.now().isoformat()
        fields = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [reel_id]
        
        with self._get_conn() as conn:
            cursor = conn.execute(
                f"UPDATE published_reels SET {fields} WHERE id = ?",
                values
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def get_reel(self, reel_id: int) -> Optional[PublishedReel]:
        """Get a reel by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM published_reels WHERE id = ?",
                (reel_id,)
            ).fetchone()
            return self._row_to_reel(row) if row else None
    
    def get_reel_by_video(self, video_filename: str) -> Optional[PublishedReel]:
        """Get a reel by video filename."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM published_reels WHERE video_filename = ?",
                (video_filename,)
            ).fetchone()
            return self._row_to_reel(row) if row else None
    
    def get_recent_topics(self, limit: int = 20) -> List[str]:
        """Get recently published topics for duplicate checking."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT topic FROM published_reels ORDER BY generated_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [row["topic"] for row in rows]
    
    def get_recent_reels(self, limit: int = 20, include_dry_run: bool = False) -> List[PublishedReel]:
        """Get recent reel records."""
        with self._get_conn() as conn:
            if include_dry_run:
                rows = conn.execute(
                    "SELECT * FROM published_reels ORDER BY generated_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM published_reels WHERE dry_run = 0 ORDER BY generated_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [self._row_to_reel(row) for row in rows]
    
    def get_pending_publish(self, platform: str) -> List[PublishedReel]:
        """Get reels pending publication on a platform."""
        with self._get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM published_reels WHERE {platform}_status = 'pending' AND dry_run = 0 ORDER BY generated_at ASC"
            ).fetchall()
            return [self._row_to_reel(row) for row in rows]
    
    def get_failed_publish(self, platform: str, max_retries: int = 3) -> List[PublishedReel]:
        """Get reels that failed publication and can be retried."""
        with self._get_conn() as conn:
            rows = conn.execute(
                f"""SELECT * FROM published_reels 
                    WHERE {platform}_status = 'failed' 
                    AND {platform}_retry_count < ?
                    AND dry_run = 0
                    ORDER BY generated_at ASC""",
                (max_retries,)
            ).fetchall()
            return [self._row_to_reel(row) for row in rows]
    
    def mark_youtube_published(self, reel_id: int, video_id: str, url: str):
        """Mark YouTube as published."""
        self.update_reel(reel_id, {
            "youtube_status": "published",
            "youtube_video_id": video_id,
            "youtube_url": url,
            "youtube_published_at": datetime.now().isoformat(),
            "youtube_error": ""
        })
        self._update_overall_status(reel_id)
    
    def mark_youtube_failed(self, reel_id: int, error: str):
        """Mark YouTube as failed."""
        reel = self.get_reel(reel_id)
        retry_count = (reel.youtube_retry_count if reel else 0) + 1
        self.update_reel(reel_id, {
            "youtube_status": "failed",
            "youtube_error": error,
            "youtube_retry_count": retry_count
        })
        self._update_overall_status(reel_id)
    
    def mark_instagram_published(self, reel_id: int, media_id: str, url: str):
        """Mark Instagram as published."""
        self.update_reel(reel_id, {
            "instagram_status": "published",
            "instagram_media_id": media_id,
            "instagram_url": url,
            "instagram_published_at": datetime.now().isoformat(),
            "instagram_error": ""
        })
        self._update_overall_status(reel_id)
    
    def mark_instagram_failed(self, reel_id: int, error: str):
        """Mark Instagram as failed."""
        reel = self.get_reel(reel_id)
        retry_count = (reel.instagram_retry_count if reel else 0) + 1
        self.update_reel(reel_id, {
            "instagram_status": "failed",
            "instagram_error": error,
            "instagram_retry_count": retry_count
        })
        self._update_overall_status(reel_id)
    
    def _update_overall_status(self, reel_id: int):
        """Update overall status based on platform statuses."""
        reel = self.get_reel(reel_id)
        if not reel:
            return
        
        yt = reel.youtube_status
        ig = reel.instagram_status
        
        # Treat "skipped" as neutral — only consider enabled platforms
        active = [s for s in (yt, ig) if s != "skipped"]
        
        if not active:
            overall = "published"  # Nothing to publish, trivially done
        elif all(s == "published" for s in active):
            overall = "published"
        elif all(s == "failed" for s in active):
            overall = "failed"
        elif any(s == "published" for s in active) and any(s == "failed" for s in active):
            overall = "partial"
        else:
            overall = "pending"
        
        self.update_reel(reel_id, {"overall_status": overall})
    
    def _row_to_reel(self, row: sqlite3.Row) -> PublishedReel:
        """Convert database row to PublishedReel object."""
        return PublishedReel(
            id=row["id"],
            topic=row["topic"],
            title=row["title"],
            hook=row["hook"] or "",
            description=row["description"] or "",
            hashtags=row["hashtags"] or "[]",
            generation_options=row["generation_options"] or "{}",
            video_path=row["video_path"],
            video_filename=row["video_filename"],
            generated_at=row["generated_at"],
            duration_seconds=row["duration_seconds"] or 0.0,
            file_size_bytes=row["file_size_bytes"] or 0,
            youtube_status=row["youtube_status"],
            youtube_video_id=row["youtube_video_id"] or "",
            youtube_url=row["youtube_url"] or "",
            youtube_error=row["youtube_error"] or "",
            youtube_retry_count=row["youtube_retry_count"] or 0,
            youtube_published_at=row["youtube_published_at"] or "",
            instagram_status=row["instagram_status"],
            instagram_media_id=row["instagram_media_id"] or "",
            instagram_url=row["instagram_url"] or "",
            instagram_error=row["instagram_error"] or "",
            instagram_retry_count=row["instagram_retry_count"] or 0,
            instagram_published_at=row["instagram_published_at"] or "",
            overall_status=row["overall_status"],
            dry_run=bool(row["dry_run"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
    
    def cleanup_old_records(self, days: int = 365, max_records: int = 1000):
        """Clean up old records beyond retention policy."""
        with self._get_conn() as conn:
            # Delete old records beyond max_records
            conn.execute("""
                DELETE FROM published_reels 
                WHERE id NOT IN (
                    SELECT id FROM published_reels 
                    ORDER BY generated_at DESC 
                    LIMIT ?
                )
            """, (max_records,))
            
            # Delete records older than retention period
            cutoff = datetime.now()
            from datetime import timedelta
            cutoff -= timedelta(days=days)
            conn.execute(
                "DELETE FROM published_reels WHERE generated_at < ?",
                (cutoff.isoformat(),)
            )
            conn.commit()


# Global instance
_db_instance: Optional[PublishingHistoryDB] = None


def get_db() -> PublishingHistoryDB:
    """Get global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = PublishingHistoryDB()
    return _db_instance


def init_db(db_path: Path = None) -> PublishingHistoryDB:
    """Initialize and return database instance."""
    global _db_instance
    _db_instance = PublishingHistoryDB(db_path)
    return _db_instance