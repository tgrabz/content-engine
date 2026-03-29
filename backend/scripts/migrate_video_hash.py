"""Add video_hash column to videos table."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "content_engine.db"

def migrate():
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(videos)").fetchall()]
    if "video_hash" not in cols:
        cur.execute("ALTER TABLE videos ADD COLUMN video_hash VARCHAR(64) DEFAULT NULL")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_videos_hash ON videos(video_hash)")
        conn.commit()
        print("Added video_hash column + index to videos table")
    else:
        print("video_hash column already exists")
    conn.close()

if __name__ == "__main__":
    migrate()
