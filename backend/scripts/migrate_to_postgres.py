"""Migrate local SQLite data to remote Postgres, assigning all data to a specific network."""

import sys
import sqlite3
import psycopg2
from datetime import datetime

# Remote Postgres (public URL for external access)
PG_URL = "postgresql://postgres:KbmcJjwkiYohSbOujdUiQBAsVOiHPUHU@gondola.proxy.rlwy.net:56830/railway"
SQLITE_PATH = "data/content_engine.db"


def migrate():
    # Get the network_id to assign data to
    network_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    print(f"Migrating local SQLite → Postgres (network_id={network_id})")

    lite = sqlite3.connect(SQLITE_PATH)
    lite.row_factory = sqlite3.Row
    pg = psycopg2.connect(PG_URL)
    cur = pg.cursor()

    # ── Niches ──
    rows = lite.execute("SELECT * FROM niches").fetchall()
    for r in rows:
        cur.execute(
            """INSERT INTO niches (id, name, network_id, created_at)
               VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
            (r["id"], r["name"], network_id, r["created_at"]),
        )
    print(f"  niches: {len(rows)}")

    # ── Profiles ──
    rows = lite.execute("SELECT * FROM profiles").fetchall()
    for r in rows:
        cur.execute(
            """INSERT INTO profiles (id, name, niche_id, export_dir, network_id, created_at)
               VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
            (r["id"], r["name"], r["niche_id"], r["export_dir"], network_id, r["created_at"]),
        )
    print(f"  profiles: {len(rows)}")

    # ── Credentials ──
    rows = lite.execute("SELECT * FROM ig_login_credentials").fetchall()
    cols = [d[0] for d in lite.execute("SELECT * FROM ig_login_credentials LIMIT 0").description]
    for r in rows:
        cur.execute(
            """INSERT INTO ig_login_credentials (id, username, password_enc, network_id, created_at)
               VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
            (r["id"], r["username"], r["password_enc"], network_id, r["created_at"]),
        )
    print(f"  credentials: {len(rows)}")

    # ── Videos ──
    rows = lite.execute("SELECT * FROM videos").fetchall()
    cols = [d[0] for d in lite.execute("SELECT * FROM videos LIMIT 0").description]
    for r in rows:
        rd = dict(r)
        cur.execute(
            """INSERT INTO videos (id, source_account, shortcode, media_url, local_path, thumbnail_path,
               caption, status, niche_id, profile_id, network_id, scraped_at, duration, width, height,
               ig_media_id, ig_permalink)
               VALUES (%(id)s, %(source_account)s, %(shortcode)s, %(media_url)s, %(local_path)s,
               %(thumbnail_path)s, %(caption)s, %(status)s, %(niche_id)s, %(profile_id)s, %(network_id)s,
               %(scraped_at)s, %(duration)s, %(width)s, %(height)s, %(ig_media_id)s, %(ig_permalink)s)
               ON CONFLICT (id) DO NOTHING""",
            {
                "id": rd.get("id"),
                "source_account": rd.get("source_account"),
                "shortcode": rd.get("shortcode"),
                "media_url": rd.get("media_url"),
                "local_path": rd.get("local_path"),
                "thumbnail_path": rd.get("thumbnail_path"),
                "caption": rd.get("caption"),
                "status": rd.get("status", "scraped"),
                "niche_id": rd.get("niche_id"),
                "profile_id": rd.get("profile_id"),
                "network_id": network_id,
                "scraped_at": rd.get("scraped_at"),
                "duration": rd.get("duration"),
                "width": rd.get("width"),
                "height": rd.get("height"),
                "ig_media_id": rd.get("ig_media_id"),
                "ig_permalink": rd.get("ig_permalink"),
            },
        )
    print(f"  videos: {len(rows)}")

    # ── Templates ──
    rows = lite.execute("SELECT * FROM templates").fetchall()
    for r in rows:
        rd = dict(r)
        cur.execute(
            """INSERT INTO templates (id, name, profile_id, network_id, canvas_json, preview_path,
               video_box, created_at, updated_at)
               VALUES (%(id)s, %(name)s, %(profile_id)s, %(network_id)s, %(canvas_json)s,
               %(preview_path)s, %(video_box)s, %(created_at)s, %(updated_at)s)
               ON CONFLICT (id) DO NOTHING""",
            {
                "id": rd.get("id"),
                "name": rd.get("name"),
                "profile_id": rd.get("profile_id"),
                "network_id": network_id,
                "canvas_json": rd.get("canvas_json"),
                "preview_path": rd.get("preview_path"),
                "video_box": rd.get("video_box"),
                "created_at": rd.get("created_at"),
                "updated_at": rd.get("updated_at"),
            },
        )
    print(f"  templates: {len(rows)}")

    # ── Scrape Jobs ──
    rows = lite.execute("SELECT * FROM scrape_jobs").fetchall()
    for r in rows:
        rd = dict(r)
        cur.execute(
            """INSERT INTO scrape_jobs (id, account, status, total_found, total_downloaded,
               network_id, started_at, finished_at, error_message)
               VALUES (%(id)s, %(account)s, %(status)s, %(total_found)s, %(total_downloaded)s,
               %(network_id)s, %(started_at)s, %(finished_at)s, %(error_message)s)
               ON CONFLICT (id) DO NOTHING""",
            {
                "id": rd.get("id"),
                "account": rd.get("account"),
                "status": rd.get("status"),
                "total_found": rd.get("total_found"),
                "total_downloaded": rd.get("total_downloaded"),
                "network_id": network_id,
                "started_at": rd.get("started_at"),
                "finished_at": rd.get("finished_at"),
                "error_message": rd.get("error_message"),
            },
        )
    print(f"  scrape_jobs: {len(rows)}")

    # ── Post Queue ──
    rows = lite.execute("SELECT * FROM post_queue").fetchall()
    for r in rows:
        rd = dict(r)
        cur.execute(
            """INSERT INTO post_queue (id, video_id, profile_id, network_id, caption, status,
               scheduled_at, published_at, error_message, ig_media_id)
               VALUES (%(id)s, %(video_id)s, %(profile_id)s, %(network_id)s, %(caption)s,
               %(status)s, %(scheduled_at)s, %(published_at)s, %(error_message)s, %(ig_media_id)s)
               ON CONFLICT (id) DO NOTHING""",
            {
                "id": rd.get("id"),
                "video_id": rd.get("video_id"),
                "profile_id": rd.get("profile_id"),
                "network_id": network_id,
                "caption": rd.get("caption"),
                "status": rd.get("status"),
                "scheduled_at": rd.get("scheduled_at"),
                "published_at": rd.get("published_at"),
                "error_message": rd.get("error_message"),
                "ig_media_id": rd.get("ig_media_id"),
            },
        )
    print(f"  post_queue: {len(rows)}")

    # Reset sequences so new inserts don't conflict
    for table in ["niches", "profiles", "ig_login_credentials", "videos", "templates", "scrape_jobs", "post_queue"]:
        cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1)) FROM {table}")

    pg.commit()
    cur.close()
    pg.close()
    lite.close()
    print("\nDone! All local data migrated to Postgres.")


if __name__ == "__main__":
    migrate()
