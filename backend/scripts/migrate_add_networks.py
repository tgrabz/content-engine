#!/usr/bin/env python3
"""Migration: Add multi-network support.

Creates users, networks, user_networks tables.
Adds network_id column to existing tables.
Backfills existing data into a default 'Network 1'.
Reads current IG credentials from .env for the default network.
"""

import base64
import hashlib
import secrets
import sqlite3
import sys
from pathlib import Path

# Resolve paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BACKEND_DIR / "data" / "content_engine.db"
ENV_PATH = BACKEND_DIR / ".env"


def read_env():
    """Read .env file into a dict."""
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def encrypt_value(value: str, secret_key: str) -> str:
    """Encrypt with Fernet using the same key derivation as the app."""
    from cryptography.fernet import Fernet
    key = hashlib.sha256(secret_key.encode()).digest()
    f = Fernet(base64.urlsafe_b64encode(key))
    return f.encrypt(value.encode()).decode()


def main():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        sys.exit(1)

    env = read_env()
    secret_key = env.get("SECRET_KEY", "change-me-in-production")

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys=OFF")
    cur = conn.cursor()

    print("=== Multi-Network Migration ===\n")

    # ── 1. Create new tables ──
    print("Creating users table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            display_name VARCHAR(100),
            role VARCHAR(20) DEFAULT 'member',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("Creating networks table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS networks (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            slug VARCHAR(100) UNIQUE NOT NULL,
            ig_app_id VARCHAR(100),
            ig_app_secret_enc TEXT,
            ig_redirect_uri VARCHAR(500),
            public_url VARCHAR(500),
            api_key VARCHAR(128) UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("Creating user_networks table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_networks (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            network_id INTEGER NOT NULL REFERENCES networks(id) ON DELETE CASCADE,
            role VARCHAR(20) DEFAULT 'member',
            UNIQUE(user_id, network_id)
        )
    """)

    # ── 2. Insert default network from .env ──
    cur.execute("SELECT COUNT(*) FROM networks")
    if cur.fetchone()[0] == 0:
        ig_app_id = env.get("IG_APP_ID", "")
        ig_app_secret = env.get("IG_APP_SECRET", "")
        ig_redirect_uri = env.get("IG_REDIRECT_URI", "https://localhost:5173/auth/callback")
        public_url = env.get("PUBLIC_URL", "")
        api_key = secrets.token_hex(32)

        ig_app_secret_enc = encrypt_value(ig_app_secret, secret_key) if ig_app_secret else None

        cur.execute("""
            INSERT INTO networks (id, name, slug, ig_app_id, ig_app_secret_enc, ig_redirect_uri, public_url, api_key, created_at, updated_at)
            VALUES (1, 'Default Network', 'default', ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (ig_app_id, ig_app_secret_enc, ig_redirect_uri, public_url, api_key))
        print(f"Created default network (API key: {api_key[:8]}...)")
    else:
        print("Networks table already has data, skipping default network creation")

    # ── 3. Add network_id columns to existing tables ──
    tables_to_update = [
        "niches", "profiles", "videos", "templates",
        "ig_login_credentials", "scrape_jobs", "post_queue",
    ]

    for table in tables_to_update:
        # Check if column already exists
        cur.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cur.fetchall()]
        if "network_id" not in columns:
            print(f"Adding network_id to {table}...")
            cur.execute(f"ALTER TABLE {table} ADD COLUMN network_id INTEGER REFERENCES networks(id) ON DELETE CASCADE")
            # Backfill with network 1
            cur.execute(f"UPDATE {table} SET network_id = 1")
        else:
            print(f"{table} already has network_id, skipping")

    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()
    conn.close()

    print("\n=== Migration complete! ===")
    print("Next: Register your account at the login page (first user becomes owner)")


if __name__ == "__main__":
    main()
