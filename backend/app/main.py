from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import settings, BASE_DIR
from app.database import Base, engine, get_db
from app.dependencies import get_optional_user
from app.models import user as _user_models  # noqa: F401 — register User/Network tables
from app.routers import niches, profiles, credentials, videos, scraper, templates, editor, auth, posts, networks
from app.services.scheduler_service import recover_stale_posts, start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create tables on startup (Alembic is the proper way, this is a fallback)
    Base.metadata.create_all(bind=engine)
    # Recover any posts stuck mid-publish from a previous crash
    recover_stale_posts()
    # Start background scheduler for scheduled posts
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Content Engine", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth dependency for protected routes (optional for now — returns None if no token)
_auth_dep = [Depends(get_optional_user)]

# API routers — protected (require auth when token provided)
app.include_router(niches.router, prefix="/api/niches", tags=["niches"], dependencies=_auth_dep)
app.include_router(profiles.router, prefix="/api/profiles", tags=["profiles"], dependencies=_auth_dep)
app.include_router(credentials.router, prefix="/api/credentials", tags=["credentials"], dependencies=_auth_dep)
app.include_router(videos.router, prefix="/api/videos", tags=["videos"], dependencies=_auth_dep)
app.include_router(scraper.router, prefix="/api/scraper", tags=["scraper"], dependencies=_auth_dep)
app.include_router(scraper.ws_router, prefix="/ws/scraper")
app.include_router(templates.router, prefix="/api/templates", tags=["templates"], dependencies=_auth_dep)
app.include_router(editor.router, prefix="/api/editor", tags=["editor"], dependencies=_auth_dep)
app.include_router(posts.router, prefix="/api/posts", tags=["posts"], dependencies=_auth_dep)
app.include_router(networks.router, prefix="/api/networks", tags=["networks"])

# Auth router — handles its own auth per-endpoint (register/login are public)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/install/{platform}")
async def serve_installer(platform: str):
    """Serve install scripts publicly (repo is private)."""
    from fastapi.responses import PlainTextResponse
    scripts = {
        "mac": BASE_DIR.parent / "install-mac.sh",
        "windows": BASE_DIR.parent / "install-windows.ps1",
    }
    script_path = scripts.get(platform)
    if not script_path or not script_path.exists():
        raise HTTPException(404, "Installer not found")
    return PlainTextResponse(script_path.read_text())


@app.get("/api/stats")
def stats(network_id: int | None = None, db: Session = Depends(get_db)):
    """Dashboard stats — lightweight counts by status."""
    from sqlalchemy import func
    from app.models.video import Video
    from app.models.post import PostQueue

    # Video counts by status
    vq = db.query(Video.status, func.count()).group_by(Video.status)
    if network_id is not None:
        vq = vq.filter(Video.network_id == network_id)
    video_rows = vq.all()
    video_counts = {status: count for status, count in video_rows}
    total_videos = sum(video_counts.values())

    # Post counts by status
    pq = db.query(PostQueue.status, func.count()).group_by(PostQueue.status)
    if network_id is not None:
        pq = pq.filter(PostQueue.network_id == network_id)
    post_rows = pq.all()
    post_counts = {status: count for status, count in post_rows}

    # Recent activity (last 10 videos)
    rq = db.query(Video.id, Video.source_account, Video.shortcode, Video.status, Video.scraped_at)
    if network_id is not None:
        rq = rq.filter(Video.network_id == network_id)
    recent = rq.order_by(Video.scraped_at.desc()).limit(10).all()
    recent_videos = [
        {
            "id": v.id,
            "source_account": v.source_account,
            "shortcode": v.shortcode,
            "status": v.status,
            "scraped_at": v.scraped_at.isoformat() if v.scraped_at else None,
        }
        for v in recent
    ]

    return {
        "total_videos": total_videos,
        "video_counts": video_counts,
        "post_counts": post_counts,
        "recent_videos": recent_videos,
    }


# Static file serving for downloads/exports/templates
app.mount("/static/downloads", StaticFiles(directory=str(settings.downloads_dir)), name="downloads")
app.mount("/static/exports", StaticFiles(directory=str(settings.exports_dir)), name="exports")
app.mount("/static/templates", StaticFiles(directory=str(settings.templates_dir)), name="templates")

# ── Serve built frontend (production) ───────────────────
# In Docker, frontend is built to ../static_frontend (sibling to app/)
# Locally, it's at ../../frontend/dist
_frontend_dir = BASE_DIR / "static_frontend"
if not _frontend_dir.exists():
    _frontend_dir = BASE_DIR.parent / "frontend" / "dist"

if _frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dir / "assets")), name="frontend-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """Serve frontend index.html for all non-API routes (SPA fallback)."""
        # Try to serve a static file first
        file_path = _frontend_dir / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dir / "index.html")
