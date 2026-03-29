import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.config import settings, THUMB_DIR
from app.database import get_db
from app.models.edit import EditSession
from app.models.profile import Profile
from app.models.video import Video
from app.schemas.video import VideoOut, VideoUpdate

try:
    import imageio_ffmpeg

    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_BIN = "ffmpeg"

router = APIRouter()


@router.get("", response_model=list[VideoOut])
def list_videos(
    niche_id: int | None = None,
    status: str | None = None,
    source_account: str | None = None,
    search: str | None = None,
    sort: str | None = None,
    network_id: int | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Video)
    if network_id is not None:
        q = q.filter(Video.network_id == network_id)
    if niche_id:
        q = q.filter(Video.niche_id == niche_id)
    if status:
        q = q.filter(Video.status == status)
    if source_account:
        q = q.filter(Video.source_account == source_account)
    if search:
        q = q.filter(
            Video.shortcode.ilike(f"%{search}%")
            | Video.source_account.ilike(f"%{search}%")
            | Video.caption.ilike(f"%{search}%")
        )

    if sort == "status_priority":
        priority = case(
            (Video.status == "ready", 0),
            (Video.status == "editing", 1),
            (Video.status == "downloaded", 2),
            (Video.status == "queued", 3),
            (Video.status == "posting", 4),
            (Video.status == "posted", 5),
            else_=99,
        )
        q = q.order_by(priority, Video.scraped_at.desc())
    else:
        q = q.order_by(Video.scraped_at.desc())

    return q.offset(offset).limit(limit).all()


@router.get("/accounts")
def list_source_accounts(
    niche_id: int | None = None, db: Session = Depends(get_db)
):
    q = db.query(Video.source_account).distinct()
    if niche_id:
        q = q.filter(Video.niche_id == niche_id)
    return [row[0] for row in q.all()]


@router.get("/for-profile/{profile_id}")
def videos_for_profile(
    profile_id: int,
    limit: int = Query(200, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Return videos in the profile's niche with per-profile edit state."""
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    if not profile.niche_id:
        return []

    rows = (
        db.query(
            Video,
            EditSession.id.label("session_id"),
            EditSession.profile_status,
            EditSession.exported_path.label("profile_exported_path"),
        )
        .outerjoin(
            EditSession,
            (EditSession.video_id == Video.id)
            & (EditSession.profile_id == profile_id),
        )
        .filter(Video.niche_id == profile.niche_id)
        .order_by(
            case(
                (EditSession.profile_status == "ready", 0),
                (EditSession.profile_status == "edited", 1),
                (EditSession.profile_status == "rendering", 2),
                (EditSession.profile_status == "editing", 3),
                else_=4,
            ),
            Video.scraped_at.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []
    for video, session_id, profile_status, profile_exported_path in rows:
        d = VideoOut.model_validate(video).model_dump()
        d["session_id"] = session_id
        d["profile_status"] = profile_status
        d["profile_exported_path"] = profile_exported_path
        results.append(d)
    return results


@router.get("/{video_id}", response_model=VideoOut)
def get_video(video_id: int, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    return video


@router.patch("/{video_id}", response_model=VideoOut)
def update_video(video_id: int, body: VideoUpdate, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    data = body.model_dump(exclude_unset=True)
    for key, val in data.items():
        setattr(video, key, val)
    db.commit()
    db.refresh(video)
    return video


@router.get("/{video_id}/thumbnail")
def get_thumbnail(
    video_id: int,
    edited: bool = False,
    profile_id: int | None = None,
    db: Session = Depends(get_db),
):
    video = db.get(Video, video_id)
    if not video or not video.local_path:
        raise HTTPException(404, "Video not found")

    # When profile_id is provided, prefer per-profile exported_path from EditSession
    exported = None
    if edited and profile_id:
        session = (
            db.query(EditSession)
            .filter(EditSession.video_id == video_id, EditSession.profile_id == profile_id)
            .first()
        )
        if session and session.exported_path and Path(session.exported_path).exists():
            exported = session.exported_path
    if not exported and edited and video.exported_path:
        exported = video.exported_path

    if exported and Path(exported).exists():
        src = Path(exported)
        suffix = f"_edited_p{profile_id}" if profile_id else "_edited"
        thumb_path = THUMB_DIR / f"{video_id}{suffix}.jpg"
    else:
        src = Path(video.local_path)
        thumb_path = THUMB_DIR / f"{video_id}.jpg"

    no_cache_headers = {"Cache-Control": "no-cache, must-revalidate"}

    if thumb_path.exists():
        return FileResponse(thumb_path, media_type="image/jpeg", headers=no_cache_headers)

    if not src.exists():
        raise HTTPException(404, "Video file missing from disk")

    try:
        subprocess.run(
            [
                FFMPEG_BIN,
                "-ss",
                "1",
                "-i",
                str(src),
                "-vframes",
                "1",
                "-vf",
                "scale=320:-2",
                "-q:v",
                "4",
                "-y",
                str(thumb_path),
            ],
            capture_output=True,
            check=True,
            timeout=15,
        )
    except Exception:
        raise HTTPException(500, "Failed to generate thumbnail")

    if not thumb_path.exists():
        raise HTTPException(500, "Thumbnail generation produced no output")

    return FileResponse(thumb_path, media_type="image/jpeg", headers=no_cache_headers)


@router.get("/{video_id}/stream")
async def stream_video(
    video_id: int,
    edited: bool = False,
    profile_id: int | None = None,
    request: Request = None,
    db: Session = Depends(get_db),
):
    video = db.get(Video, video_id)
    if not video or not video.local_path:
        raise HTTPException(404, "Video file not found")

    # Prefer per-profile exported_path when profile_id is given
    exported = None
    if edited and profile_id:
        session = (
            db.query(EditSession)
            .filter(EditSession.video_id == video_id, EditSession.profile_id == profile_id)
            .first()
        )
        if session and session.exported_path and Path(session.exported_path).exists():
            exported = session.exported_path
    if not exported and edited and video.exported_path:
        exported = video.exported_path

    if exported and Path(exported).exists():
        path = Path(exported)
    else:
        path = Path(video.local_path)

    if not path.exists():
        raise HTTPException(404, "Video file missing from disk")

    file_size = path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        range_val = range_header.replace("bytes=", "")
        parts = range_val.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        def _iter():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            _iter(),
            status_code=206,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
                "Content-Type": "video/mp4",
            },
        )

    def _iter_full():
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(
        _iter_full(),
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": "video/mp4",
        },
    )


@router.delete("/{video_id}", status_code=204)
def delete_video(video_id: int, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    # Clean up files
    for p in [video.local_path, video.exported_path]:
        if p:
            path = Path(p)
            if path.exists():
                path.unlink()
    # Clean up thumbnails (original + edited)
    for suffix in [f"{video.id}.jpg", f"{video.id}_edited.jpg"]:
        thumb = THUMB_DIR / suffix
        if thumb.exists():
            thumb.unlink()
    db.delete(video)
    db.commit()
