#!/usr/bin/env python3
"""Auto-configure ngrok tunnel and update network public_url in the database.

Starts ngrok, grabs the public URL, and writes it to all networks
so Instagram can download videos for posting.
"""

import json
import os
import subprocess
import sys
import time

import requests


def get_ngrok_url(max_retries=10):
    """Poll ngrok's local API to get the public URL."""
    for i in range(max_retries):
        try:
            r = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
            tunnels = r.json().get("tunnels", [])
            for t in tunnels:
                url = t.get("public_url", "")
                if url.startswith("https://"):
                    return url
        except Exception:
            pass
        time.sleep(1)
    return None


def update_database(public_url):
    """Update all networks with the current public URL."""
    try:
        # Use the app's config to get DATABASE_URL
        sys.path.insert(0, os.path.dirname(__file__))
        from app.config import settings

        if settings.database_url.startswith("sqlite"):
            import sqlite3
            conn = sqlite3.connect(settings.database_url.replace("sqlite:///", ""))
            conn.execute("UPDATE networks SET public_url = ?", (public_url,))
            conn.commit()
            conn.close()
        else:
            import psycopg2
            conn = psycopg2.connect(settings.database_url)
            cur = conn.cursor()
            cur.execute("UPDATE networks SET public_url = %s", (public_url,))
            conn.commit()
            cur.close()
            conn.close()
        print(f"  Updated all networks with public_url: {public_url}")
    except Exception as e:
        print(f"  Warning: could not update database: {e}")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

    # Check if ngrok is already running
    try:
        r = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=2)
        tunnels = r.json().get("tunnels", [])
        if tunnels:
            url = get_ngrok_url(max_retries=1)
            if url:
                print(f"\n  Tunnel already running: {url}\n")
                update_database(url)
                return
    except Exception:
        pass

    # Start ngrok
    print(f"\n  Starting tunnel to localhost:{port}...")
    proc = subprocess.Popen(
        ["ngrok", "http", str(port), "--log=stderr"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    url = get_ngrok_url()
    if url:
        print(f"  Tunnel ready: {url}")
        update_database(url)
    else:
        print("  Warning: could not get tunnel URL")

    # Keep running
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


if __name__ == "__main__":
    main()
