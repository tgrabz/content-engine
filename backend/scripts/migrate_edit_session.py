"""One-time migration: add exported_path + profile_status to edit_sessions,
and create a unique index on (video_id, profile_id).

Safe to run multiple times — each ALTER is wrapped in try/except.
"""

import sqlite3
import sys
from pathlib import Path

# Resolve DB path relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "content_engine.db"


def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # 1. Add exported_path column
    try:
        cur.execute("ALTER TABLE edit_sessions ADD COLUMN exported_path TEXT")
        print("Added column: exported_path")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("Column exported_path already exists, skipping")
        else:
            raise

    # 2. Add profile_status column
    try:
        cur.execute("ALTER TABLE edit_sessions ADD COLUMN profile_status VARCHAR(20)")
        print("Added column: profile_status")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("Column profile_status already exists, skipping")
        else:
            raise

    # 3. Create unique index on (video_id, profile_id)
    try:
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uix_edit_session_video_profile "
            "ON edit_sessions (video_id, profile_id)"
        )
        print("Created unique index: uix_edit_session_video_profile")
    except sqlite3.OperationalError as e:
        print(f"Index creation note: {e}")

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    migrate()
