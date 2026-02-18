from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app.routers import niches, profiles, credentials, videos


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create tables on startup (Alembic is the proper way, this is a fallback)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Content Engine", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(niches.router, prefix="/api/niches", tags=["niches"])
app.include_router(profiles.router, prefix="/api/profiles", tags=["profiles"])
app.include_router(credentials.router, prefix="/api/credentials", tags=["credentials"])
app.include_router(videos.router, prefix="/api/videos", tags=["videos"])

# Static file serving for downloads/exports/templates
app.mount("/static/downloads", StaticFiles(directory=str(settings.downloads_dir)), name="downloads")
app.mount("/static/exports", StaticFiles(directory=str(settings.exports_dir)), name="exports")
app.mount("/static/templates", StaticFiles(directory=str(settings.templates_dir)), name="templates")


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
