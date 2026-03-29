"""Add ai_description column to videos table."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "content_engine.db"

def migrate():
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    # Check if column exists
    cols = [r[1] for r in cur.execute("PRAGMA table_info(videos)").fetchall()]
    if "ai_description" not in cols:
        cur.execute("ALTER TABLE videos ADD COLUMN ai_description TEXT DEFAULT NULL")
        conn.commit()
        print("Added ai_description column to videos table")
    else:
        print("ai_description column already exists")
    conn.close()

if __name__ == "__main__":
    migrate()
