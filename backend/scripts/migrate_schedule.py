"""Add schedule columns to profiles table.

Run once:  cd backend && python -m scripts.migrate_schedule
"""

import sqlite3
from app.config import settings

db_path = settings.database_url.replace("sqlite:///", "")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

migrations = [
    "ALTER TABLE profiles ADD COLUMN schedule_times TEXT DEFAULT NULL",
    "ALTER TABLE profiles ADD COLUMN daily_post_limit INTEGER DEFAULT 3 NOT NULL",
    "ALTER TABLE profiles ADD COLUMN warmup_started_at DATETIME DEFAULT NULL",
]

for sql in migrations:
    try:
        cur.execute(sql)
        print(f"OK: {sql}")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print(f"SKIP (exists): {sql}")
        else:
            raise

conn.commit()
conn.close()
print("Migration complete.")
