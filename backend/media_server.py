#!/usr/bin/env python3
"""
Local Media Server for Content Engine.

Run this on your machine so the live site can load thumbnails and stream
videos from your shared Google Drive folder.

Usage:
    python media_server.py                        # auto-detects Google Drive
    python media_server.py --port 8200            # custom port
    python media_server.py --media-root /path/to  # custom media root

Then set "http://localhost:8100" as your Local Media Server URL in Settings.
"""

import argparse
import os
import sys
from pathlib import Path

# Auto-detect Google Drive media folder
def find_gdrive_media():
    cloud_storage = Path.home() / "Library" / "CloudStorage"
    if not cloud_storage.exists():
        # Windows
        cloud_storage = Path.home() / "Google Drive"
        if not cloud_storage.exists():
            cloud_storage = Path(os.environ.get("GOOGLE_DRIVE_PATH", ""))

    if cloud_storage.exists():
        for d in cloud_storage.iterdir():
            if d.name.startswith("GoogleDrive"):
                media = d / "My Drive" / "content-engine-media"
                if media.exists():
                    return media

    # Windows: check common paths
    for base in [Path.home() / "Google Drive" / "My Drive", Path.home() / "Google Drive"]:
        media = base / "content-engine-media"
        if media.exists():
            return media

    return None


parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, default=8100)
parser.add_argument("--media-root", type=str, default=None)
args = parser.parse_args()

# Set MEDIA_ROOT before importing app config
media_root = args.media_root
if not media_root:
    gdrive = find_gdrive_media()
    if gdrive:
        media_root = str(gdrive)
        print(f"  Found Google Drive media: {gdrive}")
    else:
        media_root = str(Path(__file__).parent)
        print(f"  No Google Drive found, using local: {media_root}")

os.environ["MEDIA_ROOT"] = media_root

import uvicorn
from app.config import settings
from app.database import Base, engine

Base.metadata.create_all(bind=engine)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import videos

app = FastAPI(title="Content Engine - Local Media Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(videos.router, prefix="/api/videos", tags=["videos"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "mode": "local-media", "media_root": media_root}


if __name__ == "__main__":
    print(f"\n  Local Media Server on http://localhost:{args.port}")
    print(f"  Media root: {media_root}")
    print(f"  Set this URL in Settings → Local Media Server\n")
    uvicorn.run(app, host="0.0.0.0", port=args.port)
