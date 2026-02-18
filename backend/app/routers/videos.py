from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.video import Video
from app.schemas.video import VideoOut

router = APIRouter()


@router.get("", response_model=list[VideoOut])
def list_videos(
    niche_id: int | None = None,
    status: str | None = None,
    source_account: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Video)
    if niche_id:
        q = q.filter(Video.niche_id == niche_id)
    if status:
        q = q.filter(Video.status == status)
    if source_account:
        q = q.filter(Video.source_account == source_account)
    return q.order_by(Video.scraped_at.desc()).offset(offset).limit(limit).all()


@router.get("/{video_id}", response_model=VideoOut)
def get_video(video_id: int, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video:
        raise HTTPException(404, "Video not found")
    return video


@router.get("/{video_id}/stream")
async def stream_video(video_id: int, request: Request, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if not video or not video.local_path:
        raise HTTPException(404, "Video file not found")
    path = Path(video.local_path)
    if not path.exists():
        raise HTTPException(404, "Video file missing from disk")

    file_size = path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        # Parse Range: bytes=START-END
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
    db.delete(video)
    db.commit()
