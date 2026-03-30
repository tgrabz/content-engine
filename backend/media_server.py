#!/usr/bin/env python3
"""
Local Media Server for Content Engine.

Run this on your machine so the live site can load thumbnails and stream
videos from your local downloads/exports folders.

Usage:
    python media_server.py          # default port 8100
    python media_server.py 8200     # custom port

Then set "http://localhost:8100" as your Local Media Server URL in Settings.
"""

import sys
import uvicorn

# Re-use the existing FastAPI app's video routes — they already handle
# thumbnail generation and video streaming from local file paths.

from app.config import settings  # noqa: E402
from app.database import Base, engine  # noqa: E402

# Create tables if they don't exist locally
Base.metadata.create_all(bind=engine)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import videos

app = FastAPI(title="Content Engine - Local Media Server")

# Allow requests from any origin (the Railway site will call this)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(videos.router, prefix="/api/videos", tags=["videos"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "mode": "local-media"}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8100
    print(f"\n  Local Media Server running on http://localhost:{port}")
    print(f"  Set this URL in Settings → Local Media Server\n")
    uvicorn.run(app, host="0.0.0.0", port=port)
